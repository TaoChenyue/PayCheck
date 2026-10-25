"""现有 boc-pdf2csv 工具回归：包导入与版本不受工作台改动影响"""

from __future__ import annotations


def test_boc_pdf2csv_importable():
    import boc_pdf2csv

    assert boc_pdf2csv.__version__ == "1.1.0"


def test_boc_pdf2csv_public_api():
    from boc_pdf2csv import FolderResult, process_folder, process_pdf

    assert callable(process_pdf)
    assert callable(process_folder)
    assert FolderResult is not None
