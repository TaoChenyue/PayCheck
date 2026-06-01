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

    # 内部转账提示区块
    internal_note = ""
    if s["internal_count"] > 0:
        internal_note = (
            f'<div style="background:#fff7e6;border:1px solid #ffd591;border-radius:8px;'
            f'padding:12px 18px;margin:0 0 20px 0;font-size:13px;color:#ad4e00">'
            f'  <strong>⚡ 内部转账已剔除</strong> — 为反映真实消费，共剔除 <strong>{s["internal_count"]} 笔</strong> '
            f'内部转账（充值、提现、理财等），金额合计 <strong>¥{_fmt_num(s["internal_total"])}</strong>。'
            f'（微信: ¥{_fmt_num(s["internal_wechat"])}，支付宝: ¥{_fmt_num(s["internal_alipay"])}）'
            f' 这些是子账户间的资金流动，不影响总资产。'
            f'</div>'
        )

    generated_at = data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # header / footer 中可选的内转备注
    internal_header_note = (
        f' · 已排除 {s["internal_count"]} 笔内部转账（¥{_fmt_num(s["internal_total"])}）'
    ) if s["internal_count"] > 0 else ""
    footer_note = (
        f' · 已排除 {s["internal_count"]} 笔内部转账'
    ) if s["internal_count"] > 0 else ""

    tmpl = Template(_load_template())
    html = tmpl.substitute(
        PERIOD_START=data["period"]["start"],
        PERIOD_END=data["period"]["end"],
        GENERATED_AT=generated_at,
        INTERNAL_HEADER_NOTE=internal_header_note,
        TOTAL_EXPENSE=_fmt_num(s["total_expense"]),
        TOTAL_COUNT=str(s["total_count"]),
        MONTHLY_AVG=_fmt_num(s["monthly_avg"]),
        MONTH_COUNT=str(len(data["monthly"])),
        TOTAL_INCOME=_fmt_num(s["total_income"]),
        INTERNAL_NOTE=internal_note,
        WECHAT_TOTAL=_fmt_num(s["wechat_total"]),
        WECHAT_COUNT=str(s["wechat_count"]),
        ALIPAY_TOTAL=_fmt_num(s["alipay_total"]),
        ALIPAY_COUNT=str(s["alipay_count"]),
        BANK_TOTAL=_fmt_num(s.get("bank_total", 0)),
        BANK_COUNT=str(s.get("bank_count", 0)),
        TABLE_ROWS=table_rows,
        FOOTER_NOTE=footer_note,
        JSON_DATA=json.dumps(data, ensure_ascii=False),
    )
    return html
