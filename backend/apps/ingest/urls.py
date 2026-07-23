"""数据导入 URL 路由"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.ingest.views import ImportUploadView, ImportJobViewSet

router = DefaultRouter()
router.register(r"jobs", ImportJobViewSet, basename="import-job")

urlpatterns = router.urls + [
    path("upload/", ImportUploadView.as_view(), name="import-upload"),
]
