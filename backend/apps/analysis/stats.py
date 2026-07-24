"""统计分析工具函数 — 从 views.py 提取的可复用聚合逻辑。

当前 stats 逻辑直接内联在 views.py 的 SummaryView/MonthlyView/CategoriesView 中。
本模块预留给未来复杂统计计算场景（如同比/环比、分类预算分析等）。
"""

from collections import defaultdict
from typing import Dict, List


def compute_category_distribution(transactions, total_expense: float) -> List[Dict]:
    """计算类别支出分布，按金额降序排列。

    Args:
        transactions: Transaction queryset (expense only)
        total_expense: 总支出金额

    Returns:
        List[dict] with keys: name, amount, count, pct
    """
    cat_data: Dict[str, Dict] = defaultdict(
        lambda: {"name": "", "amount": 0.0, "count": 0}
    )
    for tx in transactions:
        cat = tx.category or "未分类"
        if cat not in cat_data:
            cat_data[cat]["name"] = cat
        cat_data[cat]["amount"] += tx.amount
        cat_data[cat]["count"] += 1

    categories = sorted(cat_data.values(), key=lambda x: x["amount"], reverse=True)
    for c in categories:
        c["amount"] = round(c["amount"], 2)
        c["pct"] = round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0.0

    return categories
