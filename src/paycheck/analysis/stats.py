"""数据聚合统计模块 — 月度、平台、类别多维度统计"""

from datetime import datetime
import logging
from collections import defaultdict
from typing import List, Dict

from paycheck.core.models import Transaction

log = logging.getLogger("paycheck.analysis")


def compute_stats(txs: List[Dict]) -> Dict:
    """对一组交易计算通用统计量"""
    log.info("计算统计: %d 条交易", len(txs))
    expenses = [t for t in txs if t["tx_type_norm"] == "支出"]
    incomes = [t for t in txs if t["tx_type_norm"] == "收入"]

    total_expense = sum(t["amount"] for t in expenses)
    total_income = sum(t["amount"] for t in incomes)
    total_count = len(expenses)

    months = sorted(set(t["month"] for t in expenses))
    months_count = len(months)
    monthly_avg = round(total_expense / months_count, 2) if months_count > 0 else 0

    wechat_exp = [t for t in expenses if t["platform"] == "wechat"]
    alipay_exp = [t for t in expenses if t["platform"] == "alipay"]
    bank_exp = [t for t in expenses if t["platform"] == "bank"]

    # 月度数据
    monthly_map = {}
    for m in months:
        monthly_map[m] = {"month": m, "expense": 0, "count": 0, "wechat": 0, "alipay": 0, "bank": 0}
    for t in expenses:
        m = monthly_map.get(t["month"])
        if not m:
            continue
        m["expense"] += t["amount"]
        m["count"] += 1
        if t["platform"] == "wechat":
            m["wechat"] += t["amount"]
        elif t["platform"] == "alipay":
            m["alipay"] += t["amount"]
        elif t["platform"] == "bank":
            m["bank"] += t["amount"]

    monthly_data = [
        {
            "month": m,
            "expense": round(monthly_map[m]["expense"], 2),
            "count": monthly_map[m]["count"],
            "wechat": round(monthly_map[m]["wechat"], 2),
            "alipay": round(monthly_map[m]["alipay"], 2),
            "bank": round(monthly_map[m]["bank"], 2),
        }
        for m in months
    ]

    # 类别数据
    cat_map = {}
    for t in expenses:
        cat = t.get("category") or "未分类"
        if cat not in cat_map:
            cat_map[cat] = {"name": cat, "amount": 0, "count": 0}
        cat_map[cat]["amount"] += t["amount"]
        cat_map[cat]["count"] += 1

    categories = sorted(cat_map.values(), key=lambda c: c["amount"], reverse=True)
    categories = [
        {
            "name": c["name"],
            "amount": round(c["amount"], 2),
            "count": c["count"],
            "pct": round(c["amount"] / total_expense * 100, 1) if total_expense > 0 else 0,
        }
        for c in categories
    ]

    return {
        "totalExpense": round(total_expense, 2),
        "totalIncome": round(total_income, 2),
        "totalCount": total_count,
        "monthlyAvg": monthly_avg,
        "wechatTotal": round(sum(t["amount"] for t in wechat_exp), 2),
        "alipayTotal": round(sum(t["amount"] for t in alipay_exp), 2),
        "bankTotal": round(sum(t["amount"] for t in bank_exp), 2),
        "wechatCount": len(wechat_exp),
        "alipayCount": len(alipay_exp),
        "bankCount": len(bank_exp),
        "months": months,
        "monthlyData": monthly_data,
        "categories": categories,
        "platformMonthly": [
            {"month": m["month"], "wechat": m["wechat"], "alipay": m["alipay"], "bank": m["bank"]}
            for m in monthly_data
        ],
    }


def aggregate(transactions: List[Transaction]) -> Dict:
    """聚合所有交易记录，返回统计结果"""
    log.info("开始聚合: %d 条交易", len(transactions))
    if not transactions:
        log.warning("交易列表为空")
        return {
            "period": {"start": "", "end": ""},
            "summary": {
                "total_expense": 0, "total_income": 0, "total_count": 0, "monthly_avg": 0,
                "wechat_total": 0, "alipay_total": 0, "bank_total": 0,
                "wechat_count": 0, "alipay_count": 0, "bank_count": 0,
            },
            "monthly": [], "categories": [], "platform_monthly": [], "income_details": [],
            "all_transactions": [],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    tx_type_map = {
        "支出": "支出", "pay": "支出", "Pay": "支出",
        "收入": "收入", "收款": "收入",
        "不计收支": "不计收支",
    }

    parsed = []
    for t in transactions:
        try:
            dt_str = t.time.replace("-", "/")
            dt = datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S")
        except (ValueError, AttributeError):
            try:
                dt = datetime.strptime(dt_str, "%Y/%m/%d")
            except (ValueError, AttributeError):
                log.debug("日期解析失败: %s", t.time)
                continue
        month = f"{dt.year}-{dt.month:02d}"
        parsed.append({
            "platform": t.platform,
            "time": t.time,
            "category": t.category,
            "counterparty": t.counterparty,
            "description": t.description,
            "amount": t.amount,
            "tx_type": t.tx_type,
            "payment_method": t.payment_method,
            "balance": t.balance,
            "currency": t.currency,
            "branch": t.branch,
            "cp_account": t.cp_account,
            "cp_bank": t.cp_bank,
            "dt": dt,
            "month": month,
            "tx_type_norm": tx_type_map.get(t.tx_type, "支出"),
        })

    # 前端可用的全量交易列表（不含内部字段 dt/month/tx_type_norm）
    all_transactions = [
        {
            "platform": t["platform"],
            "time": t["time"],
            "category": t["category"],
            "counterparty": t["counterparty"],
            "description": t["description"],
            "amount": t["amount"],
            "tx_type": t["tx_type"],
            "payment_method": t["payment_method"],
            "balance": t["balance"],
            "currency": t["currency"],
            "branch": t["branch"],
            "cp_account": t["cp_account"],
            "cp_bank": t["cp_bank"],
        }
        for t in parsed
    ]

    # 统计计算
    stats_input = parsed
    ext = compute_stats(stats_input)

    # 收入明细
    income_details = [
        {
            "platform": t["platform"],
            "time": t["time"],
            "category": t["category"],
            "counterparty": t["counterparty"],
            "description": t["description"],
            "amount": t["amount"],
            "tx_type": t["tx_type"],
            "payment_method": t["payment_method"],
            "balance": t["balance"],
            "currency": t["currency"],
            "branch": t["branch"],
            "cp_account": t["cp_account"],
            "cp_bank": t["cp_bank"],
        }
        for t in stats_input
        if t["tx_type_norm"] == "收入"
    ]
    # 按时间排序
    income_details.sort(key=lambda x: x["time"])

    log.info("聚合完成: 支出%d条/收入%d条, %d个月, %d个类别",
             ext["totalCount"], len(income_details),
             len(ext["months"]), len(ext["categories"]))

    return {
        "period": {
            "start": ext["months"][0] if ext["months"] else "",
            "end": ext["months"][-1] if ext["months"] else "",
        },
        "summary": {
            "total_expense": ext["totalExpense"],
            "total_income": ext["totalIncome"],
            "total_count": ext["totalCount"],
            "monthly_avg": ext["monthlyAvg"],
            "wechat_total": ext["wechatTotal"],
            "alipay_total": ext["alipayTotal"],
            "bank_total": ext["bankTotal"],
            "wechat_count": ext["wechatCount"],
            "alipay_count": ext["alipayCount"],
            "bank_count": ext["bankCount"],
        },
        "monthly": ext["monthlyData"],
        "categories": ext["categories"],
        "platform_monthly": ext["platformMonthly"],
        "income_details": income_details,
        "all_transactions": all_transactions,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
