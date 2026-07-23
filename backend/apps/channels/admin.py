"""渠道管理 Django Admin 配置"""

from django.contrib import admin

from apps.channels.models import AlipayTx, WechatTx, BocTx


@admin.register(AlipayTx)
class AlipayTxAdmin(admin.ModelAdmin):
    """支付宝交易 Admin"""

    list_display = [
        "id", "time", "category", "counterparty", "description",
        "amount", "tx_type", "payment_method", "created_at",
    ]
    search_fields = ["counterparty", "description"]
    list_per_page = 50


@admin.register(WechatTx)
class WechatTxAdmin(admin.ModelAdmin):
    """微信交易 Admin"""

    list_display = [
        "id", "time", "category", "counterparty", "description",
        "amount", "tx_type", "payment_method", "created_at",
    ]
    search_fields = ["counterparty", "description"]
    list_per_page = 50


@admin.register(BocTx)
class BocTxAdmin(admin.ModelAdmin):
    """银行交易 Admin"""

    list_display = [
        "id", "time", "category", "counterparty", "description",
        "amount", "tx_type", "payment_method", "balance", "currency",
        "branch", "cp_account", "cp_bank", "created_at",
    ]
    search_fields = ["counterparty", "description"]
    list_per_page = 50
