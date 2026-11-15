"""boc_pdf2csv: 中国银行 PDF 对账单 → CSV 转换工具

PDF/OCR 依赖为可选 extras（`pdf`）：包本身在未安装 extras 时也可导入，
调用 process_pdf / process_folder 时才检查依赖并抛出
MissingPdfDependency（附 `uv sync --extra pdf` 安装提示）。
"""
__version__ = "1.1.0"

__all__ = ["process_pdf", "process_folder", "FolderResult", "__version__"]


def __getattr__(name):
    """惰性暴露公开 API：避免 `import boc_pdf2csv` 就拉起 PDF 链路依赖。"""
    if name in ("process_pdf", "process_folder", "FolderResult"):
        from boc_pdf2csv import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
