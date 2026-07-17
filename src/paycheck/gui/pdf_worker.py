"""PDF→CSV 后台线程 — OCR 识别银行流水 PDF 并输出 CSV 文件。"""

import csv
import logging
import os

from PySide6.QtCore import QThread, Signal

from paycheck.core.constants import (
    FIELD_TIME, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_COUNTERPARTY,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK,
    BANK_COL_DATE, BANK_COL_CHANNEL, BANK_COL_MEMO, BANK_COL_TX_NAME,
)

log = logging.getLogger("paycheck.gui")

CSV_HEADER = [
    BANK_COL_DATE, FIELD_TIME, FIELD_TX_TYPE, FIELD_AMOUNT, FIELD_COUNTERPARTY,
    BANK_COL_CHANNEL, FIELD_BALANCE, BANK_COL_MEMO, BANK_COL_TX_NAME, FIELD_CURRENCY,
    FIELD_BRANCH, FIELD_CP_ACCOUNT, FIELD_CP_BANK,
]


class Pdf2CsvWorker(QThread):
    """PDF→CSV 后台线程，通过信号更新 UI。"""

    progress_val = Signal(int)
    progress_text = Signal(str)
    finished = Signal(str)   # csv_name
    error = Signal(str)

    def __init__(self, pdf_paths: list, layout_name: str):
        super().__init__()
        self._pdf_paths = pdf_paths
        self._layout_name = layout_name

    def run(self):
        try:
            import fitz
            import cv2
            import numpy as np
            from PIL import Image
            from paycheck.ocr.pdf_render import render_page_cropped
            from paycheck.ocr.engine import process_image, warmup_engine
            from paycheck.ocr.layouts import get_layout

            layout = get_layout(self._layout_name)
            if layout is None:
                raise ValueError(f"不支持的银行类型: {self._layout_name}")

            total_pages = 0
            for p in self._pdf_paths:
                d = fitz.open(p)
                total_pages += len(d)
                d.close()

            warmup_engine()
            log.info("OCR 引擎就绪，共 %d 页，开始处理...", total_pages)

            all_dicts = []
            done = 0
            for pdf_path in self._pdf_paths:
                doc = fitz.open(pdf_path)
                for page_num in range(len(doc)):
                    pil_img = render_page_cropped(doc, page_num, scale=layout.base_scale)
                    arr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
                    items = process_image(arr)
                    if items:
                        rows = layout.group_rows(items, scale=layout.base_scale)
                        all_dicts.extend(layout.to_transactions(rows))
                    done += 1
                    pct = int(done / total_pages * 100)
                    log.info("OCR %d/%d (%d%%)", done, total_pages, pct)
                    self.progress_val.emit(pct)
                    self.progress_text.emit(f"{done}/{total_pages} 页")
                doc.close()

            if not all_dicts:
                raise RuntimeError("OCR 未识别到任何交易记录")

            out_dir = os.path.dirname(self._pdf_paths[0]) or "."
            csv_name = os.path.splitext(os.path.basename(self._pdf_paths[0]))[0] + ".csv"
            csv_path = os.path.join(out_dir, csv_name)

            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(CSV_HEADER)
                for t in all_dicts:
                    w.writerow([t.get(k, "") for k in CSV_HEADER])

            self.finished.emit(csv_name)
        except Exception as e:
            log.exception("PDF 转换失败")
            self.error.emit(str(e))
