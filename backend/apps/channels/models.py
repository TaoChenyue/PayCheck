"""渠道数据表 — 支付宝、微信、银行三渠道独立存储。

每张表保留各渠道的特有字段，作为数据源使用。
前端查询统一走 transactions 表。
"""

from django.db import models


class AlipayTx(models.Model):
    """支付宝交易记录"""

    time = models.CharField(max_length=50)  # "YYYY-MM-DD HH:MM:SS"
    category = models.CharField(max_length=200, default="", blank=True)
    counterparty = models.CharField(max_length=200, default="", blank=True)
    description = models.CharField(max_length=500, default="", blank=True)
    amount = models.FloatField()
    tx_type = models.CharField(max_length=20, default="支出")  # 支出/收入/不计收支
    payment_method = models.CharField(max_length=100, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alipay_transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["time", "amount", "counterparty"], name="uq_alipay_tx"
            )
        ]

    def __str__(self):
        return f"[支付宝] {self.time} {self.counterparty} {self.amount}"


class WechatTx(models.Model):
    """微信交易记录 — 字段与支付宝相同"""

    time = models.CharField(max_length=50)
    category = models.CharField(max_length=200, default="", blank=True)
    counterparty = models.CharField(max_length=200, default="", blank=True)
    description = models.CharField(max_length=500, default="", blank=True)
    amount = models.FloatField()
    tx_type = models.CharField(max_length=20, default="支出")
    payment_method = models.CharField(max_length=100, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wechat_transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["time", "amount", "counterparty"], name="uq_wechat_tx"
            )
        ]

    def __str__(self):
        return f"[微信] {self.time} {self.counterparty} {self.amount}"


class BocTx(models.Model):
    """银行交易记录 — 含余额/币种/分行等特有字段"""

    time = models.CharField(max_length=50)
    category = models.CharField(max_length=200, default="", blank=True)  # maps from tx_name
    counterparty = models.CharField(max_length=200, default="", blank=True)
    description = models.CharField(max_length=500, default="", blank=True)  # maps from memo
    amount = models.FloatField()
    tx_type = models.CharField(max_length=20, default="支出")
    payment_method = models.CharField(max_length=100, default="", blank=True)  # maps from channel
    balance = models.FloatField(default=0.0)
    currency = models.CharField(max_length=20, default="", blank=True)
    branch = models.CharField(max_length=200, default="", blank=True)
    cp_account = models.CharField(max_length=100, default="", blank=True)
    cp_bank = models.CharField(max_length=200, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "boc_transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["time", "amount", "counterparty"], name="uq_boc_tx"
            )
        ]

    def __str__(self):
        return f"[银行] {self.time} {self.counterparty} {self.amount}"
