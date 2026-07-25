# PayCheck 去除 Celery Broker 依赖设计方案

> **作者**: 架构师
> **日期**: 2026-07-26
> **版本**: 1.0
> **关联 Issue**: TCY-52

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [现状分析](#2-现状分析)
3. [方案对比](#3-方案对比)
4. [推荐方案：ThreadPoolExecutor + 数据库任务追踪](#4-推荐方案threadpoolexecutor--数据库任务追踪)
5. [详细设计](#5-详细设计)
6. [实施步骤](#6-实施步骤)
7. [核心决策记录（ADR）](#7-核心决策记录adr)
8. [风险与回滚](#8-风险与回滚)

---

## 1. 背景与目标

### 1.1 问题陈述

PayCheck 项目当前使用 Celery 作为异步任务队列，即使已将 Broker 从 Redis 切换为 SQLAlchemy+SQLite（ADR-005），用户仍需：

1. 安装 `celery`、`sqlalchemy`、`django-celery-results` 等额外依赖
2. 在启动 Django 开发服务器之外，**另开终端启动 Celery Worker**
3. 理解 Celery 的配置项（broker_url、result_backend、transport_options 等）

对于一个**个人账单统计工具**而言，这套基础设施过于重量级，增加了用户的学习和部署成本。

### 1.2 目标

1. **去除 Celery 依赖**：从 `pyproject.toml` 中移除 `celery`、`sqlalchemy`、`django-celery-results`
2. **消除独立 Worker 进程**：用户只需启动 Django 服务器即可使用全部功能
3. **保持异步能力**：文件解析和 OCR 仍异步执行，不阻塞 HTTP 请求
4. **保留任务状态追踪**：前端仍可通过 API 查询导入进度
5. **功能无退化**：导入流程（上传→解析→入库→状态更新）完全保留

---

## 2. 现状分析

### 2.1 Celery 使用全景

```
用户上传文件
    │
    ▼
ImportUploadView (views.py:98)
    │  process_import_job.delay(job.id)
    ▼
┌─────────────────────────────────────────────────────┐
│  Celery Worker (独立进程)                             │
│                                                       │
│  process_import_job (tasks.py:175)                    │
│    │  chord([subtask1, subtask2, ...])                │
│    │                                                  │
│    ├── process_import_file (tasks.py:93)              │
│    │     parse_alipay_csv / parse_wechat_xlsx         │
│    │     / parse_boc_csv                               │
│    │     → channel table → Transaction (with dedup)   │
│    │                                                  │
│    └── process_pdf_ocr (tasks.py:136)                 │
│          pdf_to_csv() → parse_boc_csv()                │
│          → channel table → Transaction                │
│                                                       │
│    _on_import_job_complete (tasks.py:214)             │
│      chord callback: update ImportJob status          │
└─────────────────────────────────────────────────────┘
```

### 2.2 涉及文件清单

| 文件 | 角色 | 变更类型 |
|------|------|---------|
| `backend/config/celery.py` | Celery app 实例化 | **删除** |
| `backend/config/__init__.py` | `from .celery import app` | **删除该行** |
| `backend/config/settings.py` | CELERY_* 配置项（L109-127） | **删除** |
| `backend/config/logging.py` | celery logger（L166-170） | **删除** |
| `backend/apps/ingest/tasks.py` | 4 个 Celery 任务 | **重构为普通函数 + executor** |
| `backend/apps/ingest/views.py` | `process_import_job.delay()` 调用 | **改为 executor 调用** |
| `backend/pyproject.toml` | celery/sqlalchemy/django-celery-results 依赖 | **移除** |
| `README.md` | Celery Worker 启动说明 | **删除 Worker 章节** |

### 2.3 任务特征分析

| 任务 | 类型 | 典型耗时 | 可并行 | 需要重试 |
|------|------|---------|--------|---------|
| `process_import_file` (CSV/XLSX) | I/O 密集 | < 5 秒 | ✅ 多文件并行 | ⚠️ 偶尔（文件损坏） |
| `process_pdf_ocr` | CPU 密集 | 30 秒 ~ 数分钟 | ✅ 多文件并行 | ⚠️ 偶尔（OCR 失败） |
| `process_import_job` | 编排层 | < 1 秒 | — | — |
| `_on_import_job_complete` | 回调 | < 1 秒 | — | — |

**关键洞察**：
- 所有任务都通过 Django ORM 操作 SQLite，已经有天然的持久化层
- ImportJob/ImportFile 模型已有 `status` 字段追踪进度
- Chord 模式（并行子任务 → 汇总回调）用 `ThreadPoolExecutor` 即可等价替代
- 任务量小（个人使用，单次最多 20 个文件），不需要分布式队列

### 2.4 依赖影响

```toml
# 当前 backend/pyproject.toml 中需移除的依赖
"celery>=5.4,<6.0",                  # ~2 MB
"sqlalchemy>=2.0,<3.0",             # ~10 MB（仅用于 broker transport）
"django-celery-results>=2.5,<3.0",  # ~50 KB
```

移除后共计减少约 **12 MB** 依赖体积，更重要的是消除概念复杂度。

---

## 3. 方案对比

### 方案 A：保持现状，不修改

**描述**：继续使用 Celery + SQLAlchemy broker。

| 维度 | 评价 |
|------|------|
| 部署复杂度 | ❌ 需启动两个进程（Django + Celery Worker） |
| 依赖体积 | ❌ +12 MB（celery + sqlalchemy + django-celery-results） |
| 可靠性 | ✅ 成熟的任务队列，支持持久化和重试 |
| 实现成本 | ✅ 零改动 |

**结论**：不满足用户"简化部署"的核心诉求。

---

### 方案 B：同步执行

**描述**：在 HTTP 请求中直接调用解析/OCR 函数，去掉所有异步逻辑。

| 维度 | 评价 |
|------|------|
| 部署复杂度 | ✅ 单进程，最简单 |
| 用户体验 | ❌ OCR 任务（数分钟）会导致 HTTP 超时 |
| 并发能力 | ❌ 多个文件串行处理，前端完全阻塞 |
| 实现成本 | ✅ ~50 行改动 |

**结论**：OCR 任务的阻塞问题无法接受，不适用于 PDF 导入场景。

---

### 方案 C：轻量级异步库（Huey / django-q / django-background-tasks）

**描述**：用更轻量的 Celery 替代品。

| 维度 | 评价 |
|------|------|
| 部署复杂度 | ⚠️ 仍需独立 Worker 进程 |
| 依赖体积 | ✅ 比 Celery 轻（~1-2 MB） |
| 功能匹配 | ⚠️ Huey 支持 SQLite，但 chord 语义弱于 Celery |
| 生态成熟度 | ✅ Huey 维护活跃，django-q 已停止更新 |

**结论**：仍然需要独立进程，未从根本上解决问题。

---

### 方案 D：ThreadPoolExecutor + 数据库任务追踪（⭐ 推荐）

**描述**：使用 Python 标准库 `concurrent.futures.ThreadPoolExecutor` 在 Django 进程内异步执行任务，通过 ImportJob/ImportFile 已有的 `status` 字段追踪进度。

| 维度 | 评价 |
|------|------|
| 部署复杂度 | ✅ 单进程，零额外进程 |
| 依赖体积 | ✅ 零新增依赖（标准库） |
| 可靠性 | ⚠️ 进程重启时未完成任务丢失（可接受——个人工具，重新上传即可） |
| 并发能力 | ✅ 多文件并行处理 |
| 进度追踪 | ✅ 复用 ImportFile/ImportJob.status，前端 API 不变 |
| 实现成本 | ⚠️ ~200 行改动（tasks.py 重构 + executor 模块新增） |

**结论**：最契合 PayCheck 的定位和约束。

---

### 3.5 方案对比总结

| | A: 保持现状 | B: 同步执行 | C: 轻量库 | **D: ThreadPoolExecutor** |
|---|---|---|---|---|
| 部署进程数 | 2 | 1 | 2 | **1** |
| 新增依赖 | 无 | 无 | +1-2 MB | **0** |
| OCR 不阻塞 | ✅ | ❌ | ✅ | **✅** |
| 多文件并行 | ✅ | ❌ | ✅ | **✅** |
| 进度可查询 | ✅ | ❌ | ✅ | **✅** |
| 任务持久化 | ✅ | N/A | ✅ | **⚠️ 进程内** |
| 实现成本 | 0 | 低 | 中 | **中** |

---

## 4. 推荐方案：ThreadPoolExecutor + 数据库任务追踪

### 4.1 架构变更

```
改造前                                  改造后
───────                                 ───────

Django (runserver)                      Django (runserver)
    │                                       │
    │ upload                               │ upload
    ▼                                      ▼
ImportUploadView                       ImportUploadView
    │                                       │
    │ process_import_job.delay()           │ import_executor.submit()
    ▼                                      ▼
┌──────────────┐                      ┌──────────────────────┐
│ Celery       │                      │ ThreadPoolExecutor   │
│ Worker       │                      │ (max_workers=4)      │
│ (独立进程)    │                      │ (Django 进程内)       │
│              │                      │                      │
│ Redis/SQLite │                      │ process_import_job() │
│ Broker       │                      │   │                  │
└──────────────┘                      │   ├── Thread 1:      │
                                      │   │  parse CSV       │
                                      │   ├── Thread 2:      │
                                      │   │  parse XLSX      │
                                      │   ├── Thread 3:      │
                                      │   │  OCR PDF         │
                                      │   └── callback:      │
                                      │      update job      │
                                      └──────────────────────┘

用户操作:                               用户操作:
  terminal 1: python manage.py runserver  terminal 1: python manage.py runserver
  terminal 2: celery -A config worker     ✅ 只需一个终端！
```

### 4.2 核心设计决策

#### 4.2.1 执行器生命周期

**决策**：使用模块级单例 `ThreadPoolExecutor`，在 Django AppConfig.ready() 中初始化，在 AppConfig 中通过 `atexit` 注册优雅关闭。

**理由**：
- 单例避免每次上传都创建/销毁线程池
- `atexit` 确保 Django 关闭时线程池等待任务完成（或超时）
- `max_workers=4` 足够个人使用（单次最多 20 个文件，4 并发充分）

#### 4.2.2 任务函数去 Celery 化

**决策**：将 `@shared_task` 装饰器改为普通 Python 函数，移除 `self.retry()`、`bind=True` 等 Celery 特有模式。

**重试策略变更**：
```
Celery:   max_retries=3, default_retry_delay=60, 自动指数退避
新方案:   max_retries=1, 在函数内部 while 循环实现简单重试，失败即标记 failed
```

**理由**：
- 当前任务的重试主要处理临时性错误（如文件被占用）
- PayCheck 是交互式工具，用户看到失败后可手动重新上传
- 简化重试逻辑，降低复杂度

#### 4.2.3 Chord 替代方案

**决策**：用 `ThreadPoolExecutor.submit()` + `as_completed()` 替代 Celery chord。

```python
# Celery chord（改造前）
from celery import chord
subtasks = [process_import_file.s(f.id) for f in import_files]
chord(subtasks)(_on_import_job_complete.s(job_id))

# ThreadPoolExecutor（改造后）
from concurrent.futures import as_completed
futures = {
    executor.submit(process_import_file, f.id): f.id
    for f in import_files
}
results = []
for future in as_completed(futures):
    results.append(future.result())
_on_import_job_complete(results, job_id)
```

**理由**：
- `as_completed` 语义完全覆盖 chord 的"并行执行 + 全部完成后回调"
- 代码更直观，无 Celery 魔法
- 一个文件失败不影响其他文件继续处理

#### 4.2.4 进度追踪

**决策**：保持 ImportJob/ImportFile 的 `status` 字段更新逻辑不变，前端通过现有的 API 轮询即可。

**API 不变**：`GET /api/import/jobs/{id}/` 返回 job 状态和文件列表。

---

## 5. 详细设计

### 5.1 新增模块：`backend/apps/ingest/executor.py`

```python
"""线程池执行器 — 替代 Celery 的异步任务调度

单例 ThreadPoolExecutor，在 Django 进程内执行导入任务。
"""

import atexit
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List

logger = logging.getLogger("paycheck.ingest.executor")

# 模块级单例
_executor: ThreadPoolExecutor | None = None
MAX_WORKERS = 4


def get_executor() -> ThreadPoolExecutor:
    """获取全局线程池（懒初始化 + atexit 优雅关闭）"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="ingest-",
        )
        atexit.register(_shutdown)
        logger.info("ThreadPoolExecutor initialized (max_workers=%d)", MAX_WORKERS)
    return _executor


def _shutdown(wait: bool = True, timeout: float = 30.0) -> None:
    """atexit 回调：优雅关闭线程池"""
    global _executor
    if _executor is not None:
        logger.info("Shutting down ThreadPoolExecutor...")
        _executor.shutdown(wait=wait, cancel_futures=not wait)
        if wait:
            logger.info("ThreadPoolExecutor shut down.")
        _executor = None


def run_parallel(
    tasks: List[Callable],
    callback: Callable | None = None,
    callback_args: tuple | None = None,
) -> List:
    """并行执行多个任务，全部完成后调用回调（等价 Celery chord）

    Args:
        tasks: 无参 callable 列表
        callback: 全部完成后调用的回调函数，接收 (results_list, *callback_args)
        callback_args: 传递给回调的额外位置参数

    Returns:
        每个任务的返回值列表（保持与 tasks 相同的顺序）
    """
    executor = get_executor()
    future_to_idx = {
        executor.submit(task): idx
        for idx, task in enumerate(tasks)
    }

    # 收集结果，保持原始顺序
    results: List = [None] * len(tasks)
    errors: List[Exception] = []

    for future in as_completed(future_to_idx):
        idx = future_to_idx[future]
        try:
            results[idx] = future.result()
        except Exception as exc:
            logger.exception("Task %d failed: %s", idx, exc)
            results[idx] = exc
            errors.append(exc)

    # 回调（即使部分任务失败也执行）
    if callback is not None:
        args = callback_args or ()
        callback(results, *args)

    return results
```

### 5.2 重构：`backend/apps/ingest/tasks.py`

将 `@shared_task` 装饰器移除，`self.retry()` 替换为简单的内部重试循环：

```python
"""数据导入异步任务（去 Celery 化）

处理文件上传 → 解析 → 渠道表写入 → 统一交易表同步 的完整流程。
"""

import hashlib
import os

from django.db import IntegrityError
from django.utils import timezone

from apps.ingest.models import ImportJob, ImportFile
from apps.ingest.parsers.alipay import parse_alipay_csv
from apps.ingest.parsers.wechat import parse_wechat_xlsx
from apps.ingest.parsers.boc import parse_boc_csv
from apps.channels.models import AlipayTx, WechatTx, BocTx
from apps.transactions.models import Transaction

# ── _compute_row_hash 和 _sync_to_transactions 保持不变 ──
# （与当前 tasks.py 完全一致，此处省略以节省篇幅）


def process_import_file(import_file_id: int) -> dict:
    """处理单个导入文件：解析 → 渠道表 → 交易表（同步）"""
    max_retries = 1
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return _process_import_file_once(import_file_id)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            # 最后一次也失败了
            try:
                import_file = ImportFile.objects.get(id=import_file_id)
                import_file.status = "failed"
                import_file.error_msg = str(exc)
                import_file.save(update_fields=["status", "error_msg"])
            except ImportFile.DoesNotExist:
                pass
            raise

    return {"error": str(last_error)}


def _process_import_file_once(import_file_id: int) -> dict:
    """单次执行文件解析（内部函数，不含重试）"""
    import_file = ImportFile.objects.get(id=import_file_id)
    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    file_path = import_file.filename

    if import_file.file_type == "alipay_csv":
        txns = parse_alipay_csv(file_path)
        platform = "alipay"
    elif import_file.file_type == "wechat_xlsx":
        txns = parse_wechat_xlsx(file_path)
        platform = "wechat"
    elif import_file.file_type in ("boc_csv", "boc_pdf"):
        txns = parse_boc_csv(file_path)
        platform = "boc"
    else:
        raise ValueError(f"Unknown file type: {import_file.file_type}")

    created, skipped = _sync_to_transactions(txns, platform, import_file.file_type)

    import_file.status = "completed"
    import_file.save(update_fields=["status"])

    return {"created": created, "skipped": skipped}


def process_pdf_ocr(import_file_id: int) -> dict:
    """OCR 处理 BOC PDF：PDF → CSV → 解析 → 入库"""
    import_file = ImportFile.objects.get(id=import_file_id)
    import_file.status = "processing"
    import_file.save(update_fields=["status"])

    try:
        from apps.ocr_service.pipeline import pdf_to_csv

        pdf_path = import_file.filename
        output_dir = os.path.dirname(pdf_path)
        output_path = os.path.join(
            output_dir,
            f"{os.path.splitext(os.path.basename(pdf_path))[0]}.csv",
        )

        result = pdf_to_csv(pdf_path, "boc", output_path=output_path)
        if result != 0:
            raise RuntimeError("OCR pipeline failed")

        txns = parse_boc_csv(output_path)
        created, skipped = _sync_to_transactions(txns, "boc", "boc_pdf")

        import_file.status = "completed"
        import_file.save(update_fields=["status"])

        return {"created": created, "skipped": skipped}

    except Exception as exc:
        import_file.status = "failed"
        import_file.error_msg = str(exc)
        import_file.save(update_fields=["status", "error_msg"])
        raise


def process_import_job(job_id: int) -> dict:
    """编排导入任务：并行分发子任务，全部完成后更新 Job 状态"""
    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return {"error": f"ImportJob {job_id} not found"}

    job.status = "processing"
    job.save(update_fields=["status"])

    import_files = job.files.all()
    if not import_files:
        job.status = "completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return {"total": 0, "processed": 0}

    # 构建任务列表
    from apps.ingest.executor import run_parallel

    def make_task(import_file):
        if import_file.file_type == "boc_pdf":
            return lambda fid=import_file.id: process_pdf_ocr(fid)
        else:
            return lambda fid=import_file.id: process_import_file(fid)

    tasks = [make_task(f) for f in import_files]
    run_parallel(tasks, callback=_on_import_job_complete, callback_args=(job_id,))

    return {"job_id": job_id, "status": "processing", "total_files": len(tasks)}


def _on_import_job_complete(results: list, job_id: int) -> None:
    """所有子任务完成后的回调：更新 ImportJob 状态"""
    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        return

    job.status = "completed"
    job.processed = job.total_files
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "processed", "completed_at"])
```

### 5.3 修改：`backend/apps/ingest/views.py`

仅需修改第 98 行的调用方式：

```diff
- from apps.ingest.tasks import process_import_job
+ from apps.ingest.tasks import process_import_job
+ from apps.ingest.executor import get_executor

  # 启动 Celery 异步处理
- process_import_job.delay(job.id)
+ get_executor().submit(process_import_job, job.id)
```

### 5.4 删除清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/config/celery.py` | **删除整个文件** | Celery app 定义 |
| `backend/config/__init__.py` | **删除 L1-3** | `from .celery import app` |
| `backend/config/settings.py` | **删除 L109-127** | CELERY_* 全部配置 |
| `backend/config/settings.py` | **修改 L31** | 移除 `"django_celery_results"` from INSTALLED_APPS |
| `backend/config/settings.py` | **修改 L2** | 更新 docstring |
| `backend/config/logging.py` | **删除 L166-170** | celery logger 配置 |
| `backend/pyproject.toml` | **删除** | `celery`、`sqlalchemy`、`django-celery-results` 三个依赖 |
| `README.md` | **修改** | 删除 Celery Worker 启动章节、架构图中移除 Celery 框 |

---

## 6. 实施步骤

```
Phase 1 ───────► Phase 2 ────────► Phase 3 ────────► Phase 4
新建 executor   重构 tasks.py     清理 Celery 配置    文档 & 验证
(30 min)        (45 min)          (20 min)           (15 min)
```

### Phase 1：新建 executor 模块
1. 创建 `backend/apps/ingest/executor.py`
2. 实现 `get_executor()`、`run_parallel()`、`_shutdown()`
3. 单元测试验证线程池创建和并行执行

### Phase 2：重构 tasks.py
1. 移除所有 `@shared_task` 装饰器、`bind=True`、`self.retry()`
2. 将 `process_import_file`、`process_pdf_ocr`、`process_import_job`、`_on_import_job_complete` 改为普通函数
3. 在 `process_import_job` 中用 `run_parallel()` 替代 `celery.chord()`
4. 保持 `_compute_row_hash`、`_sync_to_transactions` 不变

### Phase 3：清理 Celery 配置
1. 修改 `views.py`：`delay()` → `get_executor().submit()`
2. 删除 `config/celery.py`
3. 修改 `config/__init__.py`
4. 修改 `config/settings.py`（删除 CELERY 配置块 + INSTALLED_APPS）
5. 修改 `config/logging.py`（删除 celery logger）
6. 修改 `pyproject.toml`（移除 3 个依赖）
7. 运行 `uv sync` 清理依赖
8. 运行 `uv run manage.py check` 验证 Django 配置

### Phase 4：文档与验证
1. 更新 README.md：移除 Celery Worker 启动步骤
2. 端到端测试：上传各类型文件，验证解析和状态更新
3. 提交 commit

---

## 7. 核心决策记录（ADR）

### ADR-008：去除 Celery，改用 ThreadPoolExecutor

**背景**：PayCheck 使用 Celery 处理文件导入和 OCR 的异步任务，需要独立的 Worker 进程和额外的 Python 依赖（celery、sqlalchemy、django-celery-results），增加了个人用户的部署复杂度。

**选项**：
- A. 保持 Celery + SQLAlchemy broker（现状）
- B. 改为同步执行
- C. 换用 Huey / django-q 等轻量库
- D. 使用 `concurrent.futures.ThreadPoolExecutor`（Python 标准库）

**决策**：选择 **D（ThreadPoolExecutor + 数据库任务追踪）**

**理由**：
1. **零依赖**：`ThreadPoolExecutor` 是 Python 3 标准库，无需安装任何额外包
2. **单进程部署**：任务在 Django 进程内执行，用户只需 `python manage.py runserver`
3. **功能匹配**：PayCheck 是个人工具（单用户、SQLite、最多 20 文件/次），不需要分布式队列的特性
4. **API 不变**：ImportJob/ImportFile 的 `status` 字段天然支持进度追踪，前端无需改动
5. **实现简单**：~200 行改动，Chord 语义用 `as_completed()` 等价替代

**代价**：
- 进程重启时未完成任务丢失（个人工具可接受——用户重新上传即可）
- 无内置的指数退避重试（可在函数内部简单实现）
- 不适用于未来可能的多 Worker 横向扩展（PayCheck 的定位不需要）

### ADR-009：max_workers=4 的线程池规模

**背景**：ThreadPoolExecutor 需要设定最大工作线程数。

**决策**：`max_workers=4`

**理由**：
- PayCheck 是个人桌面工具，CPU 核心数通常 ≥ 4
- 单次最多上传 20 个文件，4 并发可在 5 轮内处理完毕
- OCR 任务虽 CPU 密集，但在个人使用场景下一次只做一个 PDF，线程争抢不是瓶颈
- 4 个线程不会对 SQLite（WAL 模式）造成显著的写锁竞争

---

## 8. 风险与回滚

### 8.1 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| OCR 时 Django 进程崩溃导致任务丢失 | 用户需重新上传 | 低 | ImportFile.status=failed 记录错误信息，用户可重试 |
| 线程内 Django ORM 连接问题 | 任务执行失败 | 低 | 每个线程使用独立 DB 连接（Django 默认线程安全） |
| 大量并发上传导致线程池耗尽 | 新任务排队等待 | 低 | 个人工具，并发场景极少 |
| `atexit` 在某些退出方式（kill -9）不触发 | 少量数据未写入 | 极低 | SQLite WAL 模式已大幅降低数据丢失风险 |

### 8.2 回滚方案

若方案 D 出现问题，回滚路径：

```bash
# 恢复 Celery 配置文件和依赖
git revert <commit-hash>

# 重新安装 Celery 依赖
cd backend && uv sync
```

改动集中在 6 个文件中，且 tasks.py 的核心逻辑（解析、同步）保持不变，仅移除装饰器和 chord 调用，回滚安全。

---

### 8.3 SQLite 线程安全说明

Django 默认对每个线程使用独立的数据库连接，SQLite 在 WAL 模式下支持并发读和有限并发写。当前 `settings.py` 已配置：

```python
"OPTIONS": {
    "timeout": 20,          # 写锁等待 20 秒
    "init_command": (
        "PRAGMA journal_mode=WAL;"
        "PRAGMA synchronous=NORMAL;"
        "PRAGMA foreign_keys=ON;"
    ),
}
```

这些配置足以支持 4 个线程的并发写入。若遇到 `database is locked` 错误，可将 `timeout` 调高至 30 秒。

---

> **文档结束**。本文档作为 TCY-52 的 STAGE_DESIGN 产出物，覆盖去除 Celery Broker 的架构方案、替代方案对比和详细实施设计。
>
> 实施由后续 STAGE_IMPLEMENT 阶段执行。
