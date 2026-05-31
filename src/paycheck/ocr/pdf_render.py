"""PDF → 图片渲染 + 表格检测裁剪模块

功能:
  1. 用 PyMuPDF 将 PDF 页面渲染为 PIL Image
  2. 亮度分析法检测表格边界并裁剪

用法:
    uv run python -m paycheck.ocr.pdf_render <pdf_path> --scale 3.0
"""

import fitz
from PIL import Image

from paycheck.ocr.layouts.base import find_table_bounds


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
