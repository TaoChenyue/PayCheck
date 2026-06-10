"""PySide6 主窗口 — PDF→CSV + 导入 + 分渠道表格 + 分页"""

import logging
import os
from typing import List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QAbstractItemView, QFrame, QTabWidget,
    QDateEdit,
)
from PySide6.QtCore import Qt, QThread, Signal, QDate
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt, QThread, Signal

from paycheck.ingest.parsers.wechat import parse_wechat_xlsx
from paycheck.ingest.parsers.alipay import parse_alipay_csv
from paycheck.ingest.parsers.boc import parse_boc_csv
from paycheck.storage import database as db

try:
    from paycheck.ocr.layouts import list_layouts
except ImportError:
    list_layouts = lambda: ["boc"]

log = logging.getLogger("paycheck.gui")

CHANNEL_COLUMNS = {
    "wechat": [
        ("time", "交易时间", 160), ("category", "交易类型", 90),
        ("counterparty", "交易对方", 130), ("description", "商品", 120),
        ("amount", "金额(元)", 100), ("tx_type", "收/支", 60),
        ("payment_method", "支付方式", 90),
    ],
    "alipay": [
        ("time", "交易时间", 160), ("category", "交易分类", 90),
        ("counterparty", "交易对方", 130), ("description", "商品说明", 120),
        ("amount", "金额", 100), ("tx_type", "收/支", 60),
        ("payment_method", "收/付款方式", 90),
    ],
    "bank": [
        ("time", "交易时间", 160), ("category", "交易名称", 100),
        ("counterparty", "对方账户名", 130), ("description", "附言", 100),
        ("amount", "金额", 100), ("tx_type", "收支类型", 60),
        ("payment_method", "渠道", 80), ("balance", "余额", 100),
        ("currency", "币别", 50), ("branch", "网点名称", 100),
        ("cp_account", "对方账号", 130), ("cp_bank", "对方开户行", 120),
    ],
}


class ImportWorker(QThread):
    """后台导入线程"""
    progress = Signal(str)
    finished = Signal(int, int)  # added, skipped
    error = Signal(str)

    def __init__(self, wechat_files, alipay_files, bank_files):
        super().__init__()
        self._wechat = wechat_files
        self._alipay = alipay_files
        self._bank = bank_files

    def run(self):
        try:
            transactions = []
            for f in self._wechat:
                self.progress.emit(f"解析微信: {os.path.basename(f)}")
                transactions.extend(parse_wechat_xlsx(f))
            for f in self._alipay:
                self.progress.emit(f"解析支付宝: {os.path.basename(f)}")
                transactions.extend(parse_alipay_csv(f))
            for f in self._bank:
                self.progress.emit(f"解析银行: {os.path.basename(f)}")
                transactions.extend(parse_boc_csv(f))

            if not transactions:
                self.error.emit("未解析到任何交易记录")
                return

            dicts = [{
                "platform": t.platform, "time": t.time,
                "category": t.category, "counterparty": t.counterparty,
                "amount": t.amount, "tx_type": t.tx_type,
                "payment_method": t.payment_method, "description": t.description,
                "balance": t.balance, "currency": t.currency,
                "branch": t.branch, "cp_account": t.cp_account,
                "cp_bank": t.cp_bank,
            } for t in transactions]

            added = db.insert_transactions(dicts)
            self.finished.emit(added, len(dicts) - added)
        except Exception as e:
            log.exception("导入失败")
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PayCheck - 个人账单统计")
        self.setMinimumSize(1000, 700)

        self._wechat_files = []
        self._alipay_files = []
        self._bank_files = []
        self._pdf_files = []
        self._all_transactions = []
        self._page_size = 50
        self._bank_type_combo = None  # _init_ui 中创建

        self._init_ui()
        self._sync_bank_tab_label()
        self._load_from_db()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)

        # 提前创建，防止后续代码依赖时未就绪
        layouts = list_layouts()
        self._bank_type_combo = QComboBox()
        for name in layouts:
            self._bank_type_combo.addItem(name.upper(), name)

        # ═══ PDF→CSV ═══
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

        # ═══ 数据源 ═══
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

        # 银行 CSV + 类型选择
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

        # ═══ 摘要 ═══
        summary_group = QGroupBox("摘要")
        summary_layout = QGridLayout(summary_group)
        self._summary_labels = {}
        card_names = ["总支出", "总收入", "月均支出", "月均收入",
                      "微信", "支付宝", "银行"]
        for i, name in enumerate(card_names):
            card = QGroupBox(name)
            card.setMinimumWidth(120)
            cl = QVBoxLayout(card)
            lbl = QLabel("-")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
            cl.addWidget(lbl)
            self._summary_labels[name] = lbl
            summary_layout.addWidget(card, i // 4, i % 4)
        layout.addWidget(summary_group)

        # ═══ 交易明细 ═══
        table_group = QGroupBox("交易明细（点击表头筛选）")
        table_layout = QVBoxLayout(table_group)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tables = {}
        self._page_labels = {}
        self._page_states = {"wechat": 0, "alipay": 0, "bank": 0}
        self._col_filters = {"wechat": {}, "alipay": {}, "bank": {}}
        self._filter_frames = {}

        channel_names = {"wechat": "微信", "alipay": "支付宝", "bank": "银行"}
        for ch_key, ch_name in channel_names.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

            # 筛选行（表格上方，每列适配控件类型）
            filter_frame = QFrame()
            filter_layout = QHBoxLayout(filter_frame)
            filter_layout.setContentsMargins(0, 0, 0, 0)
            filter_layout.setSpacing(2)
            tab_layout.addWidget(filter_frame)

            tbl = QTableWidget()
            tbl.setAlternatingRowColors(True)
            tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tbl.setSortingEnabled(True)
            tbl.horizontalHeader().setStretchLastSection(True)
            tab_layout.addWidget(tbl, 1)
            self._tables[ch_key] = tbl

            self._col_filters[ch_key] = {}
            self._filter_frames[ch_key] = filter_frame
            self._tables[ch_key] = tbl

            page_bar = QHBoxLayout()
            page_bar.addStretch()
            btn_p = QPushButton("<")
            btn_p.clicked.connect(lambda checked, k=ch_key: self._go_page(-1, k))
            page_bar.addWidget(btn_p)
            pl = QLabel("")
            page_bar.addWidget(pl)
            self._page_labels[ch_key] = pl
            btn_n = QPushButton(">")
            btn_n.clicked.connect(lambda checked, k=ch_key: self._go_page(1, k))
            page_bar.addWidget(btn_n)
            page_bar.addStretch()
            tab_layout.addLayout(page_bar)

            self._tabs.addTab(tab, ch_name)

        table_layout.addWidget(self._tabs, 1)
        layout.addWidget(table_group, 1)

        # ── 底部状态 ──
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

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

        self._bank_type = self._bank_type_combo.currentData()
        self._tabs.setTabText(2, self._bank_type.upper() if self._bank_type else "银行")

        self._worker = ImportWorker(self._wechat_files, self._alipay_files, self._bank_files)
        self._worker.progress.connect(lambda m: self._import_status.setText(m))
        self._worker.finished.connect(self._on_import_done)
        self._worker.error.connect(self._on_import_error)
        self._worker.start()

    def _on_import_done(self, added: int, skipped: int):
        self._import_progress.setVisible(False)
        msg = f"✓ 新增 {added} 条"
        if skipped > 0:
            msg += f"（跳过 {skipped} 条重复）"
        self._import_status.setText(msg)
        self._load_from_db()

    def _on_import_error(self, msg: str):
        self._import_progress.setVisible(False)
        self._import_status.setText(f"✗ {msg}")
        QMessageBox.critical(self, "导入失败", msg)

    # ── 数据加载 ──

    def _load_from_db(self):
        self._all_transactions = db.get_all_transactions()
        if self._all_transactions:
            s = db.get_summary()
            # 月均收入 = 总收入 / 有收入的月份数
            income_months = len(set(
                t["time"][:7] for t in self._all_transactions
                if t.get("tx_type") == "收入" and t.get("time")
            )) or 1
            monthly_income = round(s['total_income'] / income_months, 2)

            self._summary_labels["总支出"].setText(f"¥{s['total_expense']:,.2f}")
            self._summary_labels["总收入"].setText(f"¥{s['total_income']:,.2f}")
            self._summary_labels["月均支出"].setText(f"¥{s['monthly_avg']:,.2f}")
            self._summary_labels["月均收入"].setText(f"¥{monthly_income:,.2f}")
            self._summary_labels["微信"].setText(f"¥{s['wechat_total']:,.2f} / {s['wechat_count']}笔")
            self._summary_labels["支付宝"].setText(f"¥{s['alipay_total']:,.2f} / {s['alipay_count']}笔")
            self._summary_labels["银行"].setText(f"¥{s['bank_total']:,.2f} / {s['bank_count']}笔")
            self._status.setText(f"已存储 {s['total_count']} 笔交易")
        else:
            self._status.setText("请导入账单文件")

        self._render_all_tables()

    def _sync_bank_tab_label(self):
        if self._bank_type_combo is not None and self._bank_type_combo.count() > 0:
            name = self._bank_type_combo.currentData()
            self._tabs.setTabText(2, name.upper() if name else "银行")

    # ── 表格渲染 ──

    def _render_all_tables(self):
        for ch_key in ("wechat", "alipay", "bank"):
            self._page_states[ch_key] = 0
        self._render_current_tab()

    def _render_current_tab(self):
        idx = self._tabs.currentIndex()
        ch_key = ("wechat", "alipay", "bank")[idx] if 0 <= idx < 3 else "wechat"
        self._render_table(ch_key)

    def _on_tab_changed(self, _idx):
        if self._all_transactions:
            self._render_current_tab()

    def _on_col_filter(self, channel: str, col: int, text: str):
        text = text.strip()
        if text:
            self._col_filters[channel][col] = text
        else:
            self._col_filters[channel].pop(col, None)
        self._page_states[channel] = 0
        self._render_table(channel)

    def _apply_filters(self, transactions: list, channel: str) -> list:
        """应用该渠道的列筛选（含文本/范围/下拉）"""
        filters = self._col_filters.get(channel, {})
        if not filters:
            return transactions

        cols = CHANNEL_COLUMNS[channel]
        result = transactions

        for fkey, fval in filters.items():
            if isinstance(fkey, str) and fkey.endswith("_range"):
                col_idx = int(fkey.replace("_range", ""))
                key = cols[col_idx][0] if col_idx < len(cols) else None
                if not key:
                    continue
                lo, hi = fval
                # 金额范围（float）
                if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                    if lo is not None:
                        result = [t for t in result if float(t.get(key, 0)) >= lo]
                    if hi is not None:
                        result = [t for t in result if float(t.get(key, 0)) <= hi]
                # 日期范围（QDate）
                elif lo is not None or hi is not None:
                    if lo:
                        s = lo.toString("yyyy-MM")
                        result = [t for t in result if (t.get("time", "") or "") >= s]
                    if hi:
                        s = hi.toString("yyyy-MM")
                        result = [t for t in result if (t.get("time", "") or "")[:7] <= s]
            else:
                # 文本或下拉筛选
                col_idx = fkey
                key = cols[col_idx][0] if isinstance(col_idx, int) and col_idx < len(cols) else None
                if not key:
                    continue
                val = str(fval).lower()
                result = [t for t in result if val in str(t.get(key, "")).lower()]

        return result

    def _build_filter_row(self, channel: str, cols: list):
        """重建筛选行，根据列类型适配控件"""
        frame = self._filter_frames.get(channel)
        if not frame:
            return

        fl = frame.layout()
        while fl.count():
            item = fl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 用 QGridLayout 支持换行
        QWidget().setLayout(fl)  # 废弃旧 layout
        grid = QGridLayout(frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        max_cols = 5
        for c in range(max_cols):
            grid.setColumnStretch(c, 1)

        filters = self._col_filters.get(channel, {})
        for i, (key, title, _) in enumerate(cols):
            card = QFrame()
            card.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
            wrapper = QHBoxLayout(card)
            wrapper.setContentsMargins(4, 2, 4, 2)
            wrapper.setSpacing(2)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #555;")
            wrapper.addWidget(lbl)

            if key in ("amount", "balance"):
                row = QHBoxLayout()
                lo = QLineEdit(); lo.setPlaceholderText("最低"); lo.setMinimumWidth(80)
                hi = QLineEdit(); hi.setPlaceholderText("最高"); hi.setMinimumWidth(80)

                # 恢复已存储的值
                rng = filters.get(f"{i}_range")
                if rng:
                    lo.blockSignals(True); hi.blockSignals(True)
                    if rng[0] is not None:
                        lo.setText(str(rng[0]))
                    if rng[1] is not None:
                        hi.setText(str(rng[1]))
                    lo.blockSignals(False); hi.blockSignals(False)

                lo.editingFinished.connect(lambda ch=channel, ci=i: self._on_text_filter(ch, ci, lo, hi))
                hi.editingFinished.connect(lambda ch=channel, ci=i: self._on_text_filter(ch, ci, lo, hi))
                row.addWidget(lo, 1); row.addWidget(QLabel("~")); row.addWidget(hi, 1)
                wrapper.addLayout(row, 1)
            elif key == "tx_type":
                cb = QComboBox()
                cb.addItems(["全部", "支出", "收入"])
                if i in filters:
                    idx = cb.findText(filters[i])
                    if idx >= 0:
                        cb.setCurrentIndex(idx)
                cb.currentIndexChanged.connect(lambda _, ch=channel, ci=i, c=cb: self._on_combo_filter(ch, ci, c))
                wrapper.addWidget(cb, 1)
            elif key == "time":
                # 从该渠道数据中提取时间范围
                times = [t.get("time", "")[:7] for t in self._all_transactions
                         if t.get("platform") == channel and t.get("time")]
                if times:
                    min_t = min(times)
                    max_t = max(times)
                    min_date = QDate(int(min_t[:4]), int(min_t[5:7]), 1)
                    max_date = QDate(int(max_t[:4]), int(max_t[5:7]), 1)
                else:
                    min_date = QDate(2020, 1, 1)
                    max_date = QDate.currentDate()

                row = QHBoxLayout()
                frm = QDateEdit(); frm.setCalendarPopup(True); frm.setDisplayFormat("yyyy-MM")
                frm.setDateRange(min_date, max_date)
                to = QDateEdit(); to.setCalendarPopup(True); to.setDisplayFormat("yyyy-MM")
                to.setDateRange(min_date, max_date)

                rng = filters.get(f"{i}_range")
                frm.blockSignals(True)
                to.blockSignals(True)
                if rng and rng[0]:
                    frm.setDate(rng[0])
                else:
                    frm.setDate(min_date)
                if rng and rng[1]:
                    to.setDate(rng[1])
                else:
                    to.setDate(max_date)
                frm.blockSignals(False)
                to.blockSignals(False)
                frm.dateChanged.connect(lambda d, ch=channel, ci=i, w=frm: self._on_date_range(ch, ci, frm, to))
                to.dateChanged.connect(lambda d, ch=channel, ci=i, w=to: self._on_date_range(ch, ci, frm, to))
                row.addWidget(frm, 1); row.addWidget(QLabel("~")); row.addWidget(to, 1)
                wrapper.addLayout(row, 1)
            else:
                inp = QLineEdit()
                inp.editingFinished.connect(lambda ch=channel, ci=i: self._on_col_filter(ch, ci, inp.text()))
                wrapper.addWidget(inp, 1)
            grid.addWidget(card, i // max_cols, i % max_cols)

    def _on_text_filter(self, channel: str, col: int, lo: QLineEdit, hi: QLineEdit):
        try:
            lo_val = float(lo.text()) if lo.text().strip() else None
        except ValueError:
            lo_val = None
        try:
            hi_val = float(hi.text()) if hi.text().strip() else None
        except ValueError:
            hi_val = None
        key = f"{col}_range"
        if lo_val is not None or hi_val is not None:
            self._col_filters[channel][key] = (lo_val, hi_val)
        else:
            self._col_filters[channel].pop(key, None)
        self._page_states[channel] = 0
        self._render_table(channel)

    def _on_date_range(self, channel: str, col: int, frm: QDateEdit, to: QDateEdit):
        d_from = frm.date() if frm.date() > frm.minimumDate() else None
        d_to = to.date() if to.date() > to.minimumDate() else None
        key = f"{col}_range"
        if d_from or d_to:
            self._col_filters[channel][key] = (d_from, d_to)
        else:
            self._col_filters[channel].pop(key, None)
        self._page_states[channel] = 0
        self._render_table(channel)

    def _on_combo_filter(self, channel: str, col: int, cb: QComboBox):
        val = cb.currentText()
        if val and val != "全部":
            self._col_filters[channel][col] = val
        else:
            self._col_filters[channel].pop(col, None)
        self._page_states[channel] = 0
        self._render_table(channel)

    def _render_table(self, channel: str):
        cols = CHANNEL_COLUMNS[channel]
        tbl = self._tables[channel]
        page = self._page_states.get(channel, 0)

        self._build_filter_row(channel, cols)

        filtered = [t for t in self._all_transactions if t.get("platform") == channel]
        filtered = self._apply_filters(filtered, channel)
        total = len(filtered)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        page = max(0, min(page, total_pages - 1))
        self._page_states[channel] = page
        start = page * self._page_size
        end = min(start + self._page_size, total)
        page_data = filtered[start:end]

        tbl.clear()
        tbl.setColumnCount(len(cols))
        tbl.setRowCount(len(page_data))
        tbl.setHorizontalHeaderLabels([c[1] for c in cols])

        for r, t in enumerate(page_data):
            for c, (key, _, _) in enumerate(cols):
                val = t.get(key, "")
                if key == "amount":
                    try:
                        val = f"¥{float(val):,.2f}"
                    except (ValueError, TypeError):
                        val = ""
                item = QTableWidgetItem(str(val) if val is not None else "")
                item.setTextAlignment(Qt.AlignRight if key == "amount" else Qt.AlignLeft)
                tbl.setItem(r, c, item)

        header = tbl.horizontalHeader()
        for i in range(len(cols)):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        self._page_labels[channel].setText(f"第 {page + 1}/{total_pages} 页 ({total} 条)")

    def _go_page(self, delta: int, channel: str):
        self._page_states[channel] = self._page_states.get(channel, 0) + delta
        self._render_table(channel)

    # ── PDF→CSV ──

    def _on_pdf2csv(self):
        if not self._pdf_files:
            QMessageBox.warning(self, "提示", "请先选择银行 PDF 文件")
            return

        layout_name = self._layout_combo.currentData()
        self._pdf_status.setText("转换中...")
        self._pdf_progress.setVisible(True)
        self._pdf_progress.setValue(0)

        from threading import Thread
        Thread(target=self._run_pdf2csv, args=(self._pdf_files, layout_name), daemon=True).start()

    def _run_pdf2csv(self, pdf_paths: list, layout_name: str):
        try:
            import fitz, cv2
            import numpy as np
            from PIL import Image
            from paycheck.ocr.pdf_render import render_page_cropped
            from paycheck.ocr.engine import process_image, warmup_engine
            from paycheck.ocr.layouts import get_layout

            layout = get_layout(layout_name)
            if layout is None:
                raise ValueError(f"不支持的银行类型: {layout_name}")

            # 计算总页数
            total_pages = 0
            for p in pdf_paths:
                d = fitz.open(p)
                total_pages += len(d)
                d.close()

            warmup_engine()

            all_dicts = []
            done = 0
            for pdf_path in pdf_paths:
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
                    self._pdf_progress.setValue(pct)
                    self._pdf_status.setText(f"{done}/{total_pages} 页")
                doc.close()

            if not all_dicts:
                raise RuntimeError("OCR 未识别到任何交易记录")

            out_dir = os.path.dirname(pdf_paths[0]) or "."
            csv_name = os.path.splitext(os.path.basename(pdf_paths[0]))[0] + ".csv"
            csv_path = os.path.join(out_dir, csv_name)

            import csv
            header = ["date", "time", "tx_type", "amount", "counterparty",
                      "channel", "balance", "memo", "tx_name", "currency",
                      "branch", "cp_account", "cp_bank"]
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                for t in all_dicts:
                    w.writerow([t.get(k, "") for k in header])

            self._pdf_status.setText(f"✓ 输出: {csv_name}")
            self._pdf_progress.setVisible(False)
            self._bank_files.append(csv_path)
            getattr(self, "_bank_files_edit").setText(f"已选 {len(self._bank_files)} 个文件")

        except Exception as e:
            log.exception("PDF 转换失败")
            self._pdf_status.setText(f"✗ {e}")
            self._pdf_progress.setVisible(False)
