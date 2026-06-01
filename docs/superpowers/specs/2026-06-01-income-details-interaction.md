# 总收入点击展开明细交互设计

## 概述

为 PayCheck HTML 报表增加交互性：点击总收入卡片，在当前页下方展开收入明细区域，按渠道（微信/支付宝/银行）分组展示每笔收入的完整信息。

## 背景

当前报表顶部有三张统计卡片：总支出、月均支出、总收入（参考）。其中总收入卡片仅显示汇总数字，不可交互。用户希望点击进入查看每笔收入的详细记录。

## 改动范围

涉及两个文件：

| 文件 | 改动 |
|---|---|
| `src/paycheck/analysis/stats.py` | `aggregate()` 返回值新增 `income_details` 字段 |
| `src/paycheck/report/html_reporter.py` | HTML/CSS/JS 增加可折叠收入明细区域 |

无需修改其他文件。无新增依赖。

## 后端：stats.py

`aggregate()` 函数中，`separate_internal()` 已返回 `external_txs`（外部交易列表），其中每条记录包含 `tx_type_norm` 字段。

在返回值中新增：

```python
"income_details": [
    t for t in external_txs if t["tx_type_norm"] == "收入"
]
```

每条收入记录包含字段：`platform`, `time`, `category`, `counterparty`, `description`, `amount`, `payment_method`。

## 前端：html_reporter.py

### HTML

总收入卡片改为带 `clickable` 类，添加 `data-target="income-details"` 属性。点击后切换下方收入详情区域的可见性。

收入详情区域结构：

```
<section id="income-details" class="section" style="display:none">
  <h2>💰 收入详情</h2>
  <!-- JS 动态渲染，按平台分组 -->
  <div id="incomeContent"></div>
</section>
```

### CSS

```css
.card.clickable { cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; }
.card.clickable:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
.card.clickable:active { transform: translateY(0); }
```

收入区域样式复用现有 `section` / `table` / `th` / `td` 样式，新增平台分组标题样式。

### JavaScript

收入数据通过 JSON 注入（同现有 DATA 模式）：

```javascript
var INCOME_DATA = [...];  // 收入交易列表
```

点击总收入卡片时：

1. 切换 `display` 属性（`none` ↔ `block`）
2. 若展开且内容为空，调用 `renderIncomeDetails()` 渲染
3. 滚动到该区域

`renderIncomeDetails()` 逻辑：

1. 按 `platform` 字段对收入交易分组（wechat / alipay / bank）
2. 每组渲染一个平台标题 + 表格
3. 表格列：时间、金额、类别、对方账户、备注、支付方式
4. 平台标题使用对应颜色标识（微信绿 #07c160、支付宝蓝 #1677ff、银行紫 #722ed1）

## 数据流

```
Transaction 列表
  → aggregate() 中过滤 external_txs, 再过滤 tx_type_norm=="收入"
  → data["income_details"] 传入 generate_html()
  → json.dumps() 序列化为 INCOME_DATA
  → JS 渲染表格
```

## 交互细节

- 点击总收入卡片展开/折叠
- 默认收起
- 展开后卡片不隐藏，保持可见
- 平台分组内按时间排序
- 金额列右对齐（复用现有 tabular-nums 样式）

## 不变的内容

- 不修改现有图表
- 不修改现有统计数据
- 不修改分析逻辑
- 不新增外部依赖
