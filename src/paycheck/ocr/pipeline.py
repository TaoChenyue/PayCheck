"""PDF / 图片 → CSV 管线编排

管线:
  pdf_to_images() → images_to_csv()   # 两阶段
  pdf_to_csv()    ← 两步组合（临时图片）  # 快捷方式
"""

import io
import logging
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from paycheck.ocr.layouts import get_layout

log = logging.getLogger("paycheck.pipeline")


# =========================================================================
# 阶段二：图片 → OCR → CSV
# =========================================================================
def _image_worker(args: Tuple[int, str, str, float]) -> Tuple[int, List[Dict[str, Any]]]:
    """在子进程中处理单张页面图片（OCR + layout 结构化）。

    每个 worker 进程有自己独立的 PaddleOCR 实例（_get_engine 缓存）。

    Args:
        args: (page_num, image_path, layout_name, scale)

    Returns:
        (page_num, list[交易字典])
    """
    page_num, image_path, layout_name, scale = args

    import cv2
    import numpy as np
    from paycheck.ocr.engine import process_image

    # 加载图片
    img = cv2.imread(image_path)
    if img is None:
        log.warning("无法读取图片: %s", image_path)
        return page_num, []

    # OCR
    items = process_image(img)

    if not items:
        return page_num, []

    # Layout 结构化
    layout = get_layout(layout_name)
    if layout is None:
        raise ValueError(f"不支持的银行布局: {layout_name}")
    rows = layout.group_rows(items, scale)
    txn_dicts = layout.to_transactions(rows)
    return page_num, txn_dicts


def _write_csv(
    page_results: Dict[int, List[Dict[str, Any]]],
    total_pages: int,
    output_path: Optional[str] = None,
) -> str:
    """将按页分组的交易记录写出为 CSV 字符串，可选写文件"""
    csv_buf = io.StringIO()
    csv_buf.write("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank\n")
    for p in range(total_pages):
        for t in page_results.get(p, []):
            row = [
                _esc_csv(t.get("date", "")),
                _esc_csv(t.get("time", "")),
                _esc_csv(t.get("tx_type", "")),
                f"{t['amount']:.2f}" if isinstance(t.get("amount"), (int, float)) else "",
                _esc_csv(t.get("counterparty", "")),
                _esc_csv(t.get("channel", "")),
                f"{float(t['balance']):.2f}" if isinstance(t.get("balance"), (int, float)) else "0.00",
                _esc_csv(t.get("memo", "")),
                _esc_csv(t.get("tx_name", "")),
                _esc_csv(t.get("currency", "")),
                _esc_csv(t.get("branch", "")),
                _esc_csv(t.get("cp_account", "")),
                _esc_csv(t.get("cp_bank", "")),
            ]
            csv_buf.write(",".join(row) + "\n")

    csv_content = csv_buf.getvalue()
    csv_buf.close()

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        log.info("已写入: %s", output_path)

    return csv_content


def images_to_csv(
    image_paths: List[str],
    layout_name: str,
    scale: float = 3.0,
    output_path: Optional[str] = None,
    timeout_minutes: int = 120,
    preview: bool = False,
) -> int:
    """图片文件列表 → OCR → CSV

    Args:
        image_paths: 页面图片路径列表（已排序）
        layout_name: 银行布局名称（如 "boc"）
        scale: 渲染倍率（需与 pdf2image 时一致）
        output_path: 输出 CSV 路径（不指定则输出到 stdout）
        timeout_minutes: 超时分钟数
        preview: 预览模式，不写文件，结果输出到终端

    Returns:
        0 成功, 1 失败
    """
    start_time = time.time()

    if not image_paths:
        log.error("图片列表为空")
        return 1

    if get_layout(layout_name) is None:
        log.error("不支持的银行布局: %s", layout_name)
        return 1

    total_pages = len(image_paths)
    log.info("OCR开始: %d 张图片, 布局=%s, 缩放=%.1f, 超时=%d分钟", total_pages, layout_name, scale, timeout_minutes)
    desc = os.path.basename(os.path.dirname(image_paths[0])) if len(image_paths) > 1 else os.path.basename(image_paths[0])

    # 提取页码（从文件名 _p{N}.png）
    def _page_key(p: str) -> int:
        m = re.search(r'_p(\d+)\.png$', p)
        return int(m.group(1)) if m else 0

    sorted_paths = sorted(image_paths, key=_page_key)

    page_results: Dict[int, List[Dict[str, Any]]] = {}
    exit_code = 0
    error_info: Optional[Tuple[int, str]] = None
    total_txns = 0
    max_timeout = timeout_minutes * 60

    # 预加载 OCR 模型，避免进度条卡在 0%
    from paycheck.ocr.engine import warmup_engine
    warmup_engine()

    with tqdm(total=total_pages, desc=desc, unit="页") as pbar:
        for page_num in range(total_pages):
            # 检查总超时
            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                tqdm.write(f"⏰ 超时 {timeout_minutes} 分钟，已处理 {len(page_results)}/{total_pages} 页")
                error_info = (0, f"总处理时间超过 {timeout_minutes} 分钟")
                break

            try:
                result_page, txn_dicts = _image_worker(
                    (page_num, sorted_paths[page_num], layout_name, scale)
                )
                page_results[result_page] = txn_dicts
                total_txns += len(txn_dicts)
                pbar.update(1)
            except Exception as e:
                error_info = (page_num + 1, str(e))
                log.error("第 %d 页处理失败: %s", page_num + 1, e)
                break

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

    # 写出 CSV（预览模式 → 终端输出）
    if exit_code == 0:
        log.info("OCR识别: %d 条交易", total_txns)
        if preview:
            print(_write_csv(page_results, total_pages))
        else:
            _write_csv(page_results, total_pages, output_path)

    elapsed = time.time() - start_time
    log.info("总耗时 %ds, %d 条交易", elapsed, total_txns)
    return exit_code


# =========================================================================
# 阶段一 + 阶段二组合：PDF → CSV（两阶段，用临时图片中转）
# =========================================================================


def pdf_to_csv(
    pdf_path: str,
    layout_name: str,
    scale: float = 3.0,
    output_path: Optional[str] = None,
    timeout_minutes: int = 60,
) -> int:
    """PDF → CSV 完整流水线（组合 pdf_to_images + images_to_csv）

    内部使用临时目录存储中间图片，处理完后自动清理。

    Args:
        pdf_path: PDF 文件路径
        layout_name: 银行布局名称（如 "boc"）
        scale: 渲染缩放倍率
        output_path: 输出 CSV 路径
        timeout_minutes: 超时分钟数

    Returns:
        0 成功, 1 失败
    """
    if not os.path.exists(pdf_path):
        log.error("文件不存在: %s", pdf_path)
        return 1

    from paycheck.ocr.pdf_render import pdf_to_images

    with tempfile.TemporaryDirectory(prefix="paycheck_pdf_") as tmpdir:
        # 阶段一：PDF → 图片
        log.info("渲染 PDF → 图片...")
        image_paths = pdf_to_images(pdf_path, scale=scale, output_dir=tmpdir)

        if not image_paths:
            log.error("PDF 渲染失败: %s", pdf_path)
            return 1

        # 阶段二：图片 → CSV
        log.info("OCR %d 页...", len(image_paths))
        return images_to_csv(
            image_paths,
            layout_name,
            scale=scale,
            output_path=output_path,
            timeout_minutes=timeout_minutes,
        )


def _esc_csv(s) -> str:
    """CSV 字段转义"""
    if s is None:
        return ""
    s = str(s)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s
