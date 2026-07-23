"""交易管理 Django Admin 配置"""

from django.contrib import admin

from apps.transactions.models import Transaction, Tag, TransactionTag


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """统一交易记录 Admin"""

    list_display = [
        "id", "platform", "time", "category", "counterparty",
        "description", "amount", "tx_type", "payment_method",
        "source_channel", "source_id", "row_hash", "created_at",
    ]
    search_fields = ["counterparty", "description", "row_hash"]
    list_filter = ["platform", "tx_type", "source_channel"]
    list_per_page = 50


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """标签 Admin"""

    list_display = ["id", "name"]
    search_fields = ["name"]
    list_per_page = 100


@admin.register(TransactionTag)
class TransactionTagAdmin(admin.ModelAdmin):
    """交易-标签关联 Admin"""

    list_display = ["id", "transaction_id", "tag_id"]
    list_select_related = ["transaction", "tag"]
    list_per_page = 100
