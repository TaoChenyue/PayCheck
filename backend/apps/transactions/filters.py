"""交易记录筛选器 — 支持多渠道、多维度组合筛选"""

import django_filters
from django_filters.rest_framework import FilterSet, CharFilter, NumberFilter

from apps.transactions.models import Transaction


class TransactionFilter(FilterSet):
    """Transaction 查询筛选器"""

    platform = CharFilter(field_name="platform", lookup_expr="exact")
    tx_type = CharFilter(field_name="tx_type", lookup_expr="exact")
    time_after = CharFilter(field_name="time", lookup_expr="gte")
    time_before = CharFilter(field_name="time", lookup_expr="lte")
    amount_min = NumberFilter(field_name="amount", lookup_expr="gte")
    amount_max = NumberFilter(field_name="amount", lookup_expr="lte")
    category = CharFilter(field_name="category", lookup_expr="icontains")
    counterparty = CharFilter(field_name="counterparty", lookup_expr="icontains")
    search = CharFilter(method="filter_search")
    tag_ids = CharFilter(method="filter_tags")

    class Meta:
        model = Transaction
        fields = [
            "platform", "tx_type", "time_after", "time_before",
            "amount_min", "amount_max", "category", "counterparty",
            "search", "tag_ids",
        ]

    def filter_search(self, queryset, name, value):
        """全局搜索：counterparty + description 模糊匹配"""
        return queryset.filter(
            django_filters.Q(counterparty__icontains=value)
            | django_filters.Q(description__icontains=value)
        )

    def filter_tags(self, queryset, name, value):
        """标签筛选：逗号分隔的 tag ID 列表，OR 逻辑"""
        tag_id_list = [
            int(tid) for tid in value.split(",") if tid.strip().isdigit()
        ]
        if not tag_id_list:
            return queryset
        return queryset.filter(tags__id__in=tag_id_list).distinct()
