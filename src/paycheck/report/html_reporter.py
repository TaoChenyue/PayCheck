"""HTML 报表生成模块 — 使用 ECharts 生成交互式账单分析报告"""

import json
from datetime import datetime
from typing import Dict


def _fmt_num(n):
    if not isinstance(n, (int, float)):
        return "0.00"
    return f"{n:,.2f}"


def _fmt_yuan(n):
    return f"¥{_fmt_num(n)}"


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

    json_data = json.dumps(data, ensure_ascii=False)

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

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PayCheck 账单分析报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:#f0f2f5;color:#333;line-height:1.6}}
.container{{max-width:1200px;margin:0 auto;padding:20px}}
header{{text-align:center;padding:40px 0 20px}}
header h1{{font-size:28px;color:#1a1a2e}}
header .period{{font-size:16px;color:#666;margin-top:4px}}
header .generated{{font-size:13px;color:#999;margin-top:2px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0}}
.card{{background:#fff;border-radius:12px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.card .card-label{{font-size:14px;color:#888}}
.card .card-value{{font-size:28px;font-weight:700;color:#1a1a2e;margin-top:4px}}
.card .card-sub{{font-size:13px;color:#999;margin-top:2px}}
.platform-cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0}}
.platform-card{{border-radius:12px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06);color:#fff}}
.platform-card.wechat{{background:linear-gradient(135deg,#07c160,#06ad56)}}
.platform-card.alipay{{background:linear-gradient(135deg,#1677ff,#096dd9)}}
.platform-card.bank{{background:linear-gradient(135deg,#722ed1,#531dab)}}
.platform-card .platform-name{{font-size:14px;opacity:0.9}}
.platform-card .platform-value{{font-size:26px;font-weight:700;margin-top:4px}}
.platform-card .platform-count{{font-size:13px;opacity:0.85;margin-top:2px}}
.section{{background:#fff;border-radius:12px;padding:24px;margin:20px 0;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.section h2{{font-size:18px;color:#1a1a2e;margin-bottom:16px}}
.chart{{width:100%;height:400px}}
.filter{{margin-bottom:12px}}
.filter button{{padding:6px 18px;border:1px solid #d9d9d9;background:#fff;border-radius:6px;cursor:pointer;font-size:13px;margin-right:8px;transition:all 0.2s}}
.filter button.active{{background:#1a1a2e;color:#fff;border-color:#1a1a2e}}
.filter button:hover:not(.active){{border-color:#1a1a2e;color:#1a1a2e}}
.chart-row{{display:flex;gap:16px}}
.chart-row .chart{{height:380px}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
thead{{background:#fafafa}}
th{{padding:12px 16px;text-align:left;font-weight:600;color:#555;border-bottom:2px solid #e8e8e8}}
td{{padding:10px 16px;border-bottom:1px solid #f0f0f0}}
tr:hover td{{background:#fafafa}}
td:last-child,th:last-child{{text-align:right}}
td:nth-child(3),td:nth-child(4),td:nth-child(5),td:nth-child(6){{text-align:right;font-variant-numeric:tabular-nums}}
footer{{text-align:center;padding:20px;color:#aaa;font-size:13px}}
@media(max-width:768px){{.cards{{grid-template-columns:1fr}}.platform-cards{{grid-template-columns:1fr}}.chart-row{{flex-direction:column}}}}
.category-list{{margin-top:16px}}
.category-item{{display:flex;align-items:center;padding:6px 0}}
.category-item .cat-dot{{width:10px;height:10px;border-radius:50%;margin-right:10px;flex-shrink:0}}
.category-item .cat-name{{flex:1;font-size:14px}}
.category-item .cat-amount{{font-size:14px;font-weight:600}}
.category-item .cat-pct{{font-size:13px;color:#999;margin-left:8px}}
.chart-inline{{display:inline-block;vertical-align:top}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>PayCheck 账单分析报告</h1>
  <p class="period">{data["period"]["start"]} ~ {data["period"]["end"]} · 总账户（微信 + 支付宝 + 银行）</p>
  <p class="generated">生成于 {generated_at}"""
    if s["internal_count"] > 0:
        html += f' · 已排除 {s["internal_count"]} 笔内部转账（¥{_fmt_num(s["internal_total"])}）'
    html += """</p>
</header>

<div class="cards">
  <div class="card"><div class="card-label">总支出</div><div class="card-value">¥""" + _fmt_num(s["total_expense"]) + f"""</div><div class="card-sub">{s["total_count"]} 笔 · 已剔除内部转账</div></div>
  <div class="card"><div class="card-label">月均支出</div><div class="card-value">¥""" + _fmt_num(s["monthly_avg"]) + f"""</div><div class="card-sub">共 {len(data["monthly"])} 个月</div></div>
  <div class="card"><div class="card-label">总收入（参考）</div><div class="card-value">¥""" + _fmt_num(s["total_income"]) + """</div><div class="card-sub">外部收入 · 不含转账</div></div>
</div>
""" + internal_note + """
<div class="platform-cards">
  <div class="platform-card wechat"><div class="platform-name">微信支付（真实消费）</div><div class="platform-value">¥""" + _fmt_num(s["wechat_total"]) + f"""</div><div class="platform-count">{s["wechat_count"]} 笔</div></div>
  <div class="platform-card alipay"><div class="platform-name">支付宝（真实消费）</div><div class="platform-value">¥""" + _fmt_num(s["alipay_total"]) + f"""</div><div class="platform-count">{s["alipay_count"]} 笔</div></div>
  <div class="platform-card bank"><div class="platform-name">银行账户（银行卡）</div><div class="platform-value">¥""" + _fmt_num(s.get("bank_total", 0)) + f"""</div><div class="platform-count">{s.get("bank_count", 0)} 笔</div></div>
</div>

<div class="section">
  <h2>月度开销</h2>
  <div class="filter" id="monthlyFilter">
    <button class="active" data-mode="all">全部</button>
    <button data-mode="wechat">微信</button>
    <button data-mode="alipay">支付宝</button>
    <button data-mode="bank">银行</button>
  </div>
  <div id="monthlyChart" class="chart"></div>
</div>

<div class="section">
  <h2>消费类别分布</h2>
  <div class="chart-row">
    <div id="categoryPie" class="chart chart-inline" style="width:55%;height:380px"></div>
    <div id="categoryBar" class="chart chart-inline" style="width:45%;height:380px"></div>
  </div>
  <div class="category-list" id="categoryList"></div>
</div>

<div class="section">
  <h2>平台对比（真实消费）</h2>
  <div id="platformChart" class="chart" style="height:380px"></div>
</div>

<div class="section">
  <h2>月度明细（总账户）</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>月份</th><th>笔数</th><th>总金额</th><th>微信</th><th>支付宝</th><th>银行</th></tr></thead>
      <tbody>
        """ + table_rows + """
      </tbody>
    </table>
  </div>
</div>

<footer>
  <p>PayCheck · 总账户（微信 + 支付宝 + 银行）""" + (f' · 已排除 {s["internal_count"]} 笔内部转账' if s["internal_count"] > 0 else "") + f""" · {generated_at}</p>
</footer>
</div>

<script>
var DATA = {json_data};
var COLORS = ["#5470c6","#91cc75","#fac858","#ee6666","#73c0de","#3ba272","#fc8452","#9a60b4","#ea7ccc","#2f4554","#61a0a8","#d48265","#749f83","#ca8622","#bda29a"];
function fmtNum(n) {{ return Number(n).toLocaleString("zh-CN", {{minimumFractionDigits:2, maximumFractionDigits:2}}); }}
function fmtYuan(n) {{ return "¥" + fmtNum(n); }}

// Monthly chart
(function(){{
var chart = echarts.init(document.getElementById("monthlyChart"));
var mode = "all";
function update() {{
  var vals = DATA.monthly.map(function(m) {{ return mode === "all" ? m.expense : (mode === "wechat" ? m.wechat : (mode === "alipay" ? m.alipay : m.bank)); }});
  var months = DATA.monthly.map(function(m) {{ return m.month; }});
  chart.setOption({{
    tooltip: {{ trigger: "axis", formatter: function(p) {{ return "<strong>" + p[0].axisValue + "</strong><br/>" + p[0].marker + " 支出: " + fmtYuan(p[0].value); }} }},
    grid: {{ left: 80, right: 30, top: 20, bottom: 30 }},
    xAxis: {{ type: "category", data: months, axisLabel: {{ rotate: 45, fontSize: 11 }} }},
    yAxis: {{ type: "value", axisLabel: {{ formatter: "¥{{value}}" }} }},
    series: [{{ type: "bar", data: vals, itemStyle: {{ color: mode === "all" ? "#5470c6" : (mode === "wechat" ? "#07c160" : (mode === "alipay" ? "#1677ff" : "#722ed1")), borderRadius: [4,4,0,0] }} }}]
  }}, true);
  chart.resize();
}}
document.querySelectorAll("#monthlyFilter button").forEach(function(b) {{
  b.addEventListener("click", function() {{
    document.querySelectorAll("#monthlyFilter button").forEach(function(x) {{ x.classList.remove("active"); }});
    this.classList.add("active");
    mode = this.dataset.mode;
    update();
  }});
}});
update();
window.addEventListener("resize", function() {{ chart.resize(); }});
}})();

// Category charts
(function(){{
if (!DATA.categories || DATA.categories.length === 0) {{
  document.getElementById("categoryList").innerHTML = '<p style="color:#999;padding:10px">暂无分类数据</p>';
  return;
}}
var cats = DATA.categories;
var colorMap = {{}};
cats.forEach(function(c,i) {{ colorMap[c.name] = COLORS[i % COLORS.length]; }});
var listEl = document.getElementById("categoryList");
cats.forEach(function(c) {{
  var div = document.createElement("div");
  div.className = "category-item";
  div.innerHTML = '<span class="cat-dot" style="background:' + colorMap[c.name] + '"></span><span class="cat-name">' + c.name + '</span><span class="cat-amount">' + fmtYuan(c.amount) + '</span><span class="cat-pct">' + c.pct + '%</span>';
  listEl.appendChild(div);
}});
var pie = echarts.init(document.getElementById("categoryPie"));
pie.setOption({{
  tooltip: {{ formatter: function(p) {{ return "<strong>" + p.name + "</strong><br/>金额: " + fmtYuan(p.value) + "<br/>占比: " + p.percent + "%"; }} }},
  series: [{{ type: "pie", radius: ["35%", "65%"], center: ["50%", "50%"],
    data: cats.map(function(c) {{ return {{ name: c.name, value: c.amount }}; }}),
    itemStyle: {{ color: function(p) {{ return colorMap[p.name]; }}, borderRadius: 4, borderColor: "#fff", borderWidth: 2 }},
    label: {{ show: false }},
    emphasis: {{ label: {{ show: true, fontSize: 14, fontWeight: "bold" }}, itemStyle: {{ shadowBlur: 10, shadowColor: "rgba(0,0,0,0.2)" }} }}
  }}]
}}, true);
var bar = echarts.init(document.getElementById("categoryBar"));
bar.setOption({{
  tooltip: {{ trigger: "axis", axisPointer: {{ type: "shadow" }}, formatter: function(p) {{ return "<strong>" + p[0].name + "</strong><br/>" + p[0].marker + " " + fmtYuan(p[0].value) + " (" + (cats.find(function(c) {{ return c.name === p[0].name; }})?.pct || 0) + "%)"; }} }},
  grid: {{ left: 10, right: 80, top: 10, bottom: 10 }},
  xAxis: {{ type: "value", axisLabel: {{ formatter: "¥{{value}}" }} }},
  yAxis: {{ type: "category", data: cats.map(function(c) {{ return c.name; }}).reverse(), axisLabel: {{ fontSize: 11 }} }},
  series: [{{ type: "bar", data: cats.map(function(c) {{ return {{value: c.amount, itemStyle: {{color: colorMap[c.name], borderRadius: [0,4,4,0]}}}}; }}).reverse() }}]
}}, true);
pie.on("click", function(p) {{ bar.dispatchAction({{ type: "highlight", name: p.name }}); }});
window.addEventListener("resize", function() {{ pie.resize(); bar.resize(); }});
}})();

// Platform comparison
(function(){{
if (!DATA.platform_monthly || DATA.platform_monthly.length === 0) return;
var chart = echarts.init(document.getElementById("platformChart"));
chart.setOption({{
  tooltip: {{ trigger: "axis", axisPointer: {{ type: "shadow" }}, formatter: function(p) {{
    var h = "<strong>" + p[0].axisValue + "</strong><br/>";
    p.forEach(function(x) {{ h += x.marker + " " + x.seriesName + ": " + fmtYuan(x.value) + "<br/>"; }});
    return h;
  }}}},
  legend: {{ data: ["微信", "支付宝", "银行"], top: 0 }},
  grid: {{ left: 80, right: 30, top: 40, bottom: 30 }},
  xAxis: {{ type: "category", data: DATA.platform_monthly.map(function(d) {{ return d.month; }}), axisLabel: {{ rotate: 45, fontSize: 11 }} }},
  yAxis: {{ type: "value", axisLabel: {{ formatter: "¥{{value}}" }} }},
  series: [
    {{ name: "微信", type: "bar", data: DATA.platform_monthly.map(function(d) {{ return d.wechat; }}), itemStyle: {{ color: "#07c160", borderRadius: [4,4,0,0] }} }},
    {{ name: "支付宝", type: "bar", data: DATA.platform_monthly.map(function(d) {{ return d.alipay; }}), itemStyle: {{ color: "#1677ff", borderRadius: [4,4,0,0] }} }},
    {{ name: "银行", type: "bar", data: DATA.platform_monthly.map(function(d) {{ return d.bank; }}), itemStyle: {{ color: "#722ed1", borderRadius: [4,4,0,0] }} }},
  ]
}}, true);
window.addEventListener("resize", function() {{ chart.resize(); }});
}})();
</script>
</body>
</html>"""
    return html
