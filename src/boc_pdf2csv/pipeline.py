"""PDF → CSV 管线编排

管线:
  process_pdf():    单个 PDF → 图片 → OCR → CSV
  process_folder(): 文件夹批量处理 → 合并去重 → CSV
"""

import logging
import os
import re
import tempfile
import time
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
) -> List[Dict[str, Any]]:
    """处理单个 PDF，返回交易字典列表（不写 CSV）

    Args:
        pdf_path: PDF 文件路径
        scale: 渲染缩放倍率
        timeout_minutes: 超时分钟数
        verbose: 是否输出详细日志

    Returns:
        交易字典列表（可能为空）
    """
    if not os.path.exists(pdf_path):
        log.error("文件不存在: %s", pdf_path)
        return []

    start_time = time.time()
    max_timeout = timeout_minutes * 60
    pdf_name = os.path.basename(pdf_path)

    with tempfile.TemporaryDirectory(prefix="boc_pdf2csv_") as tmpdir:
        # 阶段一：PDF → 图片
        image_paths = pdf_to_images(pdf_path, scale=scale, output_dir=tmpdir)
        if not image_paths:
            log.warning("PDF 渲染无输出: %s", pdf_path)
            return []

        # 阶段二：图片 → OCR → 结构化
        warmup_engine()

        def _page_key(p: str) -> int:
            m = re.search(r'p(\d+)\.png$', p)
            return int(m.group(1)) if m else 0

        sorted_paths = sorted(image_paths, key=_page_key)
        total_pages = len(sorted_paths)

        all_transactions: List[Dict[str, Any]] = []
        stem = os.path.splitext(pdf_name)[0]

        for page_num, img_path in enumerate(sorted_paths):
            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                tqdm.write(f"⏰ 超时 {timeout_minutes} 分钟，已处理 {page_num}/{total_pages} 页")
                break

            try:
                items = process_image(img_path)
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
) -> str:
    """单个 PDF → CSV 完整流水线

    内部使用临时目录存储中间图片，处理完后自动清理。

    Args:
        pdf_path: PDF 文件路径
        output_path: 输出 CSV 路径（不指定则只返回字符串不写文件）
        scale: 渲染缩放倍率
        timeout_minutes: 单 PDF 超时分钟数
        verbose: 是否输出详细日志

    Returns:
        CSV 内容字符串

    Raises:
        FileNotFoundError: PDF 文件不存在
        RuntimeError: 渲染失败
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    start_time = time.time()
    transactions = _pdf_to_transactions(pdf_path, scale, timeout_minutes, verbose)

    elapsed = time.time() - start_time
    log.info("处理完成: %d 条交易, 耗时 %.1fs", len(transactions), elapsed)

    if not transactions:
        return ""

    return write_csv(transactions, output_path)


def process_folder(
    folder_path: str,
    output_path: str = "output.csv",
    scale: float = 3.0,
    timeout_minutes: int = 60,
    verbose: bool = False,
) -> str:
    """批量处理文件夹内所有 PDF，合并输出单个 CSV

    处理流程:
      1. 扫描文件夹中所有 .pdf 文件
      2. 逐个 PDF 调用 OCR 管线
      3. 合并所有交易记录
      4. 去重（按日期+金额+对方账户名）
      5. 按日期+时间排序
      6. 写出单个 CSV

    Args:
        folder_path: 包含 PDF 文件的文件夹路径
        output_path: 输出 CSV 文件路径（默认: output.csv）
        scale: 渲染缩放倍率
        timeout_minutes: 单个 PDF 超时分钟数
        verbose: 是否输出详细日志

    Returns:
        CSV 内容字符串

    Raises:
        NotADirectoryError: 输入路径非目录
        FileNotFoundError: 未找到 PDF 文件
        RuntimeError: 无交易记录
    """
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"输入路径不存在或非目录: {folder_path}")

    # 扫描 PDF 文件
    pdf_files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".pdf")
    ])

    if not pdf_files:
        raise FileNotFoundError(f"未找到 PDF 文件: {folder_path}")

    log.info("扫描到 %d 个 PDF 文件", len(pdf_files))
    if verbose:
        log.info("PDF 列表: %s", [os.path.basename(p) for p in pdf_files])

    all_transactions: List[Dict[str, Any]] = []
    failed_count = 0

    with tqdm(total=len(pdf_files), desc="处理 PDF", unit="个") as pbar:
        for i, pdf_path in enumerate(pdf_files):
            pdf_name = os.path.basename(pdf_path)
            pbar.set_postfix_str(pdf_name)

            try:
                transactions = _pdf_to_transactions(pdf_path, scale, timeout_minutes, verbose)
                all_transactions.extend(transactions)
                if verbose:
                    tqdm.write(f"  [{i + 1}/{len(pdf_files)}] {pdf_name} → {len(transactions)} 条交易")
            except Exception as e:
                log.error("处理失败: %s — %s", pdf_name, e)
                failed_count += 1
                if verbose:
                    tqdm.write(f"  [{i + 1}/{len(pdf_files)}] {pdf_name} 失败: {e}")

    if not all_transactions:
        if failed_count > 0:
            raise RuntimeError(f"处理失败: {failed_count}/{len(pdf_files)} 个 PDF 处理出错，且无有效交易记录")
        raise RuntimeError("未提取到任何交易记录")

    # 去重（按日期 + 金额 + 对方账户名）
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for t in all_transactions:
        key = (t.get("date"), t.get("amount"), t.get("counterparty"))
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    if verbose:
        log.info("去重: %d → %d 条交易", len(all_transactions), len(deduped))

    # 按日期 + 时间排序
    deduped.sort(key=lambda t: (t.get("date", ""), t.get("time", "")))

    # 写出 CSV
    csv_content = write_csv(deduped, output_path)
    log.info("合并输出: %d 条交易 → %s", len(deduped), output_path)
    return csv_content
