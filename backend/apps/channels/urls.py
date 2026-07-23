"""渠道管理 URL 路由"""

from rest_framework.routers import DefaultRouter

from apps.channels.views import AlipayTxViewSet, WechatTxViewSet, BocTxViewSet

router = DefaultRouter()
router.register(r"alipay", AlipayTxViewSet, basename="alipay")
router.register(r"wechat", WechatTxViewSet, basename="wechat")
router.register(r"boc", BocTxViewSet, basename="boc")

urlpatterns = router.urls
