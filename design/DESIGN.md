# PayCheck 核心包迁移与版本更新设计

> **作者**: 架构师
> **日期**: 2026-07-25
> **版本**: 1.1
> **关联 Issue**: TCY-37

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [现状分析](#2-现状分析)
3. [迁移方案设计](#3-迁移方案设计)
4. [版本号更新方案](#4-版本号更新方案)
5. [文档刷新策略](#5-文档刷新策略)
6. [测试迁移策略](#6-测试迁移策略)
7. [实施步骤](#7-实施步骤)
8. [核心决策记录（ADR）](#8-核心决策记录adr)
9. [风险与回滚](#9-风险与回滚)

---

## 1. 背景与目标

### 1.1 问题陈述

当前 PayCheck 项目在仓库根目录保留了一个 Python 包项目（`src/paycheck/` + 根 `pyproject.toml`），这是 Phase 1-3 重构过程中遗留的旧架构层。该包项目包含：

- **已迁移代码**：解析器、OCR 管线、统计分析等已完整迁移至 `backend/apps/` 并在生产中使用
- **未迁移代码**：日志工具（`core/log.py`）、CLI 入口（`__main__.py`）、旧存储层（`storage/database.py`）
- **重复常量**：`core/constants.py` 与 `backend/apps/transactions/constants.py` 功能重叠

这使得项目处于"双架构并存"状态，增加维护负担和认知成本。

### 1.2 目标

1. **清理旧包**：移除 `src/paycheck/` Python 包，消除双架构并存
2. **迁移剩余有用代码**：将 `core/log.py` 适配后迁入 `backend/config/`
3. **版本号统一**：根项目、后端、README 版本号统一更新至 `1.0.1`
4. **文档刷新**：README、DESIGN.md 反映真实项目结构
5. **测试路径修正**：将 `tests/` 中的 import 从 `paycheck.*` 切换到 `backend.*`

---

## 2. 现状分析

### 2.1 当前项目结构

```
PayCheck/
├── pyproject.toml              # 根包配置（定义 paycheck 包，version=1.0.0）
├── README.md                   # 版本徽章: 1.0.0
├── src/
│   └── paycheck/               # ★ 待移除的旧核心包
│       ├── __init__.py         # 空文件
│       ├── __main__.py         # CLI 入口（打印启动提示）
│       ├── core/
│       │   ├── constants.py    # 字段常量（与 backend 重叠）
│       │   ├── log.py          # ★ 有用，待迁移
│       │   ├── models.py       # Transaction dataclass（已被 Django Model 替代）
│       │   └── tag_expr.py     # 标签表达式（已迁移到 backend）
│       ├── ingest/
│       │   ├── csv_utils.py    # CSV 解析（已迁移到 backend）
│       │   ├── scanner.py      # 目录扫描（CLI 专属，Web 不再需要）
│       │   └── parsers/        # 解析器（已迁移到 backend，并从 dataclass 重构为 dict）
│       ├── ocr/                # OCR 管线（已迁移到 backend）
│       ├── analysis/           # 统计分析（已迁移到 backend）
│       └── storage/            # SQLite 存储层（已被 Django ORM 替代）
├── backend/
│   ├── pyproject.toml          # 后端独立包，version=0.1.0
│   └── apps/
│       ├── ingest/parsers/     # 解析器（已从 src/ 迁入，inlined 常量）
│       ├── ocr_service/        # OCR 管线（已从 src/ 迁入）
│       ├── analysis/           # 统计分析（Django ORM 重写）
│       ├── transactions/       # 标签表达式 + 常量（已从 src/core/ 迁入）
│       └── channels/           # 渠道管理
└── tests/
    ├── unit/
    │   ├── test_csv_utils.py   # import paycheck.ingest.csv_utils ← 待修正
    │   └── test_tag_expr.py    # import paycheck.core.tag_expr ← 待修正
    └── integration/
        └── test_database.py    # import paycheck.storage.database ← 待重写
```

### 2.2 代码重叠分析

| src/paycheck/ 模块 | backend/ 对应位置 | 重叠状态 | 操作 |
|---|---|---|---|
| `core/constants.py` | `apps/transactions/constants.py` | 部分重叠（backend 版本更精简） | 废弃 src 版本 |
| `core/models.py` | `apps/transactions/models.py` | 已替代（dataclass → Django Model） | 废弃 |
| `core/tag_expr.py` | `apps/transactions/tag_expr.py` | 完整迁移 | 废弃 src 版本 |
| `core/log.py` | 无 | **未迁移** | ★ 迁移至 `backend/config/logging.py` |
| `ingest/parsers/*` | `apps/ingest/parsers/*` | 已迁移（含重构：返回 dict） | 废弃 src 版本 |
| `ingest/csv_utils.py` | `apps/ingest/csv_utils.py` | 完全相同 | 废弃 src 版本 |
| `ingest/scanner.py` | 无 | 无需迁移（CLI 专属） | 废弃 |
| `ocr/*` | `apps/ocr_service/*` | 完整迁移 | 废弃 src 版本 |
| `analysis/stats.py` | `apps/analysis/stats.py` | 已替代（Django ORM 重写） | 废弃 src 版本 |
| `storage/database.py` | Django ORM | 已替代 | 废弃 |
| `__main__.py` | 无 | CLI 入口（内含版本号字符串） | 删除或改为项目级说明 |

### 2.3 依赖分析

- **backend/ 内部**：零引用 `paycheck.*` —— 确认后端完全独立
- **tests/**：3 处引用 `paycheck.*` —— 需修正 import 路径
- **根 pyproject.toml**：定义 `paycheck` 包，依赖 paddleocr/torch 等 OCR 库 —— 这些依赖已移至 `backend/pyproject.toml` 的 `[project.optional-dependencies] ocr`

---

## 3. 迁移方案设计

### 3.1 总体策略

**三步走**：删除冗余 → 迁移剩余 → 统一清理

```
Phase A: 删除已迁移模块        Phase B: 迁移 log.py         Phase C: 清理 & 统一
─────────────────────────     ────────────────────────     ───────────────────
src/paycheck/core/models.py   src/paycheck/core/log.py     pyproject.toml 改版
src/paycheck/core/constants   ──────────迁移──────────►    README.md 刷新
src/paycheck/core/tag_expr    backend/config/logging.py    DESIGN.md 刷新
src/paycheck/ingest/*                                    tests/ import 修正
src/paycheck/ocr/*                                        版本号 1.0.1
src/paycheck/analysis/*
src/paycheck/storage/*
```

### 3.2 Phase A：删除已迁移模块

**操作**：删除整个 `src/` 目录。

这是最核心的变更——`src/paycheck/` 中 90% 的代码已经迁移到 `backend/apps/`，且后端已是生产环境使用的代码路径。保留 `src/` 只会造成混淆。

**具体步骤**：

```bash
# 1. 删除 src/ 目录
rm -rf src/

# 2. 确认 backend/ 中所有对应模块可用
cd backend && uv run manage.py check  # Django 系统检查通过

# 3. 确认无残留引用
grep -r "from paycheck\." backend/  # 应无输出（已验证）
```

**影响评估**：
- `src/paycheck.egg-info/` 同时被删除（不再需要）
- 根 `pyproject.toml` 中的 `[tool.uv] package = true` 变为无效配置（Phase C 修复）

### 3.3 Phase B：迁移 log.py 到 backend

**分析**：`src/paycheck/core/log.py` 是通用日志工具，提供：
- `setup_logging()` — 日志配置（文件轮转 + 控制台输出）
- `get_logger()` — 自动获取调用者 logger
- `log_time()` — 耗时记录（装饰器 + 上下文管理器）
- 第三方库噪声压制（paddle、PIL、urllib3 等）

**迁移方案**：将 `log.py` 移动到 `backend/config/logging.py`，并做以下适配：

| 变更项 | 原代码 | 新代码 |
|---|---|---|
| 模块路径 | `paycheck.core.log` | `config.logging` |
| 根日志器名 | `"paycheck"` | `"paycheck"`（保持不变） |
| 日志文件路径 | `log/paycheck.log`（相对于项目根） | `BASE_DIR / "log" / "paycheck.log"`（Django 风格） |
| Django 集成 | 无 | 可通过 `LOGGING` dictConfig 集成（可选） |
| 调用方式 | `from paycheck.core.log import get_logger` | `from config.logging import get_logger` |

**为什么放在 `config/logging.py` 而非 `apps/core/`？**
- `config/` 是 Django 项目的配置目录，日志配置属于基础设施层
- 避免创建 `apps/core/` 这个仅有单文件的 app
- 保持 `config/` 目录的职责内聚（settings、urls、celery、wsgi、logging）

**迁移后的使用方式**：
```python
# 在各 app 模块中
from config.logging import get_logger
log = get_logger()  # 自动获取当前模块的 logger
```

### 3.4 Phase C：根项目配置清理

**根 `pyproject.toml` 改造**：

当前根 `pyproject.toml` 定义了 `paycheck` 包，但该包将在 Phase A 被删除。根配置应改为**工作空间级配置**，不再是一个可安装的 Python 包。

```toml
# 改造前（旧）
[project]
name = "paycheck"
version = "1.0.0"
requires-python = ">=3.10, <3.14"
dependencies = [
    "opencv-python",
    "openpyxl",
    # ... OCR 依赖 ...
]

[tool.uv]
package = true

# 改造后（新）
[project]
name = "paycheck"
version = "1.0.1"
description = "个人账单统计工具 — Django + React 前后端分离（Monorepo 根配置）"
requires-python = ">=3.10, <3.14"

[tool.uv]
package = false          # ★ 不再作为 Python 包
workspace = true         # ★ 声明为 uv workspace
```

**关键变更**：
- `package = false`：不再从 `src/` 构建 Python 包
- `version` 升至 `1.0.1`
- 移除 `dependencies`（OCR 依赖已在 backend 中管理）
- 移除 `[project.scripts]`（CLI 入口已废弃）
- 移除 `[project.optional-dependencies]`（已移至 backend）
- 移除 `[[tool.uv.index]]` 和 `[tool.uv.sources]`（已移至 backend）

---

## 4. 版本号更新方案

### 4.1 版本号统一策略

当前版本号分散在多个位置且不一致：

| 位置 | 当前版本 | 目标版本 |
|---|---|---|
| 根 `pyproject.toml` | 1.0.0 | **1.0.1** |
| `backend/pyproject.toml` | 0.1.0 | **1.0.1** |
| `README.md` 徽章 | 1.0.0 | **1.0.1** |
| `src/paycheck/__main__.py` | 1.0.0 | 随 src/ 删除 |
| `design/DESIGN.md` | 1.0 | **1.1**（设计文档独立版本号） |

### 4.2 语义化版本说明

按照 SemVer 2.0.0：
- **MAJOR (1)**：不变，无破坏性 API 变更
- **MINOR (0→1)**：包结构重构（核心包迁移至后端），功能无变化
- **PATCH (0→1)**：文档更新和版本统一

实际变更为 MINOR bump，但从 1.0.0 到 1.0.1 的 PATCH 级别更符合"内部重构 + 文档刷新"的语义——用户可见的功能和行为无任何变化。

**决策**：使用 `1.0.1`（用户要求），对应 PATCH 级别升级。

### 4.3 具体修改点

**根 `pyproject.toml`**：
```toml
version = "1.0.1"
```

**`backend/pyproject.toml`**：
```toml
version = "1.0.1"  # 从 0.1.0 同步升级
```

**`README.md`**：
```markdown
<img src="https://img.shields.io/badge/version-1.0.1-blueviolet" alt="Version">
```

**`design/DESIGN.md`**（本文档）：
```markdown
> **版本**: 1.1
```

---

## 5. 文档刷新策略

### 5.1 README.md 变更

#### 项目结构章节重写

当前 README 中 `## 项目结构` 包含 `src/paycheck/` 子树：

```
├── src/paycheck/               # Python 核心包（解析器/OCR/存储）
│   ├── ingest/parsers/         # 账单解析器
│   ├── ocr/                    # PaddleOCR 识别管线
│   ├── analysis/               # 统计分析
│   └── storage/                # SQLite 存储层
```

应删除该子树，将对应的功能模块说明合并到 `backend/` 部分：

```
├── backend/                    # Django 后端（含全部核心逻辑）
│   ├── apps/
│   │   ├── channels/           # 账单渠道管理
│   │   ├── transactions/       # 交易数据模型 + 标签表达式引擎
│   │   ├── ingest/             # 文件导入 & 解析器（支付宝/微信/银行）
│   │   ├── analysis/           # 统计分析
│   │   └── ocr_service/        # OCR 异步服务（PaddleOCR 管线）
│   ├── config/                 # Django 配置
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── celery.py           # Celery 配置
│   │   └── logging.py          # 日志配置（文件轮转 + 控制台）
│   ├── manage.py
│   └── pyproject.toml
```

#### 版本徽章更新

```diff
- <img src="https://img.shields.io/badge/version-1.0.0-blueviolet" alt="Version">
+ <img src="https://img.shields.io/badge/version-1.0.1-blueviolet" alt="Version">
```

#### 开发指南更新

删除对 `src/paycheck/` 的引用，统一指向 `backend/`：

```diff
- ### 新增银行支持
- 1. `backend/apps/ocr_service/layouts/` — 实现 `BankLayout` 接口
- 2. `backend/apps/ingest/parsers/` — 实现解析器
- 3. 注册布局并更新渠道配置
+ ### 新增银行支持
+ 1. `backend/apps/ocr_service/layouts/` — 实现 `BankLayout` 接口
+ 2. `backend/apps/ingest/parsers/` — 实现解析器（返回 `List[dict]`）
+ 3. 注册布局并更新渠道配置
```

### 5.2 DESIGN.md 变更（本次更新）

本次 DESIGN.md 即 v1.1 版本，覆盖：
- 核心包迁移路径（本文档 §3）
- 版本号更新方案（本文档 §4）
- 文档刷新策略（本文档 §5）

DESIGN.md v1.0 中的架构设计（§2-§8）仍然有效，本次更新为增量补充。

### 5.3 新增/变更文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/` | **删除** | 整个旧包目录 |
| `src/paycheck.egg-info/` | **删除** | 随 src/ 删除 |
| `backend/config/logging.py` | **新增** | 从 `src/paycheck/core/log.py` 迁移并适配 |
| `pyproject.toml` | **修改** | 版本 1.0.1，package=false，清理依赖 |
| `backend/pyproject.toml` | **修改** | 版本 0.1.0 → 1.0.1 |
| `README.md` | **修改** | 版本徽章 + 项目结构 + 开发指南 |
| `design/DESIGN.md` | **修改** | 更新为 v1.1（本文档） |
| `tests/unit/test_csv_utils.py` | **修改** | import 路径 → `backend.apps.ingest.csv_utils` |
| `tests/unit/test_tag_expr.py` | **修改** | import 路径 → `backend.apps.transactions.tag_expr` |
| `tests/integration/test_database.py` | **重写/删除** | Django ORM 替代 raw SQLite |

---

## 6. 测试迁移策略

### 6.1 当前测试与目标

| 测试文件 | 当前 import | 目标 import | 迁移难度 |
|---|---|---|---|
| `tests/unit/test_csv_utils.py` | `paycheck.ingest.csv_utils` | `apps.ingest.csv_utils` | 低（函数签名完全相同） |
| `tests/unit/test_tag_expr.py` | `paycheck.core.tag_expr` | `apps.transactions.tag_expr` | 低（代码完全相同） |
| `tests/integration/test_database.py` | `paycheck.storage.database` | Django TestCase | 中（需重写为 Django 测试） |

### 6.2 测试配置变更

当前 `tests/conftest.py` 可能需要调整为 Django 测试配置：

```python
# 选项 A: 将 tests/ 移到 backend/ 下，使用 Django 测试框架
# backend/tests/test_csv_utils.py

# 选项 B: 保持 tests/ 在根目录，通过 sys.path 添加 backend
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
```

**推荐选项 A**：将测试文件移至 `backend/tests/`，使用 Django 的 `TestCase` 和 pytest-django。理由是测试代码与被测代码在同一项目树下，import 路径自然正确。

### 6.3 测试文件映射

```
tests/unit/test_csv_utils.py      → backend/tests/unit/test_csv_utils.py
tests/unit/test_tag_expr.py       → backend/tests/unit/test_tag_expr.py
tests/integration/test_database.py → backend/tests/integration/test_models.py（重写）
tests/conftest.py                 → backend/tests/conftest.py
```

---

## 7. 实施步骤

### 总览

```
Step 1 ─────► Step 2 ─────► Step 3 ─────► Step 4 ─────► Step 5
迁移          删除          版本号         测试          文档
log.py        src/          统一切换       迁移 & 验证    刷新 & 提交
```

### Step 1：迁移 log.py（~10 分钟）

1. 复制 `src/paycheck/core/log.py` → `backend/config/logging.py`
2. 修改 `_connect()` 中的日志目录为 `BASE_DIR / "log"`
3. 更新 docstring 中的 import 示例
4. 验证：`cd backend && uv run python -c "from config.logging import get_logger; print(get_logger())"`

### Step 2：删除 src/ 目录（~5 分钟）

1. `rm -rf src/`
2. 验证 backend 无影响：`cd backend && uv run manage.py check`
3. 提交：`git add -A && git commit -m "refactor: remove src/paycheck package, migrate log.py to backend/config/"`

### Step 3：版本号统一（~10 分钟）

1. 根 `pyproject.toml`：`version = "1.0.1"`，`package = false`
2. `backend/pyproject.toml`：`version = "1.0.1"`
3. `README.md`：版本徽章 `1.0.0` → `1.0.1`
4. 提交：`git commit -m "chore: bump version to 1.0.1 across all manifests"`

### Step 4：测试迁移（~15 分钟）

1. 将 `tests/` 移至 `backend/tests/`
2. 修正 import 路径
3. 运行测试：`cd backend && uv run pytest`
4. 提交：`git commit -m "test: migrate tests from paycheck.* to backend.* imports"`

### Step 5：文档刷新（~10 分钟）

1. 更新 README.md 项目结构图
2. 更新 DESIGN.md 版本号和说明
3. 提交：`git commit -m "docs: refresh README and DESIGN for post-migration structure"`

### 实施总耗时估算

| 步骤 | 内容 | 预估 |
|---|---|---|
| Step 1 | log.py 迁移 | 10 min |
| Step 2 | 删除 src/ | 5 min |
| Step 3 | 版本号统一 | 10 min |
| Step 4 | 测试迁移 | 15 min |
| Step 5 | 文档刷新 | 10 min |
| **合计** | | **~50 min** |

---

## 8. 核心决策记录（ADR）

### ADR-005: 根 pyproject.toml 处置

**背景**：根 `pyproject.toml` 当前定义了一个可安装的 Python 包，迁移后将不再有 `src/` 目录。

**选项**：
- A. 删除根 `pyproject.toml`，仅保留 `backend/pyproject.toml`
- B. 保留根 `pyproject.toml`，改为 workspace 配置

**决策**：选择 **B（保留并改为 workspace 配置）**

**理由**：
- 保留根 `pyproject.toml` 作为 monorepo 的顶层配置锚点，对 IDE 和工具链友好
- `[tool.uv] workspace = true` 声明 workspace 关系，保持未来扩展性
- 版本号在根配置中统一管理，`backend/pyproject.toml` 同步
- 如果删除，uv 工具链可能将 `backend/` 误识别为独立项目而非 monorepo 子项目

### ADR-006: log.py 放置位置

**背景**：`core/log.py` 是通用工具，需在后端项目中找一个合适位置。

**选项**：
- A. `backend/config/logging.py`（Django 配置目录）
- B. `backend/apps/core/`（新建 app）
- C. `backend/utils/logging.py`（工具目录）

**决策**：选择 **A（`backend/config/logging.py`）**

**理由**：
- 日志属于基础设施/配置层，与 settings、celery 同级合理
- 避免为单一文件创建完整 Django app（选项 B 过度工程）
- 避免引入非 Django 惯例的 `utils/` 目录（选项 C 不符合 Django 惯例）
- `config/` 目录现有文件（settings、urls、celery、wsgi、asgi）均为配置/基础设施，logging 自然属于此层

### ADR-007: 测试目录迁移

**背景**：当前 `tests/` 在根目录，import `paycheck.*`。迁移后需修正。

**选项**：
- A. 将 `tests/` 移到 `backend/tests/`，使用 Django 测试框架
- B. 保持 `tests/` 在根目录，通过 `sys.path` hack 修正 import

**决策**：选择 **A（移到 backend/tests/）**

**理由**：
- `backend/` 是唯一 Python 项目，测试应与其在一起
- Django 测试框架（pytest-django）天然需要 tests 在 Django 项目内
- `sys.path` hack 脆弱，IDE 支持差
- 未来前端也可以有自己的 `frontend/__tests__/`

---

## 9. 风险与回滚

### 9.1 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|---|---|---|---|
| 某处仍有 `import paycheck.*` 的隐藏引用 | 该模块 ImportError | 低 | Step 2 前全局 grep 验证 |
| log.py 迁移后 Django 日志配置冲突 | 日志重复输出 | 低 | 保留独立调用接口，不与 Django LOGGING dict 强制整合 |
| 测试迁移后用例失败 | 测试红灯 | 低 | Step 4 运行全量测试验证 |
| 第三方工具/脚本依赖 `src/paycheck/` | 工具链断裂 | 极低 | 检查 CI 配置和 scripts |

### 9.2 回滚方案

若迁移出现问题，通过 git revert 回滚：

```bash
git revert <step2-commit>  # 恢复 src/ 目录
git revert <step1-commit>  # 恢复 log.py
```

所有变更是**纯删除 + 纯移动**，不涉及逻辑修改，回滚安全。

---

> **文档结束**。本文档作为 TCY-37 的 STAGE_DESIGN 产出物，覆盖核心包迁移路径、版本号更新方案和文档刷新策略。
>
> 实施由后续 STAGE_IMPLEMENT 阶段执行。
