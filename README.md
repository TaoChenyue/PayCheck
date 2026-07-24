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
- **自动 OCR** — 基于 PaddleOCR 的银行流水 PDF 识别管线，Celery 异步处理
- **智能过滤** — 自动剔除"充值/提现/零钱"等内部转账，还原真实消费
- **Web 界面** — React 单页应用，左侧手风琴菜单，响应式布局
- **分渠道管理** — 支付宝、微信、中国银行三个独立数据表，支持筛选排序和列配置

---

## 技术架构

```
┌───────────────────────┐     ┌──────────────────────────────────┐
│     React 前端         │     │        Django 后端                │
│  (Vite + Ant Design)  │◄───►│  (DRF + Celery + SQLite)         │
│  localhost:5173       │ API │  localhost:8000                  │
└───────────────────────┘     └──────────────┬───────────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │  Celery Worker   │
                                    │  (SQLite Broker) │
                                    │  (PDF OCR 异步)  │
                                    └─────────────────┘
```

### 后端

| 技术 | 用途 |
|------|------|
| Django 5.1 | Web 框架 |
| Django REST Framework 3.15 | REST API |
| Celery 5.4 | 异步任务队列（PDF OCR） |
| SQLite 3.x | 数据库 + Celery broker（零运维，可无缝切换 PostgreSQL） |
| PaddleOCR | 银行 PDF 流水 OCR 识别 |

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
│   │   ├── celery.py           # Celery 配置
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
│   │   │   └── AnalysisPage    # 统计分析页
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

### 4. 启动 Celery Worker（另开终端）

```bash
cd backend
uv run celery -A config worker --loglevel=info --pool=solo
```

### 5. 安装并启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动 Vite 开发服务器
npm run dev
```

前端运行在 http://localhost:5173

### 6. 打开浏览器

访问 **http://localhost:5173** 即可使用。

---

## 功能特性

### 多平台账单解析

| 平台 | 文件格式 | 导入方式 | 编码处理 |
|------|---------|---------|---------|
| 支付宝 | `.csv` | Web 上传 | GBK → UTF-8 自动探测 |
| 微信支付 | `.xlsx` | Web 上传 | openpyxl 直接读取 |
| 中国银行 | `.pdf` | Web 上传 → Celery 异步 OCR | UTF-16 LE / UTF-8 自动探测 |

### 银行流水 OCR

- **PaddleOCR** 中文识别引擎 — Celery 异步任务，不阻塞前端
- **亮度分析法** — 自动检测表格边界并精确裁剪
- **进度反馈** — 前端实时显示处理进度
- **布局注册表** — 新增银行只需实现 `BankLayout` 接口并注册

### 内部转账过滤

自动识别并剔除不影响总资产的内部资金流动：

| 平台 | 判定规则 |
|------|---------|
| 支付宝 | `tx_type == "不计收支"` |
| 微信 | category 含"充值"/"提现"/"零钱" |

### 前端功能

- **仪表盘** — 总支出 / 总收入 / 月均支出 / 各平台消费统计
- **渠道数据表** — 支付宝 / 微信 / 中国银行三个独立视图，支持筛选、排序、列配置
- **导入中心** — 多文件上传，异步处理，进度实时显示
- **统计分析** — 月度趋势 / 平台对比 / 类别分布图表

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/channels/` | 渠道列表 |
| GET | `/api/channels/{id}/` | 渠道详情 |
| GET | `/api/transactions/` | 交易列表（支持筛选/排序/分页） |
| POST | `/api/ingest/upload/` | 上传账单文件 |
| POST | `/api/ingest/import/` | 触发导入任务 |
| GET | `/api/ingest/tasks/{id}/` | 查询异步任务状态 |
| GET | `/api/analysis/summary/` | 汇总统计数据 |
| GET | `/api/analysis/monthly/` | 月度趋势数据 |
| GET | `/api/analysis/category/` | 类别分布数据 |

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

### 新增银行支持

1. `backend/apps/ocr_service/layouts/` — 实现 `BankLayout` 接口
2. `backend/apps/ingest/parsers/` — 实现解析器
3. 注册布局并更新渠道配置

### Git 规范

- `feat/xxx` — 新功能分支
- `fix/xxx` — 修复分支
- 小步提交，保持提交历史清晰
- Worktree 放在 `.worktrees/`，已在 `.git/info/exclude` 忽略

---

## 许可

[MIT](LICENSE) © PayCheck Contributors
