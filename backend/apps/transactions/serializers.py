"""交易记录序列化器"""

from rest_framework import serializers

from apps.transactions.models import Transaction, Tag, TransactionTag


class TagSerializer(serializers.ModelSerializer):
    """标签序列化器"""

    class Meta:
        model = Tag
        fields = ["id", "name"]


class TransactionSerializer(serializers.ModelSerializer):
    """交易记录序列化器（读取用，含嵌套标签）"""

    tags = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = "__all__"

    def get_tags(self, obj):
        """返回关联标签列表"""
        return TagSerializer(
            obj.tags.all(), many=True, read_only=True
        ).data


class TransactionWriteSerializer(serializers.ModelSerializer):
    """交易记录序列化器（创建/更新用，不含标签）"""

    class Meta:
        model = Transaction
        fields = [
            "platform", "time", "category", "counterparty", "description",
            "amount", "tx_type", "payment_method", "balance", "currency",
            "branch", "cp_account", "cp_bank", "source_channel", "source_id",
            "row_hash",
        ]


class BatchTagsSerializer(serializers.Serializer):
    """批量打标签请求序列化器"""

    transaction_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1
    )
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1
    )
