"""统计分析 URL 路由"""

from django.urls import path

from apps.analysis.views import SummaryView, MonthlyView, CategoriesView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="analysis-summary"),
    path("monthly/", MonthlyView.as_view(), name="analysis-monthly"),
    path("categories/", CategoriesView.as_view(), name="analysis-categories"),
]
