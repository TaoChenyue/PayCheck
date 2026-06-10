"""PDF → 图片渲染 + 表格检测裁剪模块

功能:
  1. 用 PyMuPDF 将 PDF 页面渲染为 PIL Image
  2. 亮度分析法检测表格边界并裁剪
  3. pdf_to_images(): 批量渲染 PDF 所有页为裁剪后 PNG 文件

用法:
    uv run python -m paycheck.ocr.pdf_render <pdf_path> --scale 3.0
"""

import logging
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Optional

import fitz
from PIL import Image
from tqdm import tqdm

from paycheck.ocr.layouts.base import find_table_bounds

log = logging.getLogger("paycheck.pdf_render")


def render_page_cropped(doc: fitz.Document, page_num: int, scale: float = 3.0) -> Image.Image:
    """将 PDF 指定页渲染为裁剪后 PIL Image（内存操作）

    Args:
        doc: fitz.Document 对象
        page_num: 页码（0-indexed）
        scale: 渲染倍率
    Returns:
        PIL.Image (RGB, 已裁剪到表格区域)
    """
    page = doc[page_num]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # 表格边界检测并裁剪
    top, bottom, left, right = find_table_bounds(img)
    cropped = img.crop((left, top, right, bottom))
    return cropped


# =========================================================================
# 多进程 PDF → 图片
# =========================================================================


def _render_worker(args) -> str:
    """子进程：渲染单页 PDF → 裁剪 → 存 PNG"""
    pdf_path, page_num, scale, output_dir = args

    import fitz
    doc = fitz.open(pdf_path)
    try:
        pil_img = render_page_cropped(doc, page_num, scale)
    finally:
        doc.close()

    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    page_dir = os.path.join(output_dir, stem)
    os.makedirs(page_dir, exist_ok=True)
    out_path = os.path.join(page_dir, f"p{page_num}.png")
    pil_img.save(out_path, "PNG")
    return out_path


def pdf_to_images(
    pdf_path: str,
    scale: float = 3.0,
    output_dir: Optional[str] = None,
    max_workers: Optional[int] = None,
) -> List[str]:
    """将 PDF 所有页渲染为裁剪后 PNG 图片文件（多进程并行）

    每页保存为 {pdf_stem}/p{page_num}.png。
    图片自带表格裁剪，可直接用于 OCR。

    Args:
        pdf_path: PDF 文件路径
        scale: 渲染倍率（默认 3.0，与 layout base_scale 一致）
        output_dir: 输出目录（默认 PDF 所在目录）
        max_workers: 并行进程数

    Returns:
        图片文件路径列表（按页码排序）
    """
    if not os.path.exists(pdf_path):
        log.error("文件不存在: %s", pdf_path)
        return []

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if total_pages == 0:
        log.warning("PDF 为空: %s", pdf_path)
        return []

    out_dir = output_dir or os.path.dirname(pdf_path) or tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    page_dir = os.path.join(out_dir, stem)
    os.makedirs(page_dir, exist_ok=True)

    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, 10)
    args_list = [(pdf_path, i, scale, out_dir) for i in range(total_pages)]
    n_workers = min(max_workers, total_pages)

    results: List[str] = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_render_worker, a): i for i, a in enumerate(args_list)}
        with tqdm(total=total_pages, desc=f"  {stem}", unit="页", leave=False) as pbar:
            for future in as_completed(futures):
                try:
                    path = future.result()
                    results.append(path)
                    pbar.update(1)
                except Exception as e:
                    log.error("第 %d 页渲染失败: %s", futures[future] + 1, e)

    # 按页码排序
    results.sort(key=lambda p: int(os.path.basename(p)[1:].replace(".png", "")))
    return results
