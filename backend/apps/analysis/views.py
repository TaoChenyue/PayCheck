"""统计分析 API — 聚合查询、月度趋势、类别分布"""

from collections import defaultdict

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

        # 分离支出和收入
        expense_txns = txns.filter(tx_type__in=["支出", "pay", "Pay"])
        income_txns = txns.filter(tx_type__in=["收入", "收款"])

        total_expense = sum(t.amount for t in expense_txns)
        total_income = sum(t.amount for t in income_txns)
        total_count = txns.count()

        # 计算月均
        times = [t.time for t in txns if t.time]
        if times:
            months = set()
            for t in times:
                m = t.replace("-", "/")[:7]
                if len(m) >= 7:
                    months.add(m)
            month_count = len(months) or 1
        else:
            month_count = 1
        monthly_avg = total_expense / month_count if month_count > 0 else 0.0

        # 各平台统计
        wechat_total = sum(t.amount for t in expense_txns.filter(platform="wechat"))
        alipay_total = sum(t.amount for t in expense_txns.filter(platform="alipay"))
        bank_total = sum(t.amount for t in expense_txns.filter(platform="bank"))
        wechat_count = expense_txns.filter(platform="wechat").count()
        alipay_count = expense_txns.filter(platform="alipay").count()
        bank_count = expense_txns.filter(platform="bank").count()

        # 月度趋势
        monthly_data = {}
        for t in expense_txns:
            if not t.time:
                continue
            m = t.time.replace("-", "/")[:7]
            if len(m) < 7:
                continue
            if m not in monthly_data:
                monthly_data[m] = {
                    "month": m,
                    "expense": 0.0,
                    "count": 0,
                    "wechat": 0.0,
                    "alipay": 0.0,
                    "bank": 0.0,
                }
            monthly_data[m]["expense"] += t.amount
            monthly_data[m]["count"] += 1
            if t.platform == "wechat":
                monthly_data[m]["wechat"] += t.amount
            elif t.platform == "alipay":
                monthly_data[m]["alipay"] += t.amount
            elif t.platform == "bank":
                monthly_data[m]["bank"] += t.amount

        monthly = sorted(monthly_data.values(), key=lambda x: x["month"])

        # 类别分布
        cat_data = defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0})
        for t in expense_txns:
            cat = t.category or "未分类"
            if cat not in cat_data:
                cat_data[cat]["name"] = cat
            cat_data[cat]["amount"] += t.amount
            cat_data[cat]["count"] += 1

        categories = sorted(
            cat_data.values(), key=lambda x: x["amount"], reverse=True
        )
        for c in categories:
            c["pct"] = round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0.0

        # 期间
        period_start = ""
        period_end = ""
        if times:
            sorted_times = sorted(times)
            period_start = sorted_times[0].replace("-", "/")[:7]
            period_end = sorted_times[-1].replace("-", "/")[:7]

        return Response({
            "period": {"start": period_start, "end": period_end},
            "summary": {
                "total_expense": round(total_expense, 2),
                "total_income": round(total_income, 2),
                "total_count": total_count,
                "monthly_avg": round(monthly_avg, 2),
                "wechat_total": round(wechat_total, 2),
                "alipay_total": round(alipay_total, 2),
                "bank_total": round(bank_total, 2),
                "wechat_count": wechat_count,
                "alipay_count": alipay_count,
                "bank_count": bank_count,
            },
            "monthly": monthly,
            "categories": categories,
            "generated_at": timezone.now().isoformat(),
        })


class MonthlyView(APIView):
    """月度趋势数据

    GET /api/analysis/monthly/?platform=alipay|wechat|bank
    """

    def get(self, request):
        platform = request.query_params.get("platform", "")

        txns = Transaction.objects.filter(tx_type__in=["支出", "pay", "Pay"])
        if platform in ("alipay", "wechat", "bank"):
            txns = txns.filter(platform=platform)

        monthly_data = {}
        for t in txns:
            if not t.time:
                continue
            m = t.time.replace("-", "/")[:7]
            if len(m) < 7:
                continue
            if m not in monthly_data:
                monthly_data[m] = {
                    "month": m,
                    "expense": 0.0,
                    "count": 0,
                }
            monthly_data[m]["expense"] += t.amount
            monthly_data[m]["count"] += 1

        monthly = sorted(monthly_data.values(), key=lambda x: x["month"])
        # Round values
        for m in monthly:
            m["expense"] = round(m["expense"], 2)

        return Response(monthly)


class CategoriesView(APIView):
    """类别分布数据

    GET /api/analysis/categories/?limit=20
    """

    def get(self, request):
        limit = int(request.query_params.get("limit", 20))

        txns = Transaction.objects.filter(tx_type__in=["支出", "pay", "Pay"])

        total_expense = sum(t.amount for t in txns)
        cat_data = defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0})
        for t in txns:
            cat = t.category or "未分类"
            if cat not in cat_data:
                cat_data[cat]["name"] = cat
            cat_data[cat]["amount"] += t.amount
            cat_data[cat]["count"] += 1

        categories = sorted(
            cat_data.values(), key=lambda x: x["amount"], reverse=True
        )[:limit]

        for c in categories:
            c["amount"] = round(c["amount"], 2)
            c["pct"] = round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0.0

        return Response(categories)
