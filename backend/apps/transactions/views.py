"""交易记录 ViewSet — 统一查询入口 + 标签管理 API"""

from django.db import transaction as db_transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import (
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from apps.channels.models import AlipayTx, WechatTx, BocTx
from apps.transactions.filters import TransactionFilter
from apps.transactions.models import Transaction, Tag, TransactionTag
from apps.transactions.serializers import (
    TagSerializer,
    TransactionSerializer,
    BatchTagsSerializer,
)


class TransactionViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin, DestroyModelMixin):
    """统一交易记录 ViewSet

    仅暴露 DESIGN.md §7.1 定义的端点：
    - list: 分页查询，支持多维度筛选/搜索/排序
    - retrieve: 单条详情
    - destroy: 删除交易（级联删除渠道表源数据）
    - tags (detail): 为单条交易设置标签
    - batch-tags (collection): 批量打标签

    不暴露 POST/PUT/PATCH（创建/更新），交易数据仅由导入流程写入。
    """

    queryset = Transaction.objects.prefetch_related("tags").all()
    serializer_class = TransactionSerializer
    filterset_class = TransactionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["counterparty", "description"]
    ordering_fields = ["time", "amount", "platform", "tx_type", "created_at"]
    ordering = ["-time"]

    def perform_destroy(self, instance):
        """删除交易时，级联删除对应渠道表的源记录"""
        source_channel = instance.source_channel
        source_id = instance.source_id

        channel_model_map = {
            "alipay": AlipayTx,
            "wechat": WechatTx,
            "boc": BocTx,
        }
        channel_model = channel_model_map.get(source_channel)
        if channel_model:
            channel_model.objects.filter(id=source_id).delete()

        instance.delete()

    @action(detail=True, methods=["post"])
    def tags(self, request, pk=None):
        """设置单条交易的标签（替换模式）

        POST body: {"tag_ids": [1, 2, 3]}
        """
        transaction = self.get_object()
        tag_ids = request.data.get("tag_ids", [])

        with db_transaction.atomic():
            TransactionTag.objects.filter(transaction=transaction).delete()
            tags = Tag.objects.filter(id__in=tag_ids)
            for tag in tags:
                TransactionTag.objects.create(transaction=transaction, tag=tag)

        return Response(TransactionSerializer(transaction).data)

    @action(detail=False, methods=["post"], url_path="batch-tags")
    def batch_tags(self, request):
        """批量设置标签

        POST body: {"transaction_ids": [1, 2, 3], "tag_ids": [4, 5]}
        """
        serializer = BatchTagsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tx_ids = serializer.validated_data["transaction_ids"]
        tag_ids = serializer.validated_data["tag_ids"]

        tags = list(Tag.objects.filter(id__in=tag_ids))
        transactions = Transaction.objects.filter(id__in=tx_ids)

        with db_transaction.atomic():
            TransactionTag.objects.filter(
                transaction_id__in=tx_ids, tag_id__in=tag_ids
            ).delete()
            for tx in transactions:
                for tag in tags:
                    TransactionTag.objects.get_or_create(
                        transaction=tx, tag=tag
                    )

        return Response(
            {"updated_transactions": len(tx_ids), "tags_applied": len(tag_ids)},
            status=status.HTTP_200_OK,
        )


class TagViewSet(ModelViewSet):
    """标签管理 ViewSet — 完整 CRUD"""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]
    ordering = ["name"]
