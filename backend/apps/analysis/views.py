"""统计分析 API — ORM 聚合查询、月度趋势、类别分布"""

from django.db.models import Count, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, Substr
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transactions.models import Transaction


class SummaryView(APIView):
    """聚合摘要统计

    GET /api/analysis/summary/
    返回：期间、总汇总、月度趋势、类别分布
    """

    def get(self, request):
        txns = Transaction.objects.all()
        expense_txns = txns.filter(tx_type="支出")
        income_txns = txns.filter(tx_type="收入")

        # ── ORM 聚合：汇总 ──
        agg = expense_txns.aggregate(
            total_expense=Sum("amount"),
            wechat_total=Sum("amount", filter=Q(platform="wechat")),
            alipay_total=Sum("amount", filter=Q(platform="alipay")),
            boc_total=Sum("amount", filter=Q(platform="boc")),
            wechat_count=Count("id", filter=Q(platform="wechat")),
            alipay_count=Count("id", filter=Q(platform="alipay")),
            boc_count=Count("id", filter=Q(platform="boc")),
        )
        total_expense = agg["total_expense"] or 0.0
        total_income = income_txns.aggregate(Sum("amount"))["amount__sum"] or 0.0
        total_count = txns.count()

        # ── ORM 聚合：月均 ──
        month_count = (
            txns.exclude(time="")
            .annotate(month=Substr("time", 1, 7))
            .values("month")
            .distinct()
            .count()
        ) or 1
        monthly_avg = total_expense / month_count

        # ── ORM 聚合：月度趋势 ──
        monthly_qs = (
            expense_txns.exclude(time="")
            .annotate(month=Substr("time", 1, 7))
            .exclude(month="")
            .values("month")
            .annotate(
                expense=Sum("amount"),
                count=Count("id"),
                wechat=Sum("amount", filter=Q(platform="wechat")),
                alipay=Sum("amount", filter=Q(platform="alipay")),
                boc=Sum("amount", filter=Q(platform="boc")),
            )
            .order_by("month")
        )
        monthly = [
            {
                "month": m["month"],
                "expense": round(m["expense"], 2),
                "count": m["count"],
                "wechat": round(m["wechat"] or 0, 2),
                "alipay": round(m["alipay"] or 0, 2),
                "boc": round(m["boc"] or 0, 2),
            }
            for m in monthly_qs
        ]

        # ── ORM 聚合：类别分布 ──
        category_qs = (
            expense_txns.annotate(
                cat_name=Coalesce("category", Value("未分类"))
            )
            .values("cat_name")
            .annotate(amount=Sum("amount"), count=Count("id"))
            .order_by("-amount")
        )
        categories = [
            {
                "name": c["cat_name"],
                "amount": round(c["amount"], 2),
                "count": c["count"],
                "pct": round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0.0,
            }
            for c in category_qs
        ]

        # ── 期间 ──
        period_qs = txns.exclude(time="").aggregate(
            start=Min("time"), end=Max("time")
        )
        period_start = period_qs["start"][:7] if period_qs["start"] else ""
        period_end = period_qs["end"][:7] if period_qs["end"] else ""

        return Response({
            "period": {"start": period_start, "end": period_end},
            "summary": {
                "total_expense": round(total_expense, 2),
                "total_income": round(total_income, 2),
                "total_count": total_count,
                "monthly_avg": round(monthly_avg, 2),
                "wechat_total": round(agg["wechat_total"] or 0, 2),
                "alipay_total": round(agg["alipay_total"] or 0, 2),
                "boc_total": round(agg["boc_total"] or 0, 2),
                "wechat_count": agg["wechat_count"] or 0,
                "alipay_count": agg["alipay_count"] or 0,
                "boc_count": agg["boc_count"] or 0,
            },
            "monthly": monthly,
            "categories": categories,
            "generated_at": timezone.now().isoformat(),
        })


class MonthlyView(APIView):
    """月度趋势数据

    GET /api/analysis/monthly/?platform=alipay|wechat|boc
    """

    def get(self, request):
        platform = request.query_params.get("platform", "")

        txns = Transaction.objects.filter(tx_type="支出")
        if platform in ("alipay", "wechat", "boc"):
            txns = txns.filter(platform=platform)

        monthly_qs = (
            txns.exclude(time="")
            .annotate(month=Substr("time", 1, 7))
            .exclude(month="")
            .values("month")
            .annotate(expense=Sum("amount"), count=Count("id"))
            .order_by("month")
        )

        monthly = [
            {
                "month": m["month"],
                "expense": round(m["expense"], 2),
                "count": m["count"],
            }
            for m in monthly_qs
        ]

        return Response(monthly)


class CategoriesView(APIView):
    """类别分布数据

    GET /api/analysis/categories/?limit=20
    """

    def get(self, request):
        limit = int(request.query_params.get("limit", 20))

        txns = Transaction.objects.filter(tx_type="支出")

        total_expense = txns.aggregate(Sum("amount"))["amount__sum"] or 0.0

        category_qs = (
            txns.annotate(cat_name=Coalesce("category", Value("未分类")))
            .values("cat_name")
            .annotate(amount=Sum("amount"), count=Count("id"))
            .order_by("-amount")[:limit]
        )

        categories = [
            {
                "name": c["cat_name"],
                "amount": round(c["amount"], 2),
                "count": c["count"],
                "pct": round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0.0,
            }
            for c in category_qs
        ]

        return Response(categories)
