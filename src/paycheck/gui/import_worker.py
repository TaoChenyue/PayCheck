"""后台导入线程 — 解析微信/支付宝/银行文件并写入数据库。"""

import logging
import os

from PySide6.QtCore import QThread, Signal

from paycheck.ingest.parsers.wechat import parse_wechat_xlsx
from paycheck.ingest.parsers.alipay import parse_alipay_csv
from paycheck.ingest.parsers.boc import parse_boc_csv
from paycheck.storage import database as db
from paycheck.core.constants import (
    FIELD_PLATFORM, FIELD_TIME, FIELD_CATEGORY, FIELD_COUNTERPARTY,
    FIELD_DESCRIPTION, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_PAYMENT_METHOD,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK,
)

log = logging.getLogger("paycheck.gui")


class ImportWorker(QThread):
    """后台导入线程，解析多平台账单文件并写入数据库。"""

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
                FIELD_PLATFORM: t.platform, FIELD_TIME: t.time,
                FIELD_CATEGORY: t.category, FIELD_COUNTERPARTY: t.counterparty,
                FIELD_AMOUNT: t.amount, FIELD_TX_TYPE: t.tx_type,
                FIELD_PAYMENT_METHOD: t.payment_method, FIELD_DESCRIPTION: t.description,
                FIELD_BALANCE: t.balance, FIELD_CURRENCY: t.currency,
                FIELD_BRANCH: t.branch, FIELD_CP_ACCOUNT: t.cp_account,
                FIELD_CP_BANK: t.cp_bank,
            } for t in transactions]

            added = db.insert_transactions(dicts)
            self.finished.emit(added, len(dicts) - added)
        except Exception as e:
            log.exception("导入失败")
            self.error.emit(str(e))
