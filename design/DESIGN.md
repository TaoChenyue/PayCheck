# PayCheck 架构设计：Django + React 前后端分离

> **作者**: 架构师
> **日期**: 2026-07-24
> **版本**: 1.0

---

## 目录

1. [概述与目标](#1-概述与目标)
2. [技术选型](#2-技术选型)
3. [项目结构](#3-项目结构)
4. [后端架构](#4-后端架构)
5. [前端架构](#5-前端架构)
6. [数据库设计](#6-数据库设计)
7. [API 接口设计](#7-api-接口设计)
8. [异步任务方案](#8-异步任务方案)
9. [现有代码迁移策略](#9-现有代码迁移策略)
10. [核心决策记录（ADR）](#10-核心决策记录adr)
11. [实施阶段划分](#11-实施阶段划分)
12. [附录：可选方案对比](#12-附录可选方案对比)

---

## 1. 概述与目标

### 1.1 背景

当前 PayCheck 是一个 PySide6 桌面 GUI 应用，功能完备但受限于桌面环境的部署和访问方式。需将其重构为 Web 应用，保留所有核心能力的同时获得以下收益：

- **随处访问**：浏览器即可使用，无需安装
- **多人协作**（远期）：可扩展为家庭/团队共享账单
- **移动端友好**：React 响应式 UI 可适应移动设备
- **数据安全**：数据存储在服务器端，不依赖本地文件系统

### 1.2 核心能力保留清单

| 现有能力 | 重构后方案 | 变更说明 |
|----------|-----------|---------|
| 支付宝 CSV 导入 | Web 上传 → 后端解析 | 文件来源从本地变为上传 |
| 微信 XLSX 导入 | Web 上传 → 后端解析 | 同上 |
| 银行 PDF OCR | Web 上传 → Celery 异步处理 | 后台任务替代阻塞 GUI |
| 内部转账过滤 | 后端解析阶段自动执行 | 无变化 |
| 摘要统计卡片 | React 组件渲染 | UI 从 Qt 迁移到 Web |
| 分渠道表格（筛选/排序） | TanStack Table | 功能增强 |
| 标签系统 | 后端 API + 前端交互 | 无变化 |
| OCR 流水线（PaddleOCR） | 复用现有代码，Celery 调用 | 核心逻辑不变 |

---

## 2. 技术选型

### 2.1 后端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| **Django** | 5.1+ | 成熟的 Web 框架，ORM 强大，生态丰富 |
| **Django REST Framework** | 3.15+ | REST API 标准方案，ViewSet/Serializer 加速开发 |
| **Celery** | 5.4+ | Python 生态最成熟的异步任务队列 |
| **Redis** | 7.x | Celery broker + 结果缓存 |
| **SQLite** | 3.x | 初期数据库，个人/小团队场景完全够用 |
| **Django Channels** | 4.x | WebSocket 支持，用于导入进度推送（可选） |

**为何选 Django 而非 FastAPI？**
- Django ORM 对复杂查询（聚合、分组、多表关联）的支持远超 SQLAlchemy 的声明式风格
- Django Admin 可用于初期数据管理和调试
- DRF 的 ViewSet + Router 模式减少 60% 样板代码
- 本项目数据操作为主（CRUD + 聚合），Django 的优势场景

**数据库从 SQLite 起步的理由：**
- 当前数据量预估：个人用户数年账单 < 10 万条，SQLite 完全胜任
- 零运维成本，备份仅需复制 `.db` 文件
- 内置 `json1` 扩展支持 JSON 字段
- 后续通过 `django.db.backends.postgresql` 一键切换 PostgreSQL

### 2.2 前端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| **React** | 19.x | 团队熟悉，生态最丰富 |
| **TypeScript** | 5.x | 类型安全，降低运行时错误 |
| **React Router** | 7.x | SPA 路由标准方案 |
| **TanStack Query** | 5.x | 服务端状态管理，缓存/重试/乐观更新 |
| **TanStack Table** | 8.x | 无头表格库，完美的筛选/排序/列配置 |
| **Ant Design** | 5.x | 企业级组件库，表格/表单/菜单开箱即用 |
| **Recharts** | 2.x | React 图表库，饼图/柱状图/折线图 |
| **Vite** | 6.x | 极速开发服务器和构建工具 |
| **Zustand** | 5.x | 轻量客户端状态管理（UI 状态） |

**为何选 Ant Design 而非 shadcn/ui？**
- Ant Design 的 Table 组件内置筛选、排序、列配置、导出——正切中本项目核心需求
- 手风琴 Menu 组件（`Menu` mode="inline"）直接可用
- shadcn/ui 的表格需要大量手动组装，开发效率差距明显

### 2.3 基础设施

| 技术 | 用途 |
|------|------|
| **uv** | Python 包管理（保持现有工具链） |
| **pnpm** | Node.js 包管理（推荐，兼容 npm） |
| **Docker Compose** | 开发环境一键启动（Django + Redis + Celery） |
| **GitHub Actions** | CI/CD |

---

## 3. 项目结构

```
PayCheck/                          # 仓库根目录（Monorepo）
├── backend/                       # Django 后端
│   ├── config/                    # Django 项目配置
│   │   ├── __init__.py
│   │   ├── settings.py            # 主配置
│   │   ├── urls.py                # 根 URL 路由
│   │   ├── wsgi.py
│   │   ├── asgi.py                # Channels ASGI
│   │   └── celery.py              # Celery 配置
│   ├── apps/
│   │   ├── channels/              # 账单渠道管理
│   │   │   ├── models.py          # AlipayTx, WechatTx, BocTx
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   └── admin.py
│   │   ├── ingest/                # 数据导入
│   │   │   ├── models.py          # ImportJob, ImportFile
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── parsers/           # 复用现有解析逻辑
│   │   │   │   ├── __init__.py
│   │   │   │   ├── alipay.py
│   │   │   │   ├── wechat.py
│   │   │   │   └── boc.py
│   │   │   ├── tasks.py           # Celery 异步任务
│   │   │   └── csv_utils.py
│   │   ├── transactions/          # 统一交易视图
│   │   │   ├── models.py          # Transaction (统一表)
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── filters.py         # DRF 筛选器
│   │   │   └── admin.py
│   │   ├── analysis/              # 统计分析
│   │   │   ├── views.py           # 聚合查询 API
│   │   │   ├── urls.py
│   │   │   └── stats.py           # 复用现有统计逻辑
│   │   └── ocr_service/           # OCR 服务封装
│   │       ├── tasks.py           # Celery OCR 任务
│   │       ├── engine.py          # 复用原 ocr/engine.py
│   │       ├── pipeline.py        # 复用原 ocr/pipeline.py
│   │       ├── pdf_render.py      # 复用原 ocr/pdf_render.py
│   │       └── layouts/           # 复用原 ocr/layouts/
│   ├── manage.py
│   ├── pyproject.toml             # 后端依赖
│   └── requirements.txt           # CI 兼容（由 pyproject.toml 导出）
├── frontend/                      # React 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/            # 布局组件
│   │   │   │   ├── AppLayout.tsx      # 整体布局（菜单+内容）
│   │   │   │   └── SideMenu.tsx       # 左侧手风琴菜单
│   │   │   ├── dashboard/         # 仪表盘
│   │   │   │   ├── SummaryCards.tsx    # 摘要卡片
│   │   │   │   └── PlatformCharts.tsx # 平台对比图表
│   │   │   ├── tables/            # 数据表格
│   │   │   │   ├── TransactionTable.tsx  # 通用交易表格
│   │   │   │   └── ChannelTable.tsx      # 渠道专属表格
│   │   │   ├── import/            # 导入页面
│   │   │   │   ├── FileUploader.tsx     # 拖拽上传区
│   │   │   │   └── ImportProgress.tsx   # 进度展示
│   │   │   └── common/            # 通用组件
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx      # 首页仪表盘
│   │   │   ├── ImportPage.tsx         # 数据导入页
│   │   │   ├── ChannelPage.tsx        # 渠道账单详情页
│   │   │   └── AnalysisPage.tsx       # 分析页
│   │   ├── hooks/                 # 自定义 Hooks
│   │   │   ├── useTransactions.ts     # TanStack Query hooks
│   │   │   ├── useChannels.ts
│   │   │   └── useImport.ts
│   │   ├── stores/                # Zustand 状态
│   │   │   └── uiStore.ts         # UI 状态（侧栏折叠等）
│   │   ├── api/                   # API 客户端
│   │   │   └── client.ts          # Axios 实例 + 拦截器
│   │   ├── types/                 # TypeScript 类型定义
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── src/                           # 保留原有桌面应用代码（不再维护）
├── docker-compose.yml             # 开发环境编排
├── .github/workflows/             # CI/CD
└── README.md
```

---

## 4. 后端架构

### 4.1 Django App 职责划分

```
┌─────────────────────────────────────────────────────────────┐
│                      Django 应用架构                         │
├─────────────┬─────────────┬──────────────┬─────────────────┤
│  channels   │   ingest    │ transactions │    analysis     │
│  (渠道管理)  │  (数据导入)  │  (统一视图)   │   (统计分析)     │
├─────────────┼─────────────┼──────────────┼─────────────────┤
│ AlipayTx    │ ImportJob   │ Transaction  │ 聚合查询 API     │
│ WechatTx    │ ImportFile  │ Tag          │ 月度统计 API     │
│ BocTx       │ Parsers     │ Transaction  │ 类别分布 API     │
│             │ Celery Task │  -Tag        │                 │
└─────────────┴─────────────┴──────────────┴─────────────────┘
         │             │              │              │
         └─────────────┴──────────────┴──────────────┘
                            │
                    ┌───────┴───────┐
                    │  ocr_service  │
                    │  (OCR 封装)   │
                    │  Celery Task  │
                    └───────────────┘
```

**职责说明：**

- **channels**：管理三个渠道的独立数据表。每个渠道表存储该渠道特有的全量字段（如银行有余额、币种、分行等，支付宝/微信没有）。渠道表是"数据源"，不作查询入口。

- **ingest**：处理文件上传→解析→入库的全流程。包含 Celery 任务用于 PDF→CSV 异步转换。解析器直接复用现有 `src/paycheck/ingest/parsers/` 代码，仅替换 `Transaction` dataclass 为 Django Model 序列化。

- **transactions**：统一的交易记录视图。包含去重逻辑（与现有 `time + amount + counterparty` 去重一致），提供 RESTful CRUD API 和标签管理 API。前端的数据展示和筛选均走此 app。

- **analysis**：聚合统计，从 `transactions` 表查询。复用现有 `stats.py` 的计算逻辑，但数据源从内存列表变为 Django ORM 查询。

- **ocr_service**：对现有 `src/paycheck/ocr/` 目录的直接封装。Celery 任务中通过 `subprocess` 或直接 `import` 调用现有 OCR 流水线。

### 4.2 数据流设计

```
用户上传文件                    后台处理                          前端展示
┌──────────────┐    ┌──────────────────────────────┐    ┌──────────────────┐
│ 前端拖拽区域  │───▶│ POST /api/import/upload/      │    │                  │
│              │    │   ↓                           │    │                  │
│ 多文件选择    │    │ 保存文件 → 创建 ImportJob      │    │                  │
└──────────────┘    │   ↓                           │    │                  │
                    │ Celery 异步任务:               │    │                  │
                    │   ① 判断文件类型 (CSV/XLSX/PDF)│    │                  │
                    │   ② CSV/XLSX → 解析器 →        │◀──▶│ API 轮询/WebSocket│
                    │      写入 channels 表            │    │  (进度更新)       │
                    │   ③ PDF → OCR 流水线 →         │    │                  │
                    │      写入 boc 表                 │    │                  │
                    │   ④ 去重 → 同步到 transactions  │    │                  │
                    │   ⑤ 更新 ImportJob 状态         │    │                  │
                    └──────────────────────────────┘    └──────────────────┘
                                                              │
                                                              ▼
                                                    ┌──────────────────┐
                                                    │ GET /api/transactions/ │
                                                    │  (含筛选/排序/分页)    │
                                                    │                      │
                                                    │ GET /api/analysis/    │
                                                    │  (聚合统计数据)        │
                                                    └──────────────────┘
```

---

## 5. 前端架构

### 5.1 组件树

```
<App>
└── <AppLayout>
    ├── <SideMenu>                         // 左侧手风琴菜单
    │   ├── Menu.SubMenu "数据管理"
    │   │   ├── Menu.Item "数据导入" → /import
    │   │   ├── Menu.Item "支付宝账单" → /channels/alipay
    │   │   ├── Menu.Item "微信账单" → /channels/wechat
    │   │   └── Menu.Item "银行账单" → /channels/boc
    │   └── Menu.SubMenu "分析"
    │       ├── Menu.Item "概览仪表盘" → /dashboard
    │       └── Menu.Item "详细分析" → /analysis
    └── <main>                             // 右侧内容区（React Router）
        ├── Route "/dashboard" → <DashboardPage>
        │   ├── <SummaryCards />            // 总支出/收入/月均 卡片
        │   └── <PlatformCharts />          // 月度趋势 + 平台对比
        ├── Route "/import" → <ImportPage>
        │   ├── <FileUploader />            // 拖拽上传 + 渠道选择
        │   └── <ImportProgress />          // 异步任务进度条
        ├── Route "/channels/:channel" → <ChannelPage>
        │   └── <ChannelTable />            // TanStack Table（筛选/排序）
        └── Route "/analysis" → <AnalysisPage>
            ├── <SummaryCards />
            └── <CategoryPieChart />        // 类别饼图 + 排名
```

### 5.2 路由设计

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | 重定向 → `/dashboard` | 默认首页 |
| `/dashboard` | `DashboardPage` | 概览仪表盘 |
| `/import` | `ImportPage` | 数据导入 |
| `/channels/alipay` | `ChannelPage` | 支付宝账单 |
| `/channels/wechat` | `ChannelPage` | 微信账单 |
| `/channels/boc` | `ChannelPage` | 银行账单 |
| `/analysis` | `AnalysisPage` | 详细分析 |

### 5.3 状态管理方案

双层状态策略：

| 状态类型 | 管理工具 | 内容 |
|---------|---------|------|
| **服务端状态** | TanStack Query | 交易数据、统计数据、渠道数据（自动缓存/重试/失效） |
| **客户端状态** | Zustand | UI 状态：侧栏折叠、表格列显示偏好、筛选条件暂存 |

**为什么不用 Redux？** 本项目状态以服务端数据为主，TanStack Query 的缓存和自动刷新机制比手写 Redux 中间件更适合。Zustand 仅需管理少量的 UI 状态，避免了 Redux 的样板代码。

---

## 6. 数据库设计

### 6.1 设计原则

1. **渠道独立表**：支付宝、微信、银行各有独立的表，保留各渠道特有字段
2. **统一交易表**：去重后写入 `transactions` 表，作为前端查询的唯一入口
3. **SQLite 优先**：初期使用 SQLite，通过 Django ORM 保持 PostgreSQL 兼容
4. **统一去重键**：`(time, amount, counterparty)` — 与现有逻辑保持一致

### 6.2 表结构

#### `alipay_transactions` / `wechat_transactions` / `boc_transactions`

```sql
-- 支付宝（字段最少，渠道特有字段少）
CREATE TABLE alipay_transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    time          TEXT NOT NULL,        -- 交易时间
    category      TEXT DEFAULT '',      -- 交易分类
    counterparty  TEXT DEFAULT '',      -- 交易对方
    description   TEXT DEFAULT '',      -- 商品说明
    amount        REAL NOT NULL,        -- 金额（正数）
    tx_type       TEXT DEFAULT '支出',  -- 支出/收入/不计收支
    payment_method TEXT DEFAULT '',     -- 支付方式
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(time, amount, counterparty)
);

-- 微信（字段与支付宝相同，但渠道标识为 wechat）
CREATE TABLE wechat_transactions ( /* 同 alipay_transactions */ );

-- 银行（字段最多，含余额/币种/分行等）
CREATE TABLE boc_transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    time          TEXT NOT NULL,        -- 交易时间
    category      TEXT DEFAULT '',      -- tx_name → 交易名称
    counterparty  TEXT DEFAULT '',      -- 对方名称
    description   TEXT DEFAULT '',      -- memo → 备注
    amount        REAL NOT NULL,        -- 金额
    tx_type       TEXT DEFAULT '支出',  -- 支出/收入
    payment_method TEXT DEFAULT '',     -- channel → 渠道
    balance       REAL DEFAULT 0,       -- 余额
    currency      TEXT DEFAULT '',      -- 币种
    branch        TEXT DEFAULT '',      -- 分行
    cp_account    TEXT DEFAULT '',      -- 对方账号
    cp_bank       TEXT DEFAULT '',      -- 对方银行
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(time, amount, counterparty)
);
```

#### `transactions`（统一交易表，前端查询入口）

```sql
CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,      -- 'alipay' | 'wechat' | 'bank'
    time            TEXT NOT NULL,
    category        TEXT DEFAULT '',
    counterparty    TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    amount          REAL NOT NULL,
    tx_type         TEXT DEFAULT '支出',
    payment_method  TEXT DEFAULT '',
    balance         REAL DEFAULT 0,
    currency        TEXT DEFAULT '',
    branch          TEXT DEFAULT '',
    cp_account      TEXT DEFAULT '',
    cp_bank         TEXT DEFAULT '',
    source_channel  TEXT NOT NULL,      -- 'alipay' | 'wechat' | 'boc'
    source_id       INTEGER NOT NULL,   -- 渠道表外键 id
    created_at      TEXT DEFAULT (datetime('now')),
    row_hash        TEXT NOT NULL UNIQUE, -- MD5(time+amount+counterparty+platform)
    -- 索引
    FOREIGN KEY (source_channel, source_id) — 逻辑外键，SQLite 不支持但 Django ORM 可模拟
);
CREATE INDEX idx_transactions_platform ON transactions(platform);
CREATE INDEX idx_transactions_time ON transactions(time);
CREATE INDEX idx_transactions_amount ON transactions(amount);
CREATE INDEX idx_transactions_tx_type ON transactions(tx_type);
```

**去重键 `row_hash`**：`MD5(f"{time}|{amount:.2f}|{counterparty}|{platform}")`，确保同一笔交易不会被重复导入。

#### `tags` / `transaction_tags`（与现有结构一致）

```sql
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE transaction_tags (
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    tag_id         INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (transaction_id, tag_id)
);
```

#### `import_jobs` / `import_files`（新增，追踪导入状态）

```sql
CREATE TABLE import_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    status      TEXT DEFAULT 'pending',  -- pending/processing/completed/failed
    total_files INTEGER DEFAULT 0,
    processed   INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE import_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES import_jobs(id),
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,           -- 'alipay_csv' | 'wechat_xlsx' | 'boc_pdf' | 'boc_csv'
    status      TEXT DEFAULT 'pending',  -- pending/processing/completed/failed
    error_msg   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

### 6.3 ER 图

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│alipay_tx     │    │wechat_tx     │    │boc_tx        │
│ (渠道表)      │    │ (渠道表)      │    │ (渠道表)      │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       │   去重后同步        │                   │
       └───────────────────┼───────────────────┘
                           ▼
                  ┌────────────────┐
                  │  transactions  │
                  │   (统一表)      │
                  └───────┬────────┘
                          │ M:N
                  ┌───────┴────────┐
                  │ transaction_   │
                  │    tags        │
                  └───────┬────────┘
                          │
                  ┌───────┴────────┐
                  │     tags       │
                  └────────────────┘

┌──────────────┐
│  import_jobs │
└──────┬───────┘
       │ 1:N
┌──────┴───────┐
│ import_files │
└──────────────┘
```

---

## 7. API 接口设计

### 7.1 接口总览

| Method | Endpoint | 说明 | App |
|--------|----------|------|-----|
| `GET` | `/api/transactions/` | 统一交易列表（分页+筛选） | transactions |
| `GET` | `/api/transactions/{id}/` | 单条交易详情 | transactions |
| `DELETE` | `/api/transactions/{id}/` | 删除交易（级联删除渠道表） | transactions |
| `GET` | `/api/channels/alipay/` | 支付宝渠道交易列表 | channels |
| `GET` | `/api/channels/wechat/` | 微信渠道交易列表 | channels |
| `GET` | `/api/channels/boc/` | 银行渠道交易列表 | channels |
| `POST` | `/api/import/upload/` | 上传文件（支持多文件） | ingest |
| `GET` | `/api/import/jobs/` | 导入任务列表 | ingest |
| `GET` | `/api/import/jobs/{id}/` | 导入任务状态/进度 | ingest |
| `WS` | `/ws/import/{job_id}/` | 导入进度实时推送（可选） | ingest |
| `GET` | `/api/analysis/summary/` | 聚合摘要统计 | analysis |
| `GET` | `/api/analysis/monthly/` | 月度趋势数据 | analysis |
| `GET` | `/api/analysis/categories/` | 类别分布数据 | analysis |
| `GET` | `/api/tags/` | 标签列表 | transactions |
| `POST` | `/api/tags/` | 创建标签 | transactions |
| `PUT` | `/api/tags/{id}/` | 更新标签 | transactions |
| `DELETE` | `/api/tags/{id}/` | 删除标签 | transactions |
| `POST` | `/api/transactions/{id}/tags/` | 设置交易标签 | transactions |
| `POST` | `/api/transactions/batch-tags/` | 批量设置标签 | transactions |

### 7.2 核心接口详情

#### GET /api/transactions/

查询参数：

```
?platform=alipay|wechat|bank    # 渠道筛选
&tx_type=支出|收入              # 收支类型
&time_after=2024-01-01          # 起始日期
&time_before=2024-12-31         # 结束日期
&amount_min=0                   # 最小金额
&amount_max=1000                # 最大金额
&category=餐饮                  # 分类筛选（模糊匹配）
&counterparty=某某              # 对方筛选（模糊匹配）
&tag_ids=1,2,3                  # 标签筛选（OR 逻辑）
&search=关键词                  # 全局搜索（counterparty + description）
&ordering=-time                 # 排序（-time 降序）
&page=1                         # 分页页码
&page_size=50                   # 每页条数（默认50，最大200）
```

响应：

```json
{
  "count": 1234,
  "next": "http://.../?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "platform": "alipay",
      "time": "2024-01-15 12:30:00",
      "category": "餐饮美食",
      "counterparty": "某某餐厅",
      "description": "午餐消费",
      "amount": 36.50,
      "tx_type": "支出",
      "payment_method": "花呗",
      "balance": 0,
      "currency": "",
      "branch": "",
      "cp_account": "",
      "cp_bank": "",
      "tags": [{"id": 1, "name": "餐饮"}],
      "created_at": "2024-01-15T12:30:00Z"
    }
  ]
}
```

#### POST /api/import/upload/

请求：`multipart/form-data`

```
channel: "alipay" | "wechat" | "boc"  # 必选，指定渠道类型
files: [file1.csv, file2.xlsx, ...]    # 多文件，最多 20 个
```

响应：

```json
{
  "job_id": 42,
  "status": "processing",
  "total_files": 5,
  "files": [
    {"id": 101, "filename": "alipay_2024.csv", "status": "pending"},
    {"id": 102, "filename": "wechat_2024.xlsx", "status": "pending"}
  ]
}
```

#### GET /api/analysis/summary/

响应：

```json
{
  "period": {"start": "2023-01", "end": "2024-12"},
  "summary": {
    "total_expense": 45678.90,
    "total_income": 120000.00,
    "total_count": 1234,
    "monthly_avg": 1903.29,
    "wechat_total": 15000.00,
    "alipay_total": 20000.00,
    "bank_total": 10678.90,
    "wechat_count": 500,
    "alipay_count": 600,
    "bank_count": 134
  },
  "monthly": [
    {"month": "2024-01", "expense": 3500.00, "count": 120,
     "wechat": 1200.00, "alipay": 1800.00, "bank": 500.00}
  ],
  "categories": [
    {"name": "餐饮", "amount": 8000.00, "count": 300, "pct": 17.5}
  ],
  "generated_at": "2024-01-15T12:30:00Z"
}
```

### 7.3 数据写入流程

```
POST /api/import/upload/
  │
  ├─ 1. 创建 ImportJob (status=pending)
  ├─ 2. 保存文件到 MEDIA_ROOT/uploads/{job_id}/
  ├─ 3. 创建 ImportFile 记录
  ├─ 4. 调用 Celery task: process_import(job_id)
  └─ 5. 返回 job_id + 状态
    
Celery Task: process_import(job_id)
  │
  ├─ For each ImportFile:
  │   ├─ CSV/XLSX: parse_file() → channel_tx INSERT
  │   └─ PDF: run_ocr_pipeline() → CSV → channel_tx INSERT
  │
  ├─ 去重: 计算 row_hash, INSERT OR IGNORE into transactions
  ├─ 更新 ImportJob 进度
  └─ 更新 ImportJob.status = 'completed'
```

---

## 8. 异步任务方案

### 8.1 方案选择

| 方案 | 复杂度 | 可靠性 | 进度推送 | 选型 |
|------|--------|--------|---------|------|
| Celery + Redis | 中 | 高 | WebSocket/轮询 | ✅ **推荐** |
| Django Q | 低 | 中 | 轮询 | ❌ 社区活跃度低 |
| Dramatiq | 中 | 高 | 无内置 | ❌ 缺少 Django 集成 |
| Threading (同步) | 低 | 低 | 无 | ❌ 阻塞请求 |

**选择 Celery 的理由：**
- Python 生态最成熟的异步任务队列
- 内置重试、超时、任务链（Chain/Group）
- Django 集成成熟（`django-celery-results`）
- 支持任务优先级，OCR 任务可设为低优先级

### 8.2 Celery 任务定义

```python
# backend/apps/ingest/tasks.py

from celery import shared_task
from celery.result import AsyncResult

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_import_file(self, import_file_id: int):
    """处理单个导入文件（CSV/XLSX 解析）"""
    # 1. 更新状态为 processing
    # 2. 调用对应解析器
    # 3. 写入渠道表
    # 4. 同步到 transactions 表
    # 5. 更新 ImportFile 状态

@shared_task(bind=True, max_retries=1, time_limit=3600)
def process_pdf_ocr(self, import_file_id: int):
    """PDF → OCR → CSV → 入库（耗时任务，1小时超时）"""
    # 1. 调用现有 OCR 流水线: pdf_to_images() → images_to_csv()
    # 2. 解析生成的 CSV → boc_tx INSERT
    # 3. 同步到 transactions 表

@shared_task
def process_import_job(job_id: int):
    """编排导入任务：按文件类型分发到对应子任务"""
    # 1. 获取 ImportJob 的文件列表
    # 2. 对 PDF 文件分发 process_pdf_ocr
    # 3. 对 CSV/XLSX 文件分发 process_import_file
    # 4. 使用 Celery Chord 等待所有子任务完成
    # 5. 更新 ImportJob 状态
```

### 8.3 进度推送方案

**推荐：前端轮询（简化实现）**

```
前端: GET /api/import/jobs/{id}/ (每 2 秒轮询)
      ↓
后端: 返回 ImportJob 的 processed/total_files 进度
```

**可选升级：WebSocket 推送**

```
前端: 连接 /ws/import/{job_id}/
      ↓
Celery: task_postrun 信号 → Channels 推送进度更新
      ↓
前端: 接收实时进度 + 完成通知
```

初期使用轮询方案，WebSocket 在后续迭代中添加。

### 8.4 OCR 管线复用方案

```
现有代码: src/paycheck/ocr/
  ├── engine.py      →  backend/apps/ocr_service/engine.py    (直接复制)
  ├── pipeline.py    →  backend/apps/ocr_service/pipeline.py   (直接复制)
  ├── pdf_render.py  →  backend/apps/ocr_service/pdf_render.py (直接复制)
  └── layouts/       →  backend/apps/ocr_service/layouts/      (直接复制)

依赖要求（在 backend/pyproject.toml 中新增）:
  - paddleocr >= 3.6.0
  - PyMuPDF
  - opencv-python
  - Pillow
  - torch
```

**注意**：OCR 依赖较重（PaddleOCR + PyTorch ~2GB），建议在 Celery worker 独立的 Docker 容器中运行，与 Django 应用容器分开部署。

---

## 9. 现有代码迁移策略

### 9.1 迁移清单

| 现有模块 | 迁移方式 | 目标位置 | 修改内容 |
|---------|---------|---------|---------|
| `core/models.py` | 改为 Django Model | `apps/transactions/models.py` | dataclass → `models.Model` |
| `core/constants.py` | 保留为常量模块 | `apps/transactions/constants.py` | 无实质修改 |
| `ingest/parsers/alipay.py` | 直接复用 | `apps/ingest/parsers/alipay.py` | 返回值从 `Transaction` dataclass 改为 `dict` |
| `ingest/parsers/wechat.py` | 直接复用 | `apps/ingest/parsers/wechat.py` | 同上 |
| `ingest/parsers/boc.py` | 直接复用 | `apps/ingest/parsers/boc.py` | 同上 |
| `ingest/scanner.py` | 不再需要 | — | Web 上传替代目录扫描 |
| `ingest/csv_utils.py` | 直接复用 | `apps/ingest/csv_utils.py` | 无修改 |
| `ocr/engine.py` | 直接复用 | `apps/ocr_service/engine.py` | 无修改 |
| `ocr/pipeline.py` | 直接复用 | `apps/ocr_service/pipeline.py` | 输出路径适配 |
| `ocr/pdf_render.py` | 直接复用 | `apps/ocr_service/pdf_render.py` | 无修改 |
| `ocr/layouts/` | 直接复用 | `apps/ocr_service/layouts/` | 无修改 |
| `storage/database.py` | 重写 | Django ORM | 原生 SQL → ORM 查询 |
| `analysis/stats.py` | 部分复用 | `apps/analysis/stats.py` | 内存计算 → ORM 聚合查询 |
| `core/tag_expr.py` | 保留 | `apps/transactions/tag_expr.py` | 无修改 |

### 9.2 不需要迁移的模块

| 模块 | 原因 |
|------|------|
| `gui/` (全部) | PySide6 GUI 被 React 前端替代 |
| `analysis/` 中的图表生成逻辑 | 图表由前端 Recharts 渲染 |
| `__main__.py` | Django 有自己的 manage.py |

### 9.3 数据库迁移路径

现有 `paycheck.db` 中的交易数据需迁移到新的 Django schema：

```
① 导出: 现有 SQLite → JSON 中间格式
② 清洗: platform 字段映射: "bank" → "boc"
③ 导入: JSON → Django ORM bulk_create
④ 验证: 对比总条数 + 汇总金额
```

可在 Django management command (`migrate_legacy_db`) 中实现一键迁移。

---

## 10. 核心决策记录（ADR）

### ADR-001: 渠道独立表 vs 单表 + JSON 字段

**背景**：三个渠道的字段结构不同（银行有余额/币种/分行等 13 个字段，支付宝/微信只有 8 个）。

**选项**：
- A. 渠道独立表（alipay_tx, wechat_tx, boc_tx）+ 统一视图 transactions
- B. 单表 + JSON 扩展字段（所有渠道存同一张表，渠道特有字段放 JSON）

**决策**：选择 **A（渠道独立表 + 统一视图）**

**理由**：
- 渠道独立表保持数据纯净，不对渠道特有字段做裁剪
- JSON 字段无法建立索引，查询效率差
- 统一 transactions 表为前端提供一致的查询接口
- 新增渠道时只需新建一张表 + 一条同步规则，不影响现有结构

### ADR-002: Celery vs 同步线程

**决策**：选择 **Celery + Redis**

**理由**：
- PDF OCR 可能耗时数十分钟，必须异步处理
- Celery 提供任务重试、超时控制、进度追踪
- 方便后续扩展（定时清理临时文件、自动备份等）
- 开销可控：Redis 额外占用 ~30MB 内存

### ADR-003: TanStack Table vs AG Grid

**决策**：选择 **TanStack Table**

**理由**：
- 无头设计：完全控制渲染，与 Ant Design 集成无冲突
- 免费 MIT 许可（AG Grid 社区版功能受限）
- 8.x 版本内置筛选/排序/分页/列拖拽
- 包体积小（~10KB gzipped vs AG Grid ~200KB）

### ADR-004: SQLite 起步 vs 直接上 PostgreSQL

**决策**：**SQLite 起步，通过 Django ORM 保持 PostgreSQL 兼容**

**理由**：
- 个人使用场景，数据量 < 10 万条/年，SQLite 可支撑 10 年以上
- 零运维成本：无需安装/配置数据库服务
- Docker Compose 可一键切换 PostgreSQL（仅需改 DATABASE_URL）
- Django ORM 屏蔽 95% 的数据库差异

---

## 11. 实施阶段划分

### 第一阶段：后端核心（2-3 周）

```
1. 初始化 Django 项目结构
2. 创建 channels app：3 张渠道表 + DRF ViewSet
3. 创建 transactions app：统一表 + 标签表 + 去重逻辑
4. 迁移现有解析器到 ingest app
5. 文件上传 API
6. Celery 集成 + OCR 任务
7. 分析 API（聚合统计）
```

### 第二阶段：前端核心（2-3 周）

```
1. Vite + React + TypeScript 项目初始化
2. Ant Design 布局 + 手风琴菜单
3. 仪表盘页面（摘要卡片 + 图表）
4. 渠道账单页面（TanStack Table）
5. 数据导入页面（拖拽上传 + 进度）
6. 标签管理交互
7. API 客户端 + TanStack Query 集成
```

### 第三阶段：集成与优化（1-2 周）

```
1. 端到端流程联调
2. 现有数据迁移工具
3. Docker Compose 开发环境
4. 性能优化（查询索引、分页）
5. 错误处理 + 用户提示
```

---

## 12. 附录：可选方案对比

### 方案 A：Django + React（✅ 推荐）

- **后端**：Django + DRF + Celery + SQLite
- **前端**：React + TypeScript + Ant Design + TanStack Table
- **优点**：Django ORM 查询能力强，Ant Design Table 开箱即用
- **缺点**：初期需同时维护 Python 和 Node.js 环境

### 方案 B：FastAPI + React

- **后端**：FastAPI + SQLAlchemy + Celery + SQLite
- **前端**：同方案 A
- **优点**：异步原生支持，API 文档自动生成
- **缺点**：SQLAlchemy 复杂查询代码量大，缺少 Django Admin

### 方案 C：Next.js 全栈

- **后端**：Next.js API Routes + Prisma + SQLite
- **前端**：Next.js + React Server Components
- **优点**：单一语言/项目，部署简单
- **缺点**：OCR 必须通过子进程调用 Python，增加运维复杂度

### 推荐结论

**方案 A（Django + React）** 是平衡性最佳的选择：
- 现有 Python 代码（解析器 + OCR）可直接复用
- Django ORM 对聚合统计查询有天然优势
- Ant Design 组件库完美匹配数据密集型应用的 UI 需求
- 后续扩展到 PostgreSQL 零代码修改

---

> **文档结束**。本设计将作为后续开发的指导基线，重大变更需更新对应的 ADR 记录。
