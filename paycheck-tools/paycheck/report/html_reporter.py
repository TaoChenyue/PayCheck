"""HTML 报表生成模块 — 使用 ECharts 生成交互式账单分析报告"""

import json
from datetime import datetime
from string import Template
from importlib.resources import files as _pkg_files
from typing import Dict


def _fmt_num(n):
    if not isinstance(n, (int, float)):
        return "0.00"
    return f"{n:,.2f}"


def _fmt_yuan(n):
    return f"¥{_fmt_num(n)}"


def _load_template() -> str:
    """从包中加载 HTML 模板文件"""
    return _pkg_files("paycheck.report").joinpath("template.html").read_text("utf-8")


def generate_html(data: Dict) -> str:
    """生成完整的 HTML 报告"""
    s = data["summary"]

    # 构建月度表格行
    table_rows = ""
    for m in data["monthly"]:
        wc = _fmt_yuan(m["wechat"]) if m["wechat"] > 0 else "-"
        ac = _fmt_yuan(m["alipay"]) if m["alipay"] > 0 else "-"
        bc = _fmt_yuan(m["bank"]) if m["bank"] > 0 else "-"
        table_rows += (
            f"<tr><td>{m['month']}</td><td>{m['count']}</td>"
            f"<td>¥{_fmt_num(m['expense'])}</td><td>{wc}</td><td>{ac}</td><td>{bc}</td></tr>"
        )

    generated_at = data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    tmpl = Template(_load_template())
    html = tmpl.substitute(
        PERIOD_START=data["period"]["start"],
        PERIOD_END=data["period"]["end"],
        GENERATED_AT=generated_at,
        TOTAL_EXPENSE=_fmt_num(s["total_expense"]),
        TOTAL_COUNT=str(s["total_count"]),
        MONTHLY_AVG=_fmt_num(s["monthly_avg"]),
        MONTH_COUNT=str(len(data["monthly"])),
        TOTAL_INCOME=_fmt_num(s["total_income"]),
        WECHAT_TOTAL=_fmt_num(s["wechat_total"]),
        WECHAT_COUNT=str(s["wechat_count"]),
        ALIPAY_TOTAL=_fmt_num(s["alipay_total"]),
        ALIPAY_COUNT=str(s["alipay_count"]),
        BANK_TOTAL=_fmt_num(s.get("bank_total", 0)),
        BANK_COUNT=str(s.get("bank_count", 0)),
        TABLE_ROWS=table_rows,
        JSON_DATA=json.dumps(data, ensure_ascii=False),
    )
    return html
