"""渠道交易记录 ViewSet。

提供三个渠道（支付宝/微信/银行）的只读查询接口，
支持筛选、搜索和排序。
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.viewsets import ModelViewSet

from apps.channels.models import AlipayTx, WechatTx, BocTx
from apps.channels.serializers import (
    AlipayTxSerializer,
    WechatTxSerializer,
    BocTxSerializer,
)


class AlipayTxViewSet(ModelViewSet):
    """支付宝交易记录 ViewSet — 支持筛选/搜索/排序"""

    queryset = AlipayTx.objects.all()
    serializer_class = AlipayTxSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["counterparty", "description"]
    ordering_fields = ["time", "amount", "tx_type", "counterparty", "created_at"]
    ordering = ["-time"]


class WechatTxViewSet(ModelViewSet):
    """微信交易记录 ViewSet — 支持筛选/搜索/排序"""

    queryset = WechatTx.objects.all()
    serializer_class = WechatTxSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["counterparty", "description"]
    ordering_fields = ["time", "amount", "tx_type", "counterparty", "created_at"]
    ordering = ["-time"]


class BocTxViewSet(ModelViewSet):
    """银行交易记录 ViewSet — 支持筛选/搜索/排序"""

    queryset = BocTx.objects.all()
    serializer_class = BocTxSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["counterparty", "description"]
    ordering_fields = ["time", "amount", "tx_type", "counterparty", "created_at"]
    ordering = ["-time"]
