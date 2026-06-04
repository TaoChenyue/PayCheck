# PayCheck React 报表前端 — 设计规格

## 概述

将 PayCheck 的分析与报告生成逻辑从 Python 端剥离，用 React SPA 重新实现。
Python CLI 的 `analyse` 命令改为输出 JSON，React 应用通过拖拽加载 JSON 文件完成全部可视化与交互。

## 架构

```
Python CLI（解析 + 聚合）                  React SPA（可视化）
┌──────────────────────────┐          ┌─────────────────────────────┐
│  pdf2image               │          │  拖拽 JSON → 解析 → 渲染     │
│  image2csv               │          │                             │
│  analyse                 │          │  聚合统计（前端重算）         │
│   ├─ 扫描/解析（不变）     │   JSON   │  图表（ECharts）             │
│   ├─ 聚合（不变）         │─────────→│  表格（过滤/分页/标记）      │
│   └─ 输出 report.json    │          │  内部转账（手动标记指纹）     │
└──────────────────────────┘          │  localStorage 持久化         │
                                      └─────────────────────────────┘
```

## 技术栈

| 项目 | 选型 |
|------|------|
| 脚手架 | Vite 6 |
| 框架 | React 18 + TypeScript |
| 图表 | ECharts 5（echarts-for-react 封装） |
| 状态管理 | React 内置 hooks（useState / useCallback / useMemo） |
| CSS | 纯 CSS（从原 template.html 移植，按组件拆分） |
| 包管理 | npm（跟随项目现有习惯） |

## Python 端改动

文件：`src/paycheck/__main__.py`

- `_run_analyse()` 末尾：去掉 `generate_html()` 调用，改为 `json.dump(data, f, ensure_ascii=False, indent=2)`
- 默认输出文件名从 `report.html` 改为 `report.json`
- `aggregate()` 函数本身不变，输出数据结构保持不变
- `html_reporter.py` 和 `template.html` 可标记废弃（不删除，保留参考）

## React 项目结构

```
paycheck-react/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx                    ← 入口
│   ├── App.tsx                     ← 顶层：文件拖拽 + 全局 JSON 状态
│   ├── App.css                     ← 全局样式 + CSS 变量
│   ├── types.ts                    ← 所有 TypeScript 类型定义
│   ├── constants.ts                ← 颜色、平台元信息、列定义
│   ├── utils/
│   │   ├── hash.ts                 ← 交易指纹：sha256(platform+time+amount+counterparty+description) 前16位
│   │   └── aggregation.ts          ← 聚合统计（移植自 Python stats.py）
│   ├── hooks/
│   │   ├── useFingerprints.ts      ← 指纹集合 localStorage 读写
│   │   ├── useAggregation.ts       ← 分类（排除指纹匹配的交易）+ 聚合计算
│   │   └── useFilteredList.ts      ← 多维过滤 + 分页
│   ├── components/
│   │   ├── EmptyState.tsx           ← 无数据时显示拖拽上传区
│   │   ├── ReportHeader.tsx         ← 标题、时间范围、生成时间
│   │   ├── SummaryCards.tsx         ← 总支出 / 月均 / 总收入（可点击展开详情）
│   │   ├── PlatformCards.tsx        ← 微信 / 支付宝 / 银行 平台卡
│   │   ├── InternalSection.tsx      ← 内部转账明细表 + 导出/导入指纹
│   │   ├── DetailTable.tsx          ← 通用详情表格（收入/支出共用）
│   │   │                              checkbox + 过滤 + 分页 + "标记为内部转账"
│   │   ├── MonthlyChart.tsx         ← 月度柱状图 + 平台切换按钮
│   │   ├── CategorySection.tsx       ← 类别饼图 + 横向柱状图 + 类别列表
│   │   ├── PlatformComparison.tsx   ← 三平台堆叠对比图
│   │   ├── MonthlyTable.tsx         ← 月度明细表格
│   │   └── common/
│   │       ├── TagSelect.tsx        ← 多选标签输入 + 下拉建议
│   │       └── Pagination.tsx       ← 分页控件
│   └── styles/
│       ├── cards.css
│       ├── charts.css
│       ├── tables.css
│       ├── filters.css
│       └── internal.css
```

## 组件树

```
App
├─ EmptyState                    ← data === null 时
└─ Dashboard                     ← data !== null 时
   ├─ ReportHeader
   ├─ SummaryCards               ← 三张概览卡，点击展开/收起详情
   ├─ InternalSection            ← 内部转账（明细表 + 导出/导入按钮）
   ├─ IncomeDetails              ← 点击"总收入"卡展开
   │  └─ DetailTable             ← tab(平台切换) + 过滤行 + 表格 + 分页
   ├─ ExpenseDetails             ← 点击"总支出"卡展开
   │  └─ DetailTable
   ├─ PlatformCards
   ├─ MonthlyChart
   ├─ CategorySection
   │  ├─ ECharts 饼图
   │  ├─ ECharts 横向柱状图
   │  └─ 类别列表（带颜色点）
   ├─ PlatformComparison
   └─ MonthlyTable
```

## 数据流

```
  JSON 文件
     │
     ▼ 拖拽上传
  App (useState<AggregatedData | null>)
     │
     ├─→ useFingerprints() ──→ localStorage 指纹集合
     │
     ├─→ useAggregation(data, fingerprints)
     │      ├─ externalTxs = data.all_transactions - 指纹匹配交易
     │      ├─ internalTxs = 指纹匹配交易
     │      └─ stats = aggregate(externalTxs)   ← 前端重算聚合
     │
     ├─→ SummaryCards ← stats.summary
     ├─→ PlatformCards ← stats.summary
     ├─→ MonthlyChart ← stats.monthly
     ├─→ CategorySection ← stats.categories
     ├─→ PlatformComparison ← stats.platform_monthly
     ├─→ MonthlyTable ← stats.monthly
     │
     ├─→ IncomeDetails (DetailTable)
     │      └─ useFilteredList(data.income_details, filters, page)
     │
     ├─→ ExpenseDetails (DetailTable)
     │      └─ useFilteredList(data.all_transactions (支出), filters, page)
     │
     └─→ InternalSection (internalTxs 表格 + 导出/导入指纹)
```

**刷新机制：** 指纹集合变更时，`useAggregation` 重新计算，所有图表组件自动更新（React 响应式）。

## 类型定义

```typescript
// types.ts

interface Transaction {
  platform: "wechat" | "alipay" | "bank";
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance: number;
  currency: string;
  branch: string;
  cp_account: string;
  cp_bank: string;
}

interface AggregatedData {
  period: { start: string; end: string };
  summary: SummaryStats;
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  platform_monthly: PlatformMonthlyItem[];
  income_details: Transaction[];
  all_transactions: Transaction[];
  generated_at: string;
}

interface SummaryStats {
  total_expense: number;
  total_income: number;
  total_count: number;
  monthly_avg: number;
  wechat_total: number;
  alipay_total: number;
  bank_total: number;
  wechat_count: number;
  alipay_count: number;
  bank_count: number;
}

interface MonthlyItem {
  month: string;    // "YYYY-MM"
  expense: number;
  count: number;
  wechat: number;
  alipay: number;
  bank: number;
}

interface CategoryItem {
  name: string;
  amount: number;
  count: number;
  pct: number;
}

interface PlatformMonthlyItem {
  month: string;
  wechat: number;
  alipay: number;
  bank: number;
}
```

## 内部转账（手动标记）

### 指纹生成

```
fingerprint = SHA256(platform + "|" + time + "|" + amount + "|" + counterparty + "|" + description).slice(0, 16)
```

使用 `|` 分隔各字段，取 SHA256 前 16 位十六进制字符串作为指纹。

### localStorage 结构

```json
{
  "paycheck_v1": {
    "fingerprints": ["a1b2c3d4e5f6a7b8", "f9e8d7c6b5a43210"]
  }
}
```

Key: `paycheck_v1`，value 为 `{ fingerprints: string[] }`。

### 导出/导入

- **导出**：将 `{ version: 1, fingerprints: [...] }` 序列化为 JSON 文件下载。额外包含 `exported_at` 时间戳和 `count` 便于识别。
- **导入**：文件选择器读取 JSON，新指纹追加到现有集合（去重合并），不覆盖。
- 按钮位置：`InternalSection` 底部。

### 详情表格交互

- 表格每行左侧有复选框，表头有全选框
- 选中 ≥1 行时，表格上方出现操作栏："已选 N 笔  [标记为内部转账]"
- 点击"标记为内部转账"，计算选中行的指纹，写入 localStorage，触发重新聚合
- 收入详情和支出详情各自独立维护选中状态

### 内部转账明细表

- 展示所有被标记为内部转账的交易（`internalTxs`）
- 按平台 tab 切换（wechat / alipay / bank）
- 支持分页
- 每行有"取消标记"按钮，点击后从指纹集合中移除
- 底部有"导出指纹""导入指纹"按钮

## 详情表格（DetailTable）

通用组件，收入详情和支出详情共用。

### Props

| Prop | 类型 | 说明 |
|------|------|------|
| `items` | `Transaction[]` | 全部待展示交易 |
| `txType` | `"income" \| "expense"` | 收入或支出 |
| `fingerprints` | `Set<string>` | 当前内部转账指纹（用于过滤已标记的） |

### 功能

- **平台 Tab**：wechat / alipay / bank，仅显示有数据的平台
- **过滤行**：时间范围、金额范围、类别/对方/备注/支付方式 多选标签
  - bank 平台额外显示：余额、币别、对方开户行、网点、对方卡号
- **分页**：可选择 10/20/50/100 条每页
- **复选框**：全选 + 单选，选中后显示"标记为内部转账"按钮
- **列定义**：根据平台动态切换（从 constants.ts 读取）

## 图表组件

所有图表组件从原 `template.html` 移植，行为保持一致。

| 组件 | ECharts 图表 |
|------|-------------|
| `MonthlyChart` | 柱状图，支持切换 全部/微信/支付宝/银行 |
| `CategorySection` | 饼图 + 横向柱状图，颜色使用 COLORS 数组循环 |
| `PlatformComparison` | 堆叠柱状图，微信+支付宝+银行三条 series |

窗口 resize 时图表自动 resize。

## 移植清单（从 template.html）

| 原位置 | 目标 |
|--------|------|
| HTML `<style>` 块 | `App.css` + `styles/*.css` |
| JS `aggregate()` 函数 | `utils/aggregation.ts` |
| JS `fmtNum` / `fmtYuan` | `utils/format.ts` 或内联 |
| JS `COLORS` 常量 | `constants.ts` |
| JS `PLATFORM_COLUMNS` | `constants.ts` |
| JS `PLATFORM_META` | `constants.ts` |
| JS `PLATFORM_FILTER_LABELS` | `constants.ts` |
| JS MonthlyChart 初始化 | `MonthlyChart.tsx` |
| JS CategorySection charts | `CategorySection.tsx` |
| JS PlatformComparison chart | `PlatformComparison.tsx` |
| JS IncomeDetails 逻辑 | `DetailTable.tsx`（收入模式） |
| JS ExpenseDetails 逻辑 | `DetailTable.tsx`（支出模式） |
| JS refreshAll 体系 | React 状态驱动（无需手动调用） |

**不需要移植：** 规则引擎相关全部代码（`RULES_KEY`, `DEFAULT_RULES`, `applyRule`, `isInternalTx` 旧版, `RulesSection` 规则编辑 UI, `updateRulesUI` 等）。

## 边界与约束

- React SPA，纯静态部署，无后端
- 数据来源仅为拖拽的 JSON 文件，无 API 调用
- 不引入路由库（单页应用）
- 不引入状态管理库（React 内置 hooks 足够）
- 不引入 UI 组件库（从原 CSS 移植）
- 指纹持久化仅依赖 localStorage
- 浏览器兼容：现代浏览器（Chrome, Firefox, Edge, Safari），不兼容 IE
