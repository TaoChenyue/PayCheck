"""PDF → CSV 管线编排

管线:
  process_pdf():    单个 PDF → 图片 → OCR → CSV
  process_folder(): 文件夹批量处理 → 每个 PDF 输出同名 CSV（已存在则跳过）
"""

import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from boc_pdf2csv.layout import group_items_to_rows, rows_to_transactions
from boc_pdf2csv.ocr_engine import process_image, warmup_engine
from boc_pdf2csv.pdf_render import pdf_to_images
from boc_pdf2csv.csv_writer import write_csv

log = logging.getLogger("boc_pdf2csv.pipeline")


# =========================================================================
# 内部：单 PDF → 交易列表
# =========================================================================

def _pdf_to_transactions(
    pdf_path: str,
    scale: float = 3.0,
    timeout_minutes: int = 60,
    verbose: bool = False,
    device: str = "gpu",
    progress_cb=None,
) -> List[Dict[str, Any]]:
    """处理单个 PDF，返回交易字典列表（不写 CSV）

    Args:
        pdf_path: PDF 文件路径
        scale: 渲染缩放倍率
        timeout_minutes: 超时分钟数
        verbose: 是否输出详细日志
        device: OCR 推理设备，"gpu"（默认，强制 GPU）或 "cpu"
        progress_cb: 可选进度回调 callback(event, info)，事件见 process_folder 文档；
            不传时行为与命令行完全一致

    Returns:
        交易字典列表（可能为空）
    """
    if not os.path.exists(pdf_path):
        log.error("文件不存在: %s", pdf_path)
        return []

    def _emit(event: str, info: Dict[str, Any]) -> None:
        if progress_cb:
            progress_cb(event, info)

    start_time = time.time()
    max_timeout = timeout_minutes * 60
    pdf_name = os.path.basename(pdf_path)

    with tempfile.TemporaryDirectory(prefix="boc_pdf2csv_") as tmpdir:
        # 阶段一：PDF → 图片
        image_paths = pdf_to_images(pdf_path, scale=scale, output_dir=tmpdir)
        if not image_paths:
            log.warning("PDF 渲染无输出: %s", pdf_path)
            # 与 process_folder 的「写出表头 CSV、计为已处理」语义一致，收尾事件照发
            _emit("pdf_done", {
                "name": pdf_name,
                "transactions": 0,
                "duration_s": round(time.time() - start_time, 1),
            })
            return []

        # 阶段二：图片 → OCR → 结构化
        _emit("engine_loading", {"device": device})
        warmup_engine(device)

        def _page_key(p: str) -> int:
            m = re.search(r'p(\d+)\.png$', p)
            return int(m.group(1)) if m else 0

        sorted_paths = sorted(image_paths, key=_page_key)
        total_pages = len(sorted_paths)

        all_transactions: List[Dict[str, Any]] = []
        stem = os.path.splitext(pdf_name)[0]

        _emit("pdf_start", {"name": pdf_name, "pages_total": total_pages})
        for page_num, img_path in enumerate(sorted_paths):
            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                tqdm.write(f"⏰ 超时 {timeout_minutes} 分钟，已处理 {page_num}/{total_pages} 页")
                break

            try:
                items = process_image(img_path, device=device)
                if items:
                    rows = group_items_to_rows(items, scale)
                    txn_dicts = rows_to_transactions(rows)
                    all_transactions.extend(txn_dicts)
                    if verbose:
                        tqdm.write(f"  [{stem}] 第 {page_num + 1} 页: {len(items)} 个OCR块 → {len(txn_dicts)} 条交易")
            except Exception as e:
                log.error("[%s] 第 %d 页处理失败: %s", pdf_name, page_num + 1, e)
                if verbose:
                    tqdm.write(f"  [{stem}] 第 {page_num + 1} 页失败: {e}")

            _emit("page_done", {
                "name": pdf_name,
                "page": page_num + 1,
                "pages_total": total_pages,
                "transactions_so_far": len(all_transactions),
            })

        _emit("pdf_done", {
            "name": pdf_name,
            "transactions": len(all_transactions),
            "duration_s": round(time.time() - start_time, 1),
        })
        return all_transactions


# =========================================================================
# 公开 API
# =========================================================================

def process_pdf(
    pdf_path: str,
    output_path: Optional[str] = None,
    scale: float = 3.0,
    timeout_minutes: int = 60,
    verbose: bool = False,
    device: str = "gpu",
) -> str:
    """单个 PDF → CSV 完整流水线

    内部使用临时目录存储中间图片，处理完后自动清理。

    Args:
        pdf_path: PDF 文件路径
        output_path: 输出 CSV 路径（不指定则只返回字符串不写文件）
        scale: 渲染缩放倍率
        timeout_minutes: 单 PDF 超时分钟数
        verbose: 是否输出详细日志
        device: OCR 推理设备，"gpu"（默认，强制 GPU）或 "cpu"

    Returns:
        CSV 内容字符串

    Raises:
        FileNotFoundError: PDF 文件不存在
        RuntimeError: 渲染失败 / 无可用 GPU
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    start_time = time.time()
    transactions = _pdf_to_transactions(pdf_path, scale, timeout_minutes, verbose, device)

    elapsed = time.time() - start_time
    log.info("处理完成: %d 条交易, 耗时 %.1fs", len(transactions), elapsed)

    if not transactions:
        return ""

    return write_csv(transactions, output_path)


@dataclass
class FolderResult:
    """process_folder 的批量处理汇总

    Attributes:
        processed: 成功处理的 PDF 路径 → 同名 CSV 路径
        skipped: 因同名 CSV 已存在而跳过的 PDF 路径
        failed: 处理失败的 PDF 路径
        total_transactions: 提取到的交易总数（去重后）
    """
    processed: Dict[str, str] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    total_transactions: int = 0


def process_folder(
    folder_path: str,
    scale: float = 3.0,
    timeout_minutes: int = 60,
    verbose: bool = False,
    device: str = "gpu",
    force: bool = False,
    progress_cb=None,
    pdf_names: Optional[List[str]] = None,
) -> FolderResult:
    """批量处理文件夹内所有 PDF，每个 PDF 输出同名 CSV

    处理流程:
      1. 扫描文件夹中所有 .pdf 文件
      2. 同名 CSV 已存在的 PDF 直接跳过（force=True 时覆盖重新导出）
      3. 逐个 PDF 调用 OCR 管线（默认强制 GPU）
      4. 每个 PDF 的交易去重（按日期+金额+对方账户名）
      5. 按日期+时间排序
      6. 写出 <同名>.csv 到 PDF 所在文件夹

    Args:
        folder_path: 包含 PDF 文件的文件夹路径
        scale: 渲染缩放倍率
        timeout_minutes: 单个 PDF 超时分钟数
        verbose: 是否输出详细日志
        device: OCR 推理设备，"gpu"（默认，强制 GPU）或 "cpu"
        force: 是否强制重新导出（同名 CSV 已存在时覆盖而不是跳过）
        progress_cb: 可选进度回调 callback(event, info)；不传时行为与命令行一致。
            事件（info 为 dict）：
              engine_loading {device}                      模型加载开始
              pdf_start      {name, pages_total}           单 PDF 处理开始
              page_done      {name, page, pages_total,
                              transactions_so_far}         单页处理完成
              pdf_done       {name, transactions, duration_s}
              pdf_skipped    {name, error}                 同名 CSV 已存在被跳过
              pdf_failed     {name, error}                 单 PDF 处理失败
        pdf_names: 可选，仅处理指定文件名列表中的 PDF（大小写不敏感；
            默认处理文件夹内全部 PDF，与命令行行为一致）

    Returns:
        FolderResult 批量处理汇总

    Raises:
        NotADirectoryError: 输入路径非目录
        FileNotFoundError: 未找到 PDF 文件
        RuntimeError: 全部 PDF 处理失败
    """
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"输入路径不存在或非目录: {folder_path}")

    # 扫描 PDF 文件
    pdf_files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".pdf")
    ])
    if pdf_names:
        wanted = {n.lower() for n in pdf_names}
        pdf_files = [p for p in pdf_files if os.path.basename(p).lower() in wanted]

    if not pdf_files:
        raise FileNotFoundError(f"未找到 PDF 文件: {folder_path}")

    log.info("扫描到 %d 个 PDF 文件", len(pdf_files))
    if verbose:
        log.info("PDF 列表: %s", [os.path.basename(p) for p in pdf_files])

    result = FolderResult()

    with tqdm(total=len(pdf_files), desc="处理 PDF", unit="个",
              disable=progress_cb is not None) as pbar:
        for pdf_path in pdf_files:
            pdf_name = os.path.basename(pdf_path)
            csv_path = os.path.splitext(pdf_path)[0] + ".csv"

            # 同名 CSV 已存在 → 跳过（force 时覆盖重新导出）
            if not force and os.path.exists(csv_path):
                result.skipped.append(pdf_path)
                if progress_cb:
                    progress_cb("pdf_skipped", {"name": pdf_name, "error": "同名 CSV 已存在"})
                pbar.set_postfix_str(f"跳过 {pdf_name}")
                log.info("跳过（同名 CSV 已存在）: %s", pdf_name)
                if verbose:
                    tqdm.write(f"  [{pdf_name}] 跳过: {os.path.basename(csv_path)} 已存在")
                pbar.update(1)
                continue

            pbar.set_postfix_str(pdf_name)
            try:
                transactions = _pdf_to_transactions(pdf_path, scale, timeout_minutes, verbose, device, progress_cb)
            except Exception as e:
                log.error("处理失败: %s — %s", pdf_name, e)
                result.failed.append(pdf_path)
                if progress_cb:
                    progress_cb("pdf_failed", {"name": pdf_name, "error": str(e)})
                if verbose:
                    tqdm.write(f"  [{pdf_name}] 失败: {e}")
                pbar.update(1)
                continue

            # 去重（按日期 + 金额 + 对方账户名）
            seen = set()
            deduped: List[Dict[str, Any]] = []
            for t in transactions:
                key = (t.get("date"), t.get("amount"), t.get("counterparty"))
                if key not in seen:
                    seen.add(key)
                    deduped.append(t)

            # 按日期 + 时间排序
            deduped.sort(key=lambda t: (t.get("date", ""), t.get("time", "")))

            # 写出同名 CSV（即使无交易也写表头，保证重跑时跳过）
            write_csv(deduped, csv_path)
            result.processed[pdf_path] = csv_path
            result.total_transactions += len(deduped)
            log.info("%s → %s (%d 条交易)", pdf_name, os.path.basename(csv_path), len(deduped))
            if verbose:
                tqdm.write(f"  [{pdf_name}] → {os.path.basename(csv_path)} ({len(deduped)} 条交易)")
            pbar.update(1)

    if not result.processed and result.failed:
        raise RuntimeError(f"处理失败: {len(result.failed)}/{len(pdf_files)} 个 PDF 处理出错")

    return result
