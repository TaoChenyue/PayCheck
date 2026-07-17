"""导入面板 — PDF→CSV 转换 + 数据源选择 + 导入编配。"""

import logging
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox,
)
from PySide6.QtCore import Qt, Signal

from paycheck.gui.import_worker import ImportWorker
from paycheck.gui.pdf_worker import Pdf2CsvWorker
from paycheck.core.constants import (
    FIELD_TIME, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_COUNTERPARTY,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK,
    BANK_COL_DATE, BANK_COL_CHANNEL, BANK_COL_MEMO, BANK_COL_TX_NAME,
)

try:
    from paycheck.ocr.layouts import list_layouts
except ImportError:
    list_layouts = lambda: ["boc"]

log = logging.getLogger("paycheck.gui")


class ImportPanel(QWidget):
    """导入页：PDF→CSV 转换 + 多平台数据源选择 + 导入操作。

    通过 Qt Signal 与 MainWindow 通信：
    - import_finished: 导入成功，MainWindow 应重新加载数据
    """

    import_finished = Signal()

    def __init__(self, bank_type_combo: QComboBox, parent=None):
        super().__init__(parent)

        self._wechat_files = []
        self._alipay_files = []
        self._bank_files = []
        self._pdf_files = []
        self._bank_type_combo = bank_type_combo

        self._pdf_worker = None
        self._import_worker = None

        layout = QVBoxLayout(self)

        # ── PDF→CSV ──
        pdf_group = QGroupBox("PDF → CSV（可选）")
        pdf_layout = QVBoxLayout(pdf_group)

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("PDF:"))
        self._pdf_path = QLineEdit()
        self._pdf_path.setReadOnly(True)
        self._pdf_path.setPlaceholderText("选择银行流水 PDF 文件...")
        row0.addWidget(self._pdf_path, 1)
        btn_pdf_browse = QPushButton("浏览...")
        btn_pdf_browse.clicked.connect(self._on_browse_pdf)
        row0.addWidget(btn_pdf_browse)
        pdf_layout.addLayout(row0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("银行:"))
        self._layout_combo = QComboBox()
        for name in list_layouts():
            self._layout_combo.addItem(name.upper(), name)
        row1.addWidget(self._layout_combo)
        row1.addSpacing(16)
        btn_convert = QPushButton("开始转换 PDF→CSV")
        btn_convert.clicked.connect(self._on_pdf2csv)
        row1.addWidget(btn_convert)
        self._pdf_progress = QProgressBar()
        self._pdf_progress.setVisible(False)
        self._pdf_progress.setMaximum(100)
        row1.addWidget(self._pdf_progress)
        self._pdf_status = QLabel("")
        row1.addWidget(self._pdf_status)
        row1.addStretch()
        pdf_layout.addLayout(row1)

        layout.addWidget(pdf_group)

        # ── 数据源 ──
        import_group = QGroupBox("数据源")
        import_layout = QVBoxLayout(import_group)

        for label, attr, filt in [
            ("微信 (.xlsx):", "_wechat_files", "Excel (*.xlsx)"),
            ("支付宝 (.csv):", "_alipay_files", "CSV (*.csv)"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            le = QLineEdit()
            le.setReadOnly(True)
            le.setPlaceholderText("选择文件...")
            setattr(self, f"_{attr}_edit", le)
            row.addWidget(le, 1)
            btn = QPushButton("浏览...")
            btn.clicked.connect(lambda checked, a=attr, f=filt: self._browse_files(a, f))
            row.addWidget(btn)
            import_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("银行 (.csv):"))
        self._bank_csv_edit = QLineEdit()
        self._bank_csv_edit.setReadOnly(True)
        self._bank_csv_edit.setPlaceholderText("选择文件...")
        row.addWidget(self._bank_csv_edit, 1)
        btn = QPushButton("浏览...")
        btn.clicked.connect(lambda: self._browse_files("_bank_files", "CSV (*.csv)"))
        row.addWidget(btn)
        row.addWidget(QLabel("类型:"))
        row.addWidget(self._bank_type_combo)
        import_layout.addLayout(row)

        btn_import = QPushButton("导入并合并")
        btn_import.clicked.connect(self._on_import)
        import_layout.addWidget(btn_import)

        self._import_progress = QProgressBar()
        self._import_progress.setVisible(False)
        self._import_progress.setRange(0, 0)
        import_layout.addWidget(self._import_progress)

        self._import_status = QLabel("")
        import_layout.addWidget(self._import_status)

        layout.addWidget(import_group)
        layout.addStretch()

    # ── 文件选择 ──

    def _browse_files(self, attr: str, filt: str):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", filt)
        if files:
            setattr(self, attr, list(files))
            edit = getattr(self, f"_{attr}_edit")
            edit.setText(f"已选 {len(files)} 个文件")

    def _on_browse_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择银行PDF", "", "PDF (*.pdf)")
        if files:
            self._pdf_files = list(files)
            self._pdf_path.setText(f"已选 {len(files)} 个文件")

    # ── 导入 ──

    def _on_import(self):
        if not self._wechat_files and not self._alipay_files and not self._bank_files:
            QMessageBox.warning(self, "提示", "请至少选择一个账单文件")
            return

        self._import_progress.setVisible(True)
        self._import_status.setText("解析中...")

        self._import_worker = ImportWorker(self._wechat_files, self._alipay_files, self._bank_files)
        self._import_worker.progress.connect(lambda m: self._import_status.setText(m))
        self._import_worker.finished.connect(self._on_import_done)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_import_done(self, added: int, skipped: int):
        self._import_progress.setVisible(False)
        msg = f"✓ 新增 {added} 条"
        if skipped > 0:
            msg += f"（跳过 {skipped} 条重复）"
        self._import_status.setText(msg)
        self.import_finished.emit()

    def _on_import_error(self, msg: str):
        self._import_progress.setVisible(False)
        self._import_status.setText(f"✗ {msg}")
        QMessageBox.critical(self, "导入失败", msg)

    # ── PDF→CSV ──

    def _on_pdf2csv(self):
        if not self._pdf_files:
            QMessageBox.warning(self, "提示", "请先选择银行 PDF 文件")
            return

        layout_name = self._layout_combo.currentData()
        self._pdf_status.setText("转换中...")
        self._pdf_progress.setVisible(True)
        self._pdf_progress.setValue(0)

        self._pdf_worker = Pdf2CsvWorker(self._pdf_files, layout_name)
        self._pdf_worker.progress_val.connect(self._pdf_progress.setValue)
        self._pdf_worker.progress_text.connect(self._pdf_status.setText)
        self._pdf_worker.finished.connect(self._on_pdf2csv_done)
        self._pdf_worker.error.connect(self._on_pdf2csv_error)
        self._pdf_worker.start()

    def _on_pdf2csv_done(self, csv_name: str):
        self._pdf_status.setText(f"输出: {csv_name}")
        self._pdf_progress.setVisible(False)
        self._bank_files.append(os.path.join(
            os.path.dirname(self._pdf_files[0]), csv_name))
        self._bank_csv_edit.setText(f"已选 {len(self._bank_files)} 个文件")

    def _on_pdf2csv_error(self, msg: str):
        self._pdf_status.setText(f"失败: {msg}")
        self._pdf_progress.setVisible(False)

    @property
    def status_label(self) -> QLabel:
        """暴露状态标签，供 MainWindow 在底部栏复用。"""
        return self._import_status
