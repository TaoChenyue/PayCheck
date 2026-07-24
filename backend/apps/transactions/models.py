"""统一交易记录模型 — 前端查询唯一入口。

三渠道数据经过去重后同步到此表，包含所有渠道字段的并集。
"""

from django.db import models


class Transaction(models.Model):
    """统一交易记录"""

    PLATFORM_CHOICES = [
        ("alipay", "支付宝"),
        ("wechat", "微信"),
        ("boc", "银行"),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    time = models.CharField(max_length=50)
    category = models.CharField(max_length=200, default="", blank=True)
    counterparty = models.CharField(max_length=200, default="", blank=True)
    description = models.CharField(max_length=500, default="", blank=True)
    amount = models.FloatField()
    tx_type = models.CharField(max_length=20, default="支出")
    payment_method = models.CharField(max_length=100, default="", blank=True)
    balance = models.FloatField(default=0.0)
    currency = models.CharField(max_length=20, default="", blank=True)
    branch = models.CharField(max_length=200, default="", blank=True)
    cp_account = models.CharField(max_length=100, default="", blank=True)
    cp_bank = models.CharField(max_length=200, default="", blank=True)
    source_channel = models.CharField(max_length=20)  # 'alipay'|'wechat'|'boc'
    source_id = models.IntegerField()  # FK to channel table id
    row_hash = models.CharField(max_length=32, unique=True)  # MD5
    tags = models.ManyToManyField("Tag", through="TransactionTag", related_name="transactions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        indexes = [
            models.Index(fields=["platform"]),
            models.Index(fields=["time"]),
            models.Index(fields=["amount"]),
            models.Index(fields=["tx_type"]),
            models.Index(fields=["counterparty"]),
            models.Index(fields=["category"]),
            models.Index(fields=["-time", "platform"]),
            models.Index(fields=["-time", "tx_type"]),
        ]

    def __str__(self):
        return f"[{self.platform}] {self.time} {self.counterparty} {self.amount}"


class Tag(models.Model):
    """交易标签"""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "tags"

    def __str__(self):
        return self.name


class TransactionTag(models.Model):
    """交易-标签关联表"""

    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, db_column="transaction_id"
    )
    tag = models.ForeignKey(
        Tag, on_delete=models.CASCADE, db_column="tag_id"
    )

    class Meta:
        db_table = "transaction_tags"
        unique_together = [["transaction", "tag"]]

    def __str__(self):
        return f"Tx#{self.transaction_id} → Tag#{self.tag_id}"
