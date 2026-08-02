"""boc-pdf2csv: 中国银行 PDF 对账单 → CSV 转换工具"""
__version__ = "1.0.0"

from boc_pdf2csv.pipeline import process_folder, process_pdf

__all__ = ["process_pdf", "process_folder", "__version__"]
