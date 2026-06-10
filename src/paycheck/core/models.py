"""统一交易记录模型"""

from dataclasses import dataclass


@dataclass
class Transaction:
    """统一交易记录模型，所有解析器都产出此类型"""

    platform: str = ""
    time: str = ""
    category: str = ""
    counterparty: str = ""
    description: str = ""
    amount: float = 0.0
    tx_type: str = "支出"
    payment_method: str = ""
    balance: float = 0.0
    currency: str = ""
    branch: str = ""
    cp_account: str = ""
    cp_bank: str = ""

    def __repr__(self):
        return f"[{self.platform}] {self.time} {self.tx_type} ¥{self.amount}"
