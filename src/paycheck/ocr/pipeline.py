"""PDF → CSV 管线编排（全内存，零中间文件）

流程: PDF → 逐页渲染 → 表格裁剪 → PaddleOCR → layout 结构化 → CSV
"""

import io
import os
import sys
import time
from typing import Optional

import cv2
import numpy as np

import fitz

from paycheck.ocr.pdf_render import render_page_cropped
from paycheck.ocr.engine import process_image as ocr_process
from paycheck.ocr.layouts import get_layout


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
        print(f"文件不存在: {pdf_path}", file=sys.stderr)
        return 1

    layout = get_layout(layout_name)
    if layout is None:
        print(f"不支持的银行布局: {layout_name}", file=sys.stderr)
        return 1

    # 打开 PDF
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"PDF: {os.path.basename(pdf_path)} ({total_pages} 页, {scale}x)", file=sys.stderr)

    exit_code = 0
    csv_buf = io.StringIO()
    total_txns = 0
    errors = 0

    # CSV 表头
    csv_buf.write("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name\n")

    try:
        for page_num in range(total_pages):
            elapsed = time.time() - start_time
            remaining = timeout_minutes * 60 - elapsed
            if remaining < 30:
                print(f"\n超时逼近，已处理 {page_num}/{total_pages} 页", file=sys.stderr)
                break

            print(f"\r  [{page_num+1}/{total_pages}]... ", file=sys.stderr, end="")

            try:
                # 内存渲染 + 裁剪
                pil_img = render_page_cropped(doc, page_num, scale)

                # PIL → numpy BGR (PaddleOCR 需要)
                img_rgb = np.array(pil_img)
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

                # OCR 识别 → items
                page_timeout = max(30, remaining + 30)
                items = ocr_process(img_bgr, timeout_sec=page_timeout)

                if not items:
                    print("0 条", file=sys.stderr)
                    continue

                # Layout 结构化: items → rows → transactions
                rows = layout.group_rows(items, scale)
                txn_dicts = layout.to_transactions(rows)

                # 写出 CSV
                for t in txn_dicts:
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

                total_txns += len(txn_dicts)
                print(f"{len(txn_dicts)} 条", file=sys.stderr)

            except Exception as e:
                errors += 1
                print(f"❌ {e}", file=sys.stderr)

    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        doc.close()

    csv_content = csv_buf.getvalue()
    csv_buf.close()

    if total_txns > 0:
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(csv_content)
            print(f"已写入: {output_path}", file=sys.stderr)
        else:
            sys.stdout.write(csv_content)
    else:
        print("OCR 未提取到任何内容", file=sys.stderr)
        if not csv_content.strip():
            exit_code = 1

    elapsed = time.time() - start_time
    status = f"总耗时 {elapsed:.0f}s, {total_txns} 条交易"
    if errors:
        status += f", {errors} 页异常"
    print(status, file=sys.stderr)
    return exit_code


def _esc_csv(s) -> str:
    """CSV 字段转义"""
    if s is None:
        return ""
    s = str(s)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s
