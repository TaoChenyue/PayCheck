"""Root URL configuration for PayCheck backend."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/channels/", include("apps.channels.urls")),
    path("api/transactions/", include("apps.transactions.urls")),
    path("api/import/", include("apps.ingest.urls")),
    path("api/analysis/", include("apps.analysis.urls")),
]
