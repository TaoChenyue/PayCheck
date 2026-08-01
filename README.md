<p align="center">
  <h1 align="center">📊 PayCheck</h1>
  <p align="center"><strong>个人账单统计工具 — 前后端分离 Web 应用</strong></p>
  <p align="center">聚合微信 · 支付宝 · 中国银行三渠道账单，自动剔除内部转账，Web 界面一站式管理</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.0.1-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/GPU-CUDA%2012.6-orange?logo=nvidia" alt="CUDA">
</p>

---

## 📋 目录

- [简介](#简介)
- [技术架构](#技术架构)
- [项目结构](#项目结构)
- [前置依赖](#前置依赖)
- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [API 接口](#api-接口)
- [开发指南](#开发指南)
- [许可](#许可)

---

## 简介

**PayCheck** 是一款个人账单聚合分析 Web 应用。它将分散在微信、支付宝、中国银行（BOC）等多个渠道的账单汇总到统一管线下，提供 Web 界面完成导入、查看与分析。

核心特性：

- **多源聚合** — 微信 `.xlsx`、支付宝 `.csv`、银行 `.pdf` 统一导入
- **统一交易模型** — 三渠道数据并集去重，`Transaction` 表作为唯一查询入口
- **自动 OCR** — 基于 PaddleOCR 的银行流水 PDF 识别管线，ThreadPoolExecutor 异步处理
- **智能过滤** — 自动剔除"充值/提现/零钱"等内部转账，还原真实消费
- **标签系统** — 标签 CRUD + 单条/批量打标签 + 递归下降标签表达式引擎（∩ ∪ - 集合运算）
- **高级筛选** — 10 维筛选参数（平台/类型/时间/金额/分类/交易对方/标签等），搜索防抖 300ms
- **Web 界面** — React 单页应用，左侧手风琴菜单，响应式布局
- **PDF→CSV 工具** — 独立工具页，银行 PDF 上传 → OCR 识别 → CSV 下载
- **分渠道管理** — 支付宝、微信、中国银行三个独立数据表，支持筛选排序和列配置

---

## 技术架构

```
┌───────────────────────┐     ┌──────────────────────────────────┐
│     React 前端         │     │        Django 后端                │
│  (Vite + Ant Design)  │◄───►│  (DRF + ThreadPoolExecutor + SQLite)         │
│  localhost:5173       │ API │  localhost:8000                  │
└───────────────────────┘     └──────────────────────────────────┘
```

### 后端

| 技术 | 用途 |
|------|------|
| Django 5.1 | Web 框架 |
| Django REST Framework 3.15 | REST API |
| SQLite 3.x | 数据库（WAL 模式，零运维，可无缝切换 PostgreSQL） |
| PaddleOCR | 银行 PDF 流水 OCR 识别 |
| django-filter | 高级查询筛选 |

### 前端

| 技术 | 用途 |
|------|------|
| React 19 | UI 框架 |
| TypeScript 6 | 类型安全 |
| Vite 8 | 构建工具 |
| Ant Design 6 | 组件库（表格/菜单/表单） |
| TanStack Query 5 | 服务端状态管理 |
| TanStack Table 8 | 表格筛选/排序/列配置 |
| React Router 7 | SPA 路由 |
| Recharts 3 | 图表（饼图/柱状图/折线图） |
| Zustand 5 | 客户端状态管理 |

---

## 项目结构

```
PayCheck/
├── backend/                    # Django 后端
│   ├── apps/                   # 业务应用
│   │   ├── channels/           # 账单渠道管理
│   │   ├── transactions/       # 交易数据模型 + 标签表达式引擎
│   │   ├── ingest/             # 文件导入 & 解析器（支付宝/微信/BOC）
│   │   ├── analysis/           # 统计分析
│   │   └── ocr_service/        # OCR 异步服务（PaddleOCR 管线）
│   ├── config/                 # Django 配置
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── logging.py          # 日志配置（RotatingFileHandler）
│   │   └── exception_handler.py
│   ├── tests/                  # 测试（pytest + Django）
│   │   ├── unit/               # 单元测试
│   │   └── integration/        # 集成测试
│   ├── manage.py               # Django 管理入口
│   └── pyproject.toml
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── api/                # API 客户端
│   │   ├── components/         # 通用组件 & AppLayout
│   │   ├── pages/              # 页面组件
│   │   │   ├── DashboardPage   # 仪表盘首页
│   │   │   ├── ChannelPage     # 渠道数据表（通用，参数化渠道）
│   │   │   ├── ImportPage      # 文件导入页
│   │   │   ├── AnalysisPage    # 统计分析页
│   │   │   ├── PdfToCsvPage    # PDF 转 CSV 工具页
│   │   │   └── TagManagementPage  # 标签管理页
│   │   ├── hooks/              # 自定义 Hooks
│   │   ├── stores/             # Zustand 状态
│   │   └── types/              # TypeScript 类型定义
│   ├── vite.config.ts
│   └── package.json
├── design/                     # 架构设计文档
│   └── DESIGN.md
└── pyproject.toml              # Monorepo 工作空间锚点
```

---

## 前置依赖

- **Python**: 3.10 ~ 3.11（PaddlePaddle 兼容性要求）
- **Node.js**: 18+（前端构建）
- **GPU**（推荐）: NVIDIA GPU + CUDA 12.6，用于加速 OCR 推理
- **Package Manager**: [uv](https://docs.astral.sh/uv/)（Python）+ npm（Node.js）

> 无 GPU 也可运行，OCR 速度会明显降低但不影响功能。

---

## 快速开始

### 1. 安装 uv 和 Node.js

```bash
# Windows (PowerShell) — uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux — uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js: https://nodejs.org/ (推荐 18 LTS 或更高)
```

### 2. 克隆仓库

```bash
git clone https://github.com/TaoChenyue/PayCheck.git
cd PayCheck
```

### 3. 安装并启动后端

```bash
cd backend

# 安装依赖
uv sync

# 数据库迁移
uv run manage.py migrate

# 启动 Django 开发服务器
uv run manage.py runserver
```

后端运行在 http://localhost:8000

### 4. 安装并启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动 Vite 开发服务器
npm run dev
```

前端运行在 http://localhost:5173

### 5. 打开浏览器

访问 **http://localhost:5173** 即可使用。

---

## 功能特性

### 统一交易数据模型

三渠道（支付宝/微信/中国银行）导入的交易数据汇入统一的 `Transaction` 表，通过 `row_hash`（MD5）去重，`source_channel` + `source_id` 关联渠道源数据。前端查询以 `Transaction` 表为唯一入口，无需关心底层渠道数据表。

| 特性 | 说明 |
|------|------|
| 去重机制 | `row_hash` MD5 唯一约束（time\|amount\|counterparty\|platform） |
| 渠道追溯 | `source_channel` + `source_id` 反向关联 AlipayTx / WechatTx / BocTx |
| 字段并集 | 包含三渠道所有字段（13 个字段：platform, time, category, counterparty, description, amount, tx_type, payment_method, balance, currency, branch, cp_account, cp_bank） |

### 多平台账单解析

| 平台 | 文件格式 | 导入方式 | 编码处理 |
|------|---------|---------|---------|
| 支付宝 | `.csv` | Web 上传 | GBK → UTF-8 自动探测 |
| 微信支付 | `.xlsx` | Web 上传 | openpyxl 直接读取 |
| 中国银行 | `.pdf` / `.csv` | Web 上传 → ThreadPoolExecutor 异步 OCR | UTF-16 LE / UTF-8 自动探测 |

### 银行流水 OCR

- **PaddleOCR** 中文识别引擎 — ThreadPoolExecutor 异步任务，不阻塞前端
- **亮度分析法** — 自动检测表格边界并精确裁剪
- **Y 轴最近邻行分组** — 以 date 列文字 Y 坐标做锚点，其余列文字按距离最近邻归属到对应行
- **进度反馈** — 前端实时显示处理进度
- **布局注册表** — 支持 `BankLayout` 接口扩展（`layouts/boc.py` 实现中行布局）

### 内部转账过滤

自动识别并剔除不影响总资产的内部资金流动：

| 平台 | 判定规则 |
|------|---------|
| 支付宝 | `tx_type == "不计收支"` |
| 微信 | category 含"充值"/"提现"/"零钱" |

### 标签管理系统

完整的标签生命周期管理，支持单条和批量操作。

- **标签 CRUD** — `TagManagementPage` 提供标签的创建、重命名、删除
- **单条打标签** — 交易表格中点击标签列弹出 Popover，选择标签后保存（替换模式）
- **批量打标签** — 勾选多条交易 → 批量应用标签
- **标签筛选** — 按标签 ID 筛选交易（OR 逻辑，逗号分隔）

#### 标签表达式引擎

基于递归下降解析器的标签表达式引擎（`apps/transactions/tag_expr.py`），支持集合运算：

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `∪` | 并集 | `餐饮 ∪ 购物` → 有餐饮或购物标签的交易 |
| `∩` | 交集 | `餐饮 ∩ 报销` → 同时有餐饮和报销标签的交易 |
| `-` | 差集 | `全部 - 餐饮` → 所有交易排除餐饮标签 |
| `()` | 括号 | `(餐饮 ∪ 购物) ∩ 报销` |

- 编译为 SQLite 集合运算 SQL（UNION / INTERSECT / EXCEPT）
- 运算符优先级：`∩` > `∪` = `-`，左结合
- 提供 `validate_expression()` 校验 + `compile_expression()` 编译接口

### 高级筛选与搜索

`ChannelPage` 提供 10 维筛选面板（Collapse 折叠面板）：

| 筛选参数 | 字段 | 类型 |
|----------|------|------|
| 平台 | `platform` | alipay / wechat / boc |
| 交易类型 | `tx_type` | 支出 / 收入 / 转账 / 其他 |
| 时间范围 | `time_after`, `time_before` | 日期范围选择器 |
| 金额范围 | `amount_min`, `amount_max` | 数字输入 |
| 分类 | `category` | 文本（icontains 模糊匹配） |
| 交易对方 | `counterparty` | 文本（icontains 模糊匹配） |
| 标签 | `tag_ids` | 多选标签（OR 逻辑） |

- **搜索** — 关键字搜索交易对方或商品说明，输入防抖 300ms
- **分类/对方筛选** — 输入防抖 500ms
- **排序** — 支持按时间/金额/平台/类型/创建时间排序
- **一键清空** — "清空筛选"按钮重置所有条件

### 前端功能

- **仪表盘** — SummaryCards 统计卡片（总支出/总收入/月均支出）+ PlatformCharts 各平台消费对比
- **渠道数据表** — 支付宝/微信/中国银行三个独立视图，支持筛选、排序、列配置
- **交易详情抽屉** — 点击行弹出 Drawer，展示交易完整字段和标签
- **交易删除** — 单条删除确认弹窗，后端级联删除渠道表源数据
- **导入中心** — 多文件拖拽上传，ThreadPoolExecutor 异步处理，进度实时显示
- **统计分析** — 月度趋势/平台对比/类别分布图表（Recharts）
- **PDF→CSV 工具页** — 独立页面，银行 PDF 上传 → OCR 识别 → CSV 下载
- **标签管理页** — 标签创建/重命名/删除，支持搜索和排序
- **列显示配置** — "列显示"下拉菜单，勾选/取消列可见性
- **虚拟滚动** — 大数据量（pageSize ≥ 100）时启用 Ant Design virtual 模式
- **空状态引导** — EmptyState 组件，无数据时引导用户跳转导入页

### 异常处理

`config/exception_handler.py` — DRF 自定义异常处理器，所有异常转换为统一 JSON 格式：

```json
{
  "error": true,
  "code": "not_found | validation_error | server_error | ...",
  "message": "人类可读的错误描述",
  "detail": { ... }
}
```

| HTTP 状态码 | code | 中文消息 |
|-------------|------|---------|
| 400 | `validation_error` | 请求参数有误 |
| 401 | `unauthorized` | 未授权访问 |
| 403 | `forbidden` | 没有访问权限 |
| 404 | `not_found` | 请求的资源不存在 |
| 405 | `method_not_allowed` | 不支持的请求方法 |
| 429 | `rate_limited` | 请求过于频繁，请稍后重试 |
| 500 | `server_error` | 服务器内部错误 |

### 日志系统

`config/logging.py` — 双通道日志 + 辅助工具：

- **文件日志** — RotatingFileHandler，单文件 10MB，保留 5 份轮转备份（`log/paycheck.log`）
- **控制台输出** — DEBUG 模式下 paycheck logger 同时输出到 stderr
- **第三方库压制** — 自动静默 paddle/PIL/matplotlib/urllib3/chardet/fitz 等 10 个库的日志噪声
- **辅助工具** — `get_logger()` 模块日志器工厂、`log_time()` 上下文管理器、`log_execution_time()` 装饰器

### 性能优化

- **SQLite WAL 模式** — `PRAGMA journal_mode=WAL`，提升并发读写性能
- **数据库索引** — Transaction 表 9 个索引：
  - 单列索引：`platform`, `time`, `amount`, `tx_type`, `counterparty`, `category`
  - 复合索引：`(-time, platform)`, `(-time, tx_type)`
  - 唯一索引：`row_hash`（MD5 去重）
- **查询优化** — `prefetch_related("tags")` 预加载标签关联，避免 N+1

### Django Admin

`/admin/` 路径提供 Django 自带管理后台，已注册以下模型：

| 模型 | Admin 路径 |
|------|-----------|
| Transaction | `/admin/transactions/transaction/` |
| Tag | `/admin/transactions/tag/` |
| TransactionTag | `/admin/transactions/transactiontag/` |
| AlipayTx | `/admin/channels/alipaytx/` |
| WechatTx | `/admin/channels/wechattx/` |
| BocTx | `/admin/channels/boctx/` |
| ImportJob | `/admin/ingest/importjob/` |
| ImportFile | `/admin/ingest/importfile/` |

### 遗留数据库迁移

```bash
python manage.py migrate_legacy_db [--db-path <path>] [--dry-run]
```

从旧版 SQLite 数据库（`log/paycheck.db`）迁移到新版 Django ORM：

1. 读取旧 SQLite 数据 → JSON 中间格式
2. 映射 platform 字段（`"bank"` → `"boc"`）
3. Batch create Transaction 记录，MD5 去重
4. 验证总条数 + 总金额一致性

---

## API 接口

### 渠道数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/channels/alipay/` | 支付宝交易列表 |
| GET | `/api/channels/wechat/` | 微信交易列表 |
| GET | `/api/channels/boc/` | 中国银行交易列表 |
| GET | `/api/channels/{channel}/{id}/` | 单条交易详情 |

### 统一交易

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/transactions/` | 通用交易列表（分页，支持筛选/排序/搜索） |
| GET | `/api/transactions/{id}/` | 单条交易详情 |
| DELETE | `/api/transactions/{id}/` | 删除交易（级联删除渠道表源数据） |
| POST | `/api/transactions/{id}/tags/` | 设置单条交易标签（替换模式） |
| POST | `/api/transactions/batch-tags/` | 批量设置标签 |

### 标签管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tags/` | 标签列表 |
| POST | `/api/tags/` | 创建标签 |
| GET | `/api/tags/{id}/` | 标签详情 |
| PUT / PATCH | `/api/tags/{id}/` | 更新标签 |
| DELETE | `/api/tags/{id}/` | 删除标签 |

### 导入管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/import/upload/` | 上传账单文件（multipart，最多 20 个） |
| GET | `/api/import/jobs/` | 导入任务列表 |
| GET | `/api/import/jobs/{id}/` | 查询导入任务状态与进度 |
| GET | `/api/import/files/{id}/download/` | 下载文件（PDF 自动返回 OCR 生成的 CSV） |

### 统计分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/analysis/summary/` | 汇总统计（期间/总支出/总收入/月均/各平台统计/月度趋势/类别分布） |
| GET | `/api/analysis/monthly/?platform=` | 月度趋势数据（可按平台过滤） |
| GET | `/api/analysis/categories/?limit=20` | 类别分布数据（支持 Top N） |

---

## 开发指南

### 后端

```bash
cd backend
uv run manage.py runserver       # 开发服务器
uv run manage.py makemigrations  # 生成迁移
uv run manage.py migrate         # 执行迁移
uv run manage.py shell           # Django shell
uv run manage.py test            # Django 测试
# 或使用 pytest:
python -m pytest tests/ -v       # 运行全部测试
```

### 前端

```bash
cd frontend
npm run dev      # 开发服务器（HMR）
npm run build    # 生产构建
npm run lint     # 代码检查
npm run preview  # 预览生产构建
```

### Git 规范

- `feat/xxx` — 新功能分支
- `fix/xxx` — 修复分支
- 小步提交，保持提交历史清晰
- Worktree 放在 `.worktrees/`，已在 `.git/info/exclude` 忽略

---

## 许可

[MIT](LICENSE) © PayCheck Contributors
