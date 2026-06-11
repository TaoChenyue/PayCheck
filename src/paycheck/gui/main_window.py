"""PySide6 主窗口 — PDF→CSV + 导入 + 分渠道表格 + 分页 + 标签筛选"""

import logging
import os
from typing import List, Set

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
from paycheck.gui.tag_builder import TagBuilder
from paycheck.gui.tag_dialog import TagDialog
from paycheck.core.tag_expr import validate_expression, compile_expression

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


class Pdf2CsvWorker(QThread):
    """PDF→CSV 后台线程，通过信号更新 UI"""
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
            import fitz, cv2
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

            import csv
            header = ["date", "time", "tx_type", "amount", "counterparty",
                      "channel", "balance", "memo", "tx_name", "currency",
                      "branch", "cp_account", "cp_bank"]
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                for t in all_dicts:
                    w.writerow([t.get(k, "") for k in header])

            self.finished.emit(csv_name)
        except Exception as e:
            log.exception("PDF 转换失败")
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
        self._bank_type_combo = None  # _init_ui 中创建
        self._tag_map = {}            # {tag_name: tag_id}
        self._tag_filter_ids: Set[int] | None = None  # None=无筛选, set=筛选结果

        self._setup_menu()
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

        # ═══ 顶层分页：导入 / 交易明细 ═══
        self._page_tabs = QTabWidget()

        # ── 页1: 导入 ──
        import_page = QWidget()
        import_page_layout = QVBoxLayout(import_page)

        # PDF→CSV
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

        import_page_layout.addWidget(pdf_group)

        # 数据源
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

        import_page_layout.addWidget(import_group)
        import_page_layout.addStretch()
        self._page_tabs.addTab(import_page, "导入")

        # ── 页2: 交易明细 ──
        detail_page = QWidget()
        detail_layout = QVBoxLayout(detail_page)

        # 摘要
        summary_group = QGroupBox("摘要")
        summary_layout_inner = QGridLayout(summary_group)
        self._summary_labels = {}
        card_names = ["总支出", "总收入", "月均支出", "月均收入",
                      "微信", "支付宝", "银行", "总交易"]
        for i, name in enumerate(card_names):
            card = QGroupBox(name)
            card.setMinimumWidth(120)
            cl = QVBoxLayout(card)
            lbl = QLabel("-")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
            cl.addWidget(lbl)
            self._summary_labels[name] = lbl
            summary_layout_inner.addWidget(card, i // 4, i % 4)
        detail_layout.addWidget(summary_group)

        # 标签筛选
        self._tag_builder = TagBuilder()
        self._tag_builder.execute_requested.connect(self._on_tag_filter)
        detail_layout.addWidget(self._tag_builder)

        # 交易表格
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tables = {}
        self._col_filters = {"wechat": {}, "alipay": {}, "bank": {}}
        self._filter_frames = {}
        self._filter_widgets = {}

        channel_names = {"wechat": "微信", "alipay": "支付宝", "bank": "银行"}
        for ch_key, ch_name in channel_names.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

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

            self._tabs.addTab(tab, ch_name)

        detail_layout.addWidget(self._tabs, 1)
        self._page_tabs.addTab(detail_page, "交易明细")

        layout.addWidget(self._page_tabs, 1)

        # ── 底部状态 ──
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

    # ── 菜单栏 ──

    def _setup_menu(self):
        pass

    def _on_open_tag_manager(self):
        dlg = TagDialog(self, db_path=db.DB_PATH, mode="manage")
        if dlg.exec():
            self._load_from_db()

    # ── 快捷键 ──

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_T:
            self._on_tag_shortcut()
        else:
            super().keyPressEvent(event)

    def _on_tag_shortcut(self):
        """Ctrl+T: 为交易明细中选中的行批量打标签"""
        idx = self._tabs.currentIndex()
        ch_key = ("wechat", "alipay", "bank")[idx] if 0 <= idx < 3 else "wechat"
        tbl = self._tables[ch_key]
        selected = tbl.selectedIndexes()
        if not selected:
            return
        # 通过选中行反查交易 ID
        selected_rows = set()
        for sel in selected:
            selected_rows.add(sel.row())
        tx_ids = []
        # 必须与 _render_table 使用相同的筛选逻辑
        channel_data = [t for t in self._all_transactions if t.get("platform") == ch_key]
        if self._tag_filter_ids is not None:
            channel_data = [t for t in channel_data if t.get("id") in self._tag_filter_ids]
        channel_data = self._apply_filters(channel_data, ch_key)
        for row in sorted(selected_rows):
            if row < len(channel_data):
                tx_ids.append(channel_data[row].get("id"))
        if not tx_ids:
            return
        dlg = TagDialog(self, db_path=db.DB_PATH, mode="assign", tx_ids=tx_ids)
        if dlg.exec():
            self._load_from_db()

    # ── 标签筛选 ──

    def _on_tag_filter(self, expr_text: str):
        """TagBuilder 执行按钮回调"""
        if not expr_text.strip():
            self._tag_filter_ids = None
            db.set_setting("tag_expr", "")
        else:
            valid, error = validate_expression(expr_text, self._tag_map)
            if not valid:
                self._status.setText(f"标签表达式无效: {error}")
                return
            sql = compile_expression(expr_text, self._tag_map)
            conn = db._connect(db.DB_PATH)
            try:
                rows = conn.execute(sql).fetchall()
                self._tag_filter_ids = {r[0] for r in rows}
            finally:
                conn.close()
            db.set_setting("tag_expr", expr_text)
        self._update_summary()
        self._render_all_tables()

    def _update_summary(self):
        """根据当前标签筛选更新摘要卡片"""
        if self._tag_filter_ids is not None:
            txs = [t for t in self._all_transactions if t.get("id") in self._tag_filter_ids]
        else:
            txs = self._all_transactions

        if not txs:
            for name in self._summary_labels:
                self._summary_labels[name].setText("-")
            self._status.setText("无匹配交易")
            return

        expenses = [t for t in txs if t.get("tx_type") == "支出"]
        incomes = [t for t in txs if t.get("tx_type") == "收入"]

        total_expense = sum(t["amount"] for t in expenses)
        total_income = sum(t["amount"] for t in incomes)

        expense_months = len(set(t["time"][:7] for t in expenses if t.get("time"))) or 1
        monthly_avg = round(total_expense / expense_months, 2)

        income_months = len(set(t["time"][:7] for t in incomes if t.get("time"))) or 1
        monthly_income = round(total_income / income_months, 2)

        def platform_total(ts, p):
            return sum(t["amount"] for t in ts if t.get("platform") == p)

        wechat_exp = [t for t in expenses if t.get("platform") == "wechat"]
        alipay_exp = [t for t in expenses if t.get("platform") == "alipay"]
        bank_exp = [t for t in expenses if t.get("platform") == "bank"]

        self._summary_labels["总支出"].setText(f"¥{total_expense:,.2f}")
        self._summary_labels["总收入"].setText(f"¥{total_income:,.2f}")
        self._summary_labels["月均支出"].setText(f"¥{monthly_avg:,.2f}")
        self._summary_labels["月均收入"].setText(f"¥{monthly_income:,.2f}")
        self._summary_labels["微信"].setText(f"¥{platform_total(expenses, 'wechat'):,.2f} / {len(wechat_exp)}笔")
        self._summary_labels["支付宝"].setText(f"¥{platform_total(expenses, 'alipay'):,.2f} / {len(alipay_exp)}笔")
        self._summary_labels["银行"].setText(f"¥{platform_total(expenses, 'bank'):,.2f} / {len(bank_exp)}笔")
        self._summary_labels["总交易"].setText(f"{len(expenses)} 笔")
        self._status.setText(f"共 {len(txs)} 条交易")

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
        self._tag_filter_ids = None
        if self._all_transactions:
            self._update_summary()
        else:
            self._status.setText("请导入账单文件")

        self._render_all_tables()
        self._refresh_tag_data()
        self._restore_tag_filter()

    def _restore_tag_filter(self):
        """从数据库恢复上次的标签筛选表达式和视觉状态"""
        expr = db.get_setting("tag_expr", "")
        if expr:
            self._tag_builder.restore_expression(expr)
            self._on_tag_filter(expr)

    def _refresh_tag_data(self):
        """刷新标签数据到 TagBuilder"""
        tags = db.get_all_tags()
        self._tag_map = {t["name"]: t["id"] for t in tags}
        self._tag_builder.set_tag_data(self._tag_map, tags)

    def _sync_bank_tab_label(self):
        if self._bank_type_combo is not None and self._bank_type_combo.count() > 0:
            name = self._bank_type_combo.currentData()
            self._tabs.setTabText(2, name.upper() if name else "银行")

    # ── 表格渲染 ──

    def _render_all_tables(self):
        self._render_current_tab()

    def _render_current_tab(self):
        idx = self._tabs.currentIndex()
        ch_key = ("wechat", "alipay", "bank")[idx] if 0 <= idx < 3 else "wechat"
        self._render_table(ch_key)

    def _on_tab_changed(self, _idx):
        if self._all_transactions:
            self._render_current_tab()

    def _on_apply_filters(self, channel: str):
        """从所有筛选控件收集值并执行筛选"""
        new_filters = {}
        for item in self._filter_widgets.get(channel, []):
            wtype = item[0]
            if wtype == "text":
                _, col, inp = item
                text = inp.text().strip()
                if text:
                    new_filters[col] = text
            elif wtype == "range":
                _, col, lo, hi = item
                try:
                    lo_val = float(lo.text()) if lo.text().strip() else None
                except ValueError:
                    lo_val = None
                try:
                    hi_val = float(hi.text()) if hi.text().strip() else None
                except ValueError:
                    hi_val = None
                if lo_val is not None or hi_val is not None:
                    new_filters[f"{col}_range"] = (lo_val, hi_val)
            elif wtype == "combo":
                _, col, cb = item
                val = cb.currentText()
                if val and val != "全部":
                    new_filters[col] = val
            elif wtype == "date":
                _, col, frm, to = item
                d_from = frm.date() if frm.date() > frm.minimumDate() else None
                d_to = to.date() if to.date() > to.minimumDate() else None
                if d_from or d_to:
                    new_filters[f"{col}_range"] = (d_from, d_to)
        self._col_filters[channel] = new_filters
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
        self._filter_widgets[channel] = []
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

                rng = filters.get(f"{i}_range")
                if rng:
                    if rng[0] is not None:
                        lo.setText(str(rng[0]))
                    if rng[1] is not None:
                        hi.setText(str(rng[1]))

                self._filter_widgets[channel].append(("range", i, lo, hi))
                row.addWidget(lo, 1); row.addWidget(QLabel("~")); row.addWidget(hi, 1)
                wrapper.addLayout(row, 1)
            elif key == "tx_type":
                cb = QComboBox()
                cb.addItems(["全部", "支出", "收入", "不计收支"])
                if i in filters:
                    idx = cb.findText(filters[i])
                    if idx >= 0:
                        cb.setCurrentIndex(idx)

                self._filter_widgets[channel].append(("combo", i, cb))
                wrapper.addWidget(cb, 1)
            elif key == "time":
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

                self._filter_widgets[channel].append(("date", i, frm, to))
                row.addWidget(frm, 1); row.addWidget(QLabel("~")); row.addWidget(to, 1)
                wrapper.addLayout(row, 1)
            else:
                inp = QLineEdit()
                if i in filters:
                    inp.setText(str(filters[i]))

                self._filter_widgets[channel].append(("text", i, inp))
                wrapper.addWidget(inp, 1)
            grid.addWidget(card, i // max_cols, i % max_cols)

        # 筛选按钮
        filter_btn = QPushButton("筛选")
        filter_btn.clicked.connect(lambda checked, ch=channel: self._on_apply_filters(ch))
        grid.addWidget(filter_btn, ((len(cols)) // max_cols), (len(cols)) % max_cols)

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
                if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                    if lo is not None:
                        result = [t for t in result if float(t.get(key, 0)) >= lo]
                    if hi is not None:
                        result = [t for t in result if float(t.get(key, 0)) <= hi]
                elif lo is not None or hi is not None:
                    if lo:
                        s = lo.toString("yyyy-MM")
                        result = [t for t in result if (t.get("time", "") or "") >= s]
                    if hi:
                        s = hi.toString("yyyy-MM")
                        result = [t for t in result if (t.get("time", "") or "")[:7] <= s]
            else:
                col_idx = fkey
                key = cols[col_idx][0] if isinstance(col_idx, int) and col_idx < len(cols) else None
                if not key:
                    continue
                val = str(fval).lower()
                result = [t for t in result if val in str(t.get(key, "")).lower()]

        return result

    def _render_table(self, channel: str):
        cols = CHANNEL_COLUMNS[channel]
        tbl = self._tables[channel]

        self._build_filter_row(channel, cols)

        filtered = [t for t in self._all_transactions if t.get("platform") == channel]
        if self._tag_filter_ids is not None:
            filtered = [t for t in filtered if t.get("id") in self._tag_filter_ids]
        filtered = self._apply_filters(filtered, channel)
        total = len(filtered)

        tbl.clear()
        tbl.setColumnCount(len(cols))
        tbl.setRowCount(total)
        tbl.setHorizontalHeaderLabels([c[1] for c in cols])

        for r, t in enumerate(filtered):
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
        getattr(self, "_bank_files_edit").setText(f"已选 {len(self._bank_files)} 个文件")

    def _on_pdf2csv_error(self, msg: str):
        self._pdf_status.setText(f"失败: {msg}")
        self._pdf_progress.setVisible(False)
