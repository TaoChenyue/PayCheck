"""交易管理 URL 路由"""

from rest_framework.routers import DefaultRouter

from apps.transactions.views import TransactionViewSet, TagViewSet

router = DefaultRouter()
router.register(r"transactions", TransactionViewSet, basename="transaction")
router.register(r"tags", TagViewSet, basename="tag")

urlpatterns = router.urls
