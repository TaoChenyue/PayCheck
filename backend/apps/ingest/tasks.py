"""数据导入异步任务（去 Celery 化）

处理文件上传 → 解析 → 渠道表写入 → 统一交易表同步 的完整流程。
"""

import hashlib
import os

from django.db import IntegrityError
from django.utils import timezone

from apps.ingest.models import ImportJob, ImportFile
from apps.ingest.parsers.alipay import parse_alipay_csv
from apps.ingest.parsers.wechat import parse_wechat_xlsx
from apps.ingest.parsers.boc import parse_boc_csv
from apps.channels.models import AlipayTx, WechatTx, BocTx
from apps.transactions.models import Transaction


def _compute_row_hash(time_str, amount, counterparty, platform):
    """MD5 hash for dedup: time|amount|counterparty|platform"""
    raw = f"{time_str}|{amount:.2f}|{counterparty}|{platform}"
    return hashlib.md5(raw.encode()).hexdigest()


def _sync_to_transactions(tx_dicts, platform, source_model_label):
    """Sync channel table records to transactions table with dedup.

    Args:
        tx_dicts: List of dicts returned by parser
        platform: 'alipay' | 'wechat' | 'boc'
        source_model_label: file_type string

    Returns:
        (created_count, skipped_count)
    """
    channel_model = {"alipay": AlipayTx, "wechat": WechatTx, "boc": BocTx}[platform]
    created = 0
    skipped = 0

    for tx in tx_dicts:
        row_hash = _compute_row_hash(
            tx["time"], tx["amount"], tx.get("counterparty", ""), platform
        )

        # Check if transaction already exists by row_hash
        if Transaction.objects.filter(row_hash=row_hash).exists():
            skipped += 1
            continue

        # Create channel record
        channel_kwargs = {
            "time": tx["time"],
            "category": tx.get("category", ""),
            "counterparty": tx.get("counterparty", ""),
            "description": tx.get("description", ""),
            "amount": tx["amount"],
            "tx_type": tx.get("tx_type", "支出"),
            "payment_method": tx.get("payment_method", ""),
        }
        if platform == "boc":
            channel_kwargs.update({
                "balance": tx.get("balance", 0.0),
                "currency": tx.get("currency", ""),
                "branch": tx.get("branch", ""),
                "cp_account": tx.get("cp_account", ""),
                "cp_bank": tx.get("cp_bank", ""),
            })

        channel_record = channel_model.objects.create(**channel_kwargs)

        # Create transaction record
        tx_kwargs = {
            "platform": platform,
            "source_channel": platform,
            "source_id": channel_record.id,
            "row_hash": row_hash,
            **channel_kwargs,
        }
        try:
            Transaction.objects.create(**tx_kwargs)
        except IntegrityError:
            # Race condition: duplicate row_hash from concurrent task
            skipped += 1
            continue
        created += 1

    return created, skipped


def _process_import_file_once(import_file_id: int) -> dict:
    """单次执行文件解析（内部函数，不含重试）"""
    import_file = ImportFile.objects.get(id=import_file_id)
    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    file_path = import_file.filename

    if import_file.file_type == "alipay_csv":
        txns = parse_alipay_csv(file_path)
        platform = "alipay"
    elif import_file.file_type == "wechat_xlsx":
        txns = parse_wechat_xlsx(file_path)
        platform = "wechat"
    elif import_file.file_type in ("boc_csv", "boc_pdf"):
        txns = parse_boc_csv(file_path)
        platform = "boc"
    else:
        raise ValueError(f"Unknown file type: {import_file.file_type}")

    created, skipped = _sync_to_transactions(txns, platform, import_file.file_type)

    import_file.status = "completed"
    import_file.save(update_fields=["status"])

    return {"created": created, "skipped": skipped}


def process_import_file(import_file_id: int) -> dict:
    """处理单个导入文件：解析 → 渠道表 → 交易表（同步）

    简单重试策略：max_retries=1，失败即标记 failed。
    """
    max_retries = 1

    for attempt in range(max_retries + 1):
        try:
            return _process_import_file_once(import_file_id)
        except Exception as exc:
            if attempt < max_retries:
                continue
            # 最后一次也失败了
            try:
                import_file = ImportFile.objects.get(id=import_file_id)
                import_file.status = "failed"
                import_file.error_msg = str(exc)
                import_file.save(update_fields=["status", "error_msg"])
            except ImportFile.DoesNotExist:
                pass
            raise

    return {"error": "max_retries exceeded"}


def process_pdf_ocr(import_file_id: int) -> dict:
    """OCR 处理 BOC PDF：PDF → CSV → 解析 → 入库"""
    import_file = ImportFile.objects.get(id=import_file_id)
    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    try:
        from apps.ocr_service.pipeline import pdf_to_csv

        pdf_path = import_file.filename
        output_dir = os.path.dirname(pdf_path)
        output_path = os.path.join(
            output_dir,
            f"{os.path.splitext(os.path.basename(pdf_path))[0]}.csv",
        )

        result = pdf_to_csv(pdf_path, "boc", output_path=output_path)
        if result != 0:
            raise RuntimeError("OCR pipeline failed")

        txns = parse_boc_csv(output_path)
        created, skipped = _sync_to_transactions(txns, "boc", "boc_pdf")

        import_file.status = "completed"
        import_file.save(update_fields=["status"])

        return {"created": created, "skipped": skipped}

    except Exception as exc:
        import_file.status = "failed"
        import_file.error_msg = str(exc)
        import_file.save(update_fields=["status", "error_msg"])
        raise


def process_import_job(job_id: int) -> dict:
    """编排导入任务：并行分发子任务，全部完成后更新 Job 状态"""
    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return {"error": f"ImportJob {job_id} not found"}

    job.status = "processing"
    job.save(update_fields=["status"])

    import_files = job.files.all()
    if not import_files:
        job.status = "completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return {"total": 0, "processed": 0}

    # 构建任务列表
    from apps.ingest.executor import run_parallel

    def make_task(import_file):
        if import_file.file_type == "boc_pdf":
            return lambda fid=import_file.id: process_pdf_ocr(fid)
        else:
            return lambda fid=import_file.id: process_import_file(fid)

    tasks = [make_task(f) for f in import_files]
    run_parallel(tasks, callback=_on_import_job_complete, callback_args=(job_id,))

    return {"job_id": job_id, "status": "processing", "total_files": len(tasks)}


def _on_import_job_complete(results: list, job_id: int) -> None:
    """所有子任务完成后的回调：更新 ImportJob 状态"""
    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return

    job.status = "completed"
    job.processed = job.total_files
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "processed", "completed_at"])
