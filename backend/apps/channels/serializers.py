"""渠道数据序列化器"""

from rest_framework import serializers

from apps.channels.models import AlipayTx, WechatTx, BocTx


class AlipayTxSerializer(serializers.ModelSerializer):
    """支付宝交易序列化器"""

    class Meta:
        model = AlipayTx
        fields = "__all__"


class WechatTxSerializer(serializers.ModelSerializer):
    """微信交易序列化器"""

    class Meta:
        model = WechatTx
        fields = "__all__"


class BocTxSerializer(serializers.ModelSerializer):
    """银行交易序列化器"""

    class Meta:
        model = BocTx
        fields = "__all__"
