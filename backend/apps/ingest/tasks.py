"""数据导入 Celery 异步任务

处理文件上传 → 解析 → 渠道表写入 → 统一交易表同步 的完整流程。
"""

import hashlib
import os
import tempfile

from celery import shared_task
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_import_file(self, import_file_id):
    """Process a single import file: parse → channel table → transactions sync."""
    try:
        import_file = ImportFile.objects.get(id=import_file_id)
    except ImportFile.DoesNotExist:
        return {"error": f"ImportFile {import_file_id} not found"}

    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    try:
        file_path = import_file.filename  # stored as full path from upload

        if import_file.file_type == "alipay_csv":
            txns = parse_alipay_csv(file_path)
            platform = "alipay"
        elif import_file.file_type == "wechat_xlsx":
            txns = parse_wechat_xlsx(file_path)
            platform = "wechat"
        elif import_file.file_type in ("boc_csv", "boc_pdf"):
            # boc_pdf should have been converted to CSV by OCR task first
            txns = parse_boc_csv(file_path)
            platform = "boc"
        else:
            raise ValueError(f"Unknown file type: {import_file.file_type}")

        created, skipped = _sync_to_transactions(
            txns, platform, import_file.file_type
        )

        import_file.status = "completed"
        import_file.save(update_fields=["status"])

        return {"created": created, "skipped": skipped}

    except Exception as exc:
        import_file.status = "failed"
        import_file.error_msg = str(exc)
        import_file.save(update_fields=["status", "error_msg"])
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, time_limit=3600)
def process_pdf_ocr(self, import_file_id):
    """OCR processing for BOC PDF: PDF → CSV → parse → sync."""
    import_file = ImportFile.objects.get(id=import_file_id)
    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    try:
        from apps.ocr_service.pipeline import pdf_to_csv
        import tempfile as tmpfile

        pdf_path = import_file.filename
        output_dir = os.path.dirname(pdf_path)
        output_path = os.path.join(
            output_dir,
            f"{os.path.splitext(os.path.basename(pdf_path))[0]}.csv",
        )

        result = pdf_to_csv(pdf_path, "boc", output_path=output_path)

        if result != 0:
            raise RuntimeError("OCR pipeline failed")

        # Now parse the generated CSV
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


@shared_task
def process_import_job(job_id):
    """Orchestrate import job: dispatch sub-tasks, update progress.

    Uses Celery chord to avoid deadlock — subtasks run in parallel,
    and the chord callback updates job status when all complete.
    """
    from celery import chord

    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return {"error": f"ImportJob {job_id} not found"}

    job.status = "processing"
    job.save(update_fields=["status"])

    import_files = job.files.all()
    subtasks = []

    for import_file in import_files:
        if import_file.file_type == "boc_pdf":
            subtask = process_pdf_ocr.s(import_file.id)
        else:
            subtask = process_import_file.s(import_file.id)
        subtasks.append(subtask)

    if not subtasks:
        job.status = "completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return {"total": 0, "processed": 0}

    # Chord: run all subtasks in parallel, then call _on_import_job_complete
    chord(subtasks)(_on_import_job_complete.s(job_id))

    return {"job_id": job_id, "status": "processing", "total_files": len(subtasks)}


@shared_task
def _on_import_job_complete(results, job_id):
    """Chord callback: update ImportJob status after all subtasks complete."""
    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return

    job.status = "completed"
    job.processed = job.total_files
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "processed", "completed_at"])
