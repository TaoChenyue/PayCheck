"""PDF → CSV 管线编排（全内存，零中间文件）

流程: PDF → 逐页渲染 → 表格裁剪 → PaddleOCR → layout 结构化 → CSV
支持多进程并行处理，任意页出错即取消所有剩余任务。
"""

import concurrent.futures
import io
import logging
import multiprocessing
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from paycheck.ocr.layouts import get_layout

log = logging.getLogger("paycheck.pipeline")


def _page_worker(args: Tuple[int, str, str, float]) -> Tuple[int, List[Dict[str, Any]]]:
    """在子进程中处理单页 PDF。
    每个 worker 进程有自己独立的 PaddleOCR 实例（_get_engine 缓存）。

    Args:
        args: (page_num, pdf_path, layout_name, scale)

    Returns:
        (page_num, list[交易字典])
    """
    page_num, pdf_path, layout_name, scale = args

    import cv2
    import fitz
    import numpy as np
    from paycheck.ocr.pdf_render import render_page_cropped
    from paycheck.ocr.engine import process_image

    # 渲染
    doc = fitz.open(pdf_path)
    try:
        pil_img = render_page_cropped(doc, page_num, scale)
    finally:
        doc.close()

    # OCR
    img_rgb = np.array(pil_img)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    items = process_image(img_bgr)

    if not items:
        return page_num, []

    # Layout 结构化
    layout = get_layout(layout_name)
    if layout is None:
        raise ValueError(f"不支持的银行布局: {layout_name}")
    rows = layout.group_rows(items, scale)
    txn_dicts = layout.to_transactions(rows)
    return page_num, txn_dicts


def pdf_to_csv(
    pdf_path: str,
    layout_name: str,
    scale: float = 3.0,
    output_path: Optional[str] = None,
    timeout_minutes: int = 60,
) -> int:
    """PDF → CSV 完整流水线

    Args:
        pdf_path: PDF 文件路径
        layout_name: 银行布局名称（如 "boc"），用于匹配 layout
        scale: 渲染缩放倍率
        output_path: 输出 CSV 路径
        timeout_minutes: 超时分钟数
    Returns:
        0 成功, 1 失败
    """
    start_time = time.time()

    if not os.path.exists(pdf_path):
        log.error("文件不存在: %s", pdf_path)
        return 1

    if get_layout(layout_name) is None:
        log.error("不支持的银行布局: %s", layout_name)
        return 1

    # 读取 PDF 确定总页数
    import fitz
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if total_pages == 0:
        log.warning("PDF 为空: %s", pdf_path)
        return 1

    desc = os.path.basename(pdf_path)
    n_workers = min(multiprocessing.cpu_count(), 4)

    page_args = [(i, pdf_path, layout_name, scale) for i in range(total_pages)]

    page_results: Dict[int, List[Dict[str, Any]]] = {}
    exit_code = 0
    error_info: Optional[Tuple[int, str]] = None
    total_txns = 0
    max_timeout = timeout_minutes * 60

    with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(_page_worker, arg): i
            for i, arg in enumerate(page_args)
        }

        try:
            with tqdm(total=total_pages, desc=desc, unit="页") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    # 检查总超时
                    elapsed = time.time() - start_time
                    if elapsed >= max_timeout:
                        tqdm.write(f"⏰ 超时 {timeout_minutes} 分钟，已处理 {len(page_results)}/{total_pages} 页")
                        error_info = (0, f"总处理时间超过 {timeout_minutes} 分钟")
                        break

                    page_num = futures[future]
                    try:
                        result_page, txn_dicts = future.result()
                        page_results[result_page] = txn_dicts
                        total_txns += len(txn_dicts)
                        pbar.update(1)
                    except Exception as e:
                        error_info = (page_num + 1, str(e))
                        log.error("第 %d 页处理失败: %s", page_num + 1, e)
                        break

        except KeyboardInterrupt:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

        # 出错或超时 → 取消所有剩余任务
        if error_info is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    # --- 结果处理 ---
    if error_info is not None:
        err_page, err_reason = error_info
        if err_page:
            log.error("OCR 处理失败: 第 %d 页 — %s", err_page, err_reason)
        else:
            log.error("OCR 处理失败: %s", err_reason)
        exit_code = 1

    if exit_code == 0 and total_txns == 0:
        log.warning("OCR 未提取到任何内容")
        return 1

    # 按页码顺序写出 CSV
    if exit_code == 0:
        csv_buf = io.StringIO()
        csv_buf.write("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name\n")
        for p in range(total_pages):
            for t in page_results.get(p, []):
                row = [
                    _esc_csv(t.get("date", "")),
                    _esc_csv(t.get("time", "")),
                    _esc_csv(t.get("tx_type", "")),
                    f"{t['amount']:.2f}" if isinstance(t.get("amount"), (int, float)) else "",
                    _esc_csv(t.get("counterparty", "")),
                    _esc_csv(t.get("channel", "")),
                    f"{t['balance']:.2f}" if isinstance(t.get("balance"), (int, float)) else "",
                    _esc_csv(t.get("memo", "")),
                    _esc_csv(t.get("tx_name", "")),
                ]
                csv_buf.write(",".join(row) + "\n")

        csv_content = csv_buf.getvalue()
        csv_buf.close()

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(csv_content)
            log.info("已写入: %s", output_path)
        else:
            sys.stdout.write(csv_content)

    elapsed = time.time() - start_time
    log.info("总耗时 %ds, %d 条交易", elapsed, total_txns)
    return exit_code


def _esc_csv(s) -> str:
    """CSV 字段转义"""
    if s is None:
        return ""
    s = str(s)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s
