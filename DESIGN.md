# boc-pdf2csv Python 包架构设计

> **作者**: 架构师
> **日期**: 2026-08-03
> **版本**: 1.0
> **关联 Issue**: TCY-77, TCY-78

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [现状分析](#2-现状分析)
3. [架构方案](#3-架构方案)
4. [项目结构](#4-项目结构)
5. [CLI 设计](#5-cli-设计)
6. [核心数据流](#6-核心数据流)
7. [模块设计](#7-模块设计)
8. [依赖清单](#8-依赖清单)
9. [迁移策略](#9-迁移策略)
10. [ADR](#10-核心决策记录adr)

---

## 1. 背景与目标

### 1.1 问题陈述

PayCheck 项目经过多轮迭代，已演变为 Django + React 全栈 Web 应用，包含：

- **4 个 Django App**（ingest, transactions, channels, analysis）
- **React SPA 前端**（~30 个组件文件）
- **Celery + ThreadPoolExecutor 双异步体系**
- **3 个渠道解析器**（Alipay, WeChat, BOC）
- **标签系统、高级筛选、统计分析、CSV 导入导出**

项目臃肿，但用户的核心诉求只有一点：**把中国银行导出的 PDF 对账单转成 CSV 文件**。

### 1.2 目标

1. **精简化**：从全栈 Web 应用精简为单一 Python CLI 包
2. **包名**：`boc-pdf2csv`
3. **项目形式**：`uv` 管理的 Python 项目
4. **CLI 命令**：`boc-pdf2csv <input_dir> [options]`
5. **功能**：输入一个文件夹（内含中国银行 PDF），输出一个合并后的 CSV 文件
6. **无 Web 依赖**：完全去除 Django / DRF / Celery / React
7. **零数据库**：不依赖任何数据库，纯文件输入输出

### 1.3 非目标

- 不支持微信、支付宝账单
- 不支持 Web 界面
- 不支持标签、筛选、统计分析
- 不支持增量更新或数据库持久化
- 不保留 BankLayout 插件体系（仅 BOC 硬编码）

---

## 2. 现状分析

### 2.1 当前架构（精简前）

```
PayCheck/
├── pyproject.toml              # 根包（mixed deps, package=false）
├── backend/
│   ├── pyproject.toml          # 后端独立包
│   └── apps/
│       ├── ingest/             # 导入 → parsers/{alipay, wechat, boc}
│       ├── ocr_service/        # OCR 管线
│       │   ├── engine.py       # PaddleOCR 封装
│       │   ├── pipeline.py     # pdf_to_csv / images_to_csv
│       │   ├── pdf_render.py   # PDF → 图片渲染
│       │   └── layouts/        # BankLayout 抽象 + BocLayout
│       ├── transactions/       # 交易模型、标签、筛选、常量
│       ├── channels/           # 渠道分表管理
│       └── analysis/           # 统计分析
├── frontend/                   # React SPA (~30 组件)
├── PayCheck/                   # 旧项目副本
└── DESIGN.md                   # 历史设计文档
```

### 2.2 BOC PDF→CSV 核心管线（需保留的代码）

```
PDF 文件
  │
  ▼
pdf_render.py          PyMuPDF 渲染 PDF → PNG 图片（多进程）
  │  pdf_to_images()
  │  render_page_cropped()   ── 亮度分析裁剪表格区域
  ▼
engine.py              PaddleOCR 识别图片中的文字
  │  process_image()
  │  OCRItem {text, cx, cy}
  ▼
layouts/boc.py         BOC 列坐标 → 行分组 → 交易结构化
  │  COLUMNS_3X (12 列定义 @ 3.0× scale)
  │  group_items_to_rows()
  │  to_transactions()
  ▼
pipeline.py            ★ 编排层：组合上述阶段
  │  pdf_to_csv(pdf_path, layout_name, scale, output_path)
  │  images_to_csv(image_paths, layout_name, scale, output_path)
  ▼
CSV 文件
```

### 2.3 涉及文件清单

| 文件 | 行数 | 角色 | 变更类型 |
|------|------|------|----------|
| `ocr_service/layouts/boc.py` | 105 | BOC 列坐标 + 交易结构化 | **适配**（简化，去除 Django 依赖） |
| `ocr_service/layouts/base.py` | 219 | BankLayout 抽象、Row、OCRItem、行分组 | **合并**（与 boc 合并为单文件） |
| `ocr_service/layouts/__init__.py` | 41 | 布局注册表 | **删除**（硬编码 BOC，无需注册） |
| `ocr_service/engine.py` | 113 | PaddleOCR 封装 | **保留**（仅改 import 路径） |
| `ocr_service/pipeline.py` | 276 | 管线编排 + CSV 写出 | **适配**（去除 Django import，改 CLI 化） |
| `ocr_service/pdf_render.py` | 136 | PDF → 图片渲染 | **保留**（仅改 import 路径） |
| `ingest/parsers/boc.py` | 134 | 解析 CSV 为 dict（Django 适配层） | **删除**（CLI 直接写 CSV，不需要回读） |
| `ingest/csv_utils.py` | 28 | CSV 行解析器 | **删除**（pipeline 已有 `_esc_csv`） |
| 其他全部文件 | — | Django/React/Celery/Alipay/WeChat | **删除** |

**保留/适配核心代码约 850 行，删除约 20,000+ 行。**

---

## 3. 架构方案

### 方案 A：保持现状，仅加 CLI 入口（不推荐）

Django 项目内新增 `manage.py boc2csv` 命令。

| 维度 | 评价 |
|------|------|
| 实现成本 | ✅ 最低（~30 行新增） |
| 部署复杂度 | ❌ 仍需安装 Django + 全部依赖 |
| 依赖体积 | ❌ ~500 MB（含 Django 生态） |
| 可分发性 | ❌ 无法作为独立 pip 包发布 |

### 方案 B：独立 Python 包 + 硬编码 BOC（⭐ 推荐）

创建全新 `boc-pdf2csv` 包，从现有代码中提取 BOC OCR 管线，去除所有 Django/Web/数据库依赖。

| 维度 | 评价 |
|------|------|
| 实现成本 | ⚠️ 中等（提取 + 适配 ~850 行） |
| 部署复杂度 | ✅ `uv tool install` 或 `pip install` 即可 |
| 依赖体积 | ✅ 仅 OCR 必要依赖（~4-6 GB 含模型，但纯 Python 包体积小） |
| 可分发性 | ✅ 独立 pip 包，可发布到 PyPI |
| CLI 体验 | ✅ `boc-pdf2csv ./pdfs/ -o output.csv` |

### 方案 C：保留 BankLayout 插件体系（过度设计）

保留抽象基类 + 注册表，支持未来扩展其他银行。

| 维度 | 评价 |
|------|------|
| 扩展性 | ✅ 新增银行只需实现 BankLayout |
| 复杂度 | ❌ 为"可能"的需求引入 200+ 行抽象层 |
| 维护成本 | ❌ 需要维护抽象接口兼容性 |

**结论**：选择 **方案 B**。方案 C 在未来确实需要支持第二个银行时再重构，成本可控。

---

## 4. 项目结构

### 4.1 目录树

```
boc-pdf2csv/
├── pyproject.toml              # uv 项目配置（含 CLI 入口点）
├── README.md                   # 使用说明
├── DESIGN.md                   # 本文档
├── LICENSE                     # MIT
├── src/
│   └── boc_pdf2csv/
│       ├── __init__.py         # 空
│       ├── __main__.py         # `python -m boc_pdf2csv` 入口（委托给 cli）
│       ├── cli.py              # ★ CLI 参数解析 + main()
│       ├── engine.py           # PaddleOCR 引擎封装（从 ocr_service/engine.py 提取）
│       ├── layout.py           # BOC 布局：列坐标、行分组、交易结构化（合并 base.py + boc.py）
│       ├── pdf_render.py       # PDF → 图片渲染（从 ocr_service/pdf_render.py 提取）
│       └── pipeline.py         # 管线编排：PDF → 图片 → OCR → CSV（从 pipeline.py 提取）
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py        # 端到端测试
└── sample/                     # 开发用示例 PDF
    └── README.md
```

### 4.2 模块职责

| 模块 | 职责 | 来源 | 行数（估） |
|------|------|------|-----------|
| `cli.py` | argparse CLI，参数校验，调用 pipeline | 新建 | ~60 |
| `__main__.py` | `python -m boc_pdf2csv` 入口 | 新建 | ~5 |
| `engine.py` | PaddleOCR 单例 + warmup + process_image | `ocr_service/engine.py` | ~90 |
| `layout.py` | BOC 列定义、OCRItem/Row 数据结构、行分组、交易转换 | `layouts/base.py` + `boc.py` | ~240 |
| `pdf_render.py` | PDF→裁剪 PNG 渲染（多进程并行） | `ocr_service/pdf_render.py` | ~110 |
| `pipeline.py` | 两阶段管线 + CSV 写出 + 批量 PDF 合并 | `ocr_service/pipeline.py` | ~200 |

**总代码量：约 700 行纯业务逻辑，无框架膨胀。**

### 4.3 模块依赖图

```
cli.py
  └── pipeline.py
        ├── pdf_render.py
        │     └── layout.py (find_table_bounds)
        ├── engine.py
        │     └── paddleocr (外部)
        └── layout.py
              └── (纯 Python，无外部依赖)
```

**依赖方向单一，无循环。** pipeline 是唯一的编排点，cli 只依赖 pipeline。

---

## 5. CLI 设计

### 5.1 命令签名

```
boc-pdf2csv <input_dir> [-o <output.csv>] [--scale <float>] [--timeout <minutes>] [--verbose]
```

### 5.2 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `input_dir` | PATH | ✅ 是 | — | 包含中国银行 PDF 文件的目录路径 |
| `-o, --output` | PATH | 否 | `<input_dir>/output.csv` | 输出 CSV 文件路径 |
| `--scale` | float | 否 | `3.0` | PDF 渲染缩放倍率（影响 OCR 精度和速度） |
| `--timeout` | int | 否 | `60` | 单文件处理超时（分钟），超时后跳过继续 |
| `-v, --verbose` | flag | 否 | `false` | 启用详细日志（DEBUG 级别输出到控制台） |

### 5.3 输入规范

- `input_dir` 必须存在且为目录
- 递归查找目录中所有 `.pdf` 文件（大小写不敏感）
- 每个 PDF 被视为中国银行导出的流水单
- 跳过非 PDF 文件，给出 warning
- 若目录内无 PDF 文件，报错退出

### 5.4 输出规范

- 输出 CSV 文件包含以下列（与现有 BOC 布局一致）：

```csv
date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank
```

- **编码**：UTF-8 with BOM（兼容 Excel 直接打开）
- **金额格式**：正数（`tx_type` 列区分"收入""支出"）
- **多 PDF 合并**：所有 PDF 的交易记录合并到同一个 CSV，按日期+时间排序
- **去重**：同一 PDF 内不重复，不同 PDF 间不去重（用户可能确实有重复记录）

### 5.5 使用示例

```bash
# 基本用法
boc-pdf2csv ./2026年账单/

# 指定输出文件
boc-pdf2csv ./pdfs/ -o ./result/2026-merged.csv

# 高精度 OCR（4K 渲染）
boc-pdf2csv ./pdfs/ --scale 4.0 -o ./output.csv

# 调试模式
boc-pdf2csv ./pdfs/ -v
```

### 5.6 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 全部成功 |
| 1 | 部分 PDF 处理失败（剩余的已输出） |
| 2 | 全部失败 / 输入错误 |

### 5.7 进度输出

```
$ boc-pdf2csv ./pdfs/
[1/3] 202401流水.pdf ... 24 条交易 ✓
[2/3] 202402流水.pdf ... 31 条交易 ✓
[3/3] 202403流水.pdf ... ✗ OCR 识别失败（跳过）
完成: 55 条交易 → ./pdfs/output.csv
部分失败 (1/3)，退出码 1
```

---

## 6. 核心数据流

### 6.1 整体流程

```
                 ┌──────────────┐
                 │   cli.py     │
                 │  argparse    │
                 │  glob PDFs   │
                 └──────┬───────┘
                        │  List[pdf_path]
                        ▼
                 ┌──────────────┐
                 │ pipeline.py  │
                 │  process_    │
                 │  directory() │
                 └──────┬───────┘
                        │  for each PDF:
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ PDF #1     │ │ PDF #2     │ │ PDF #3     │
   │ ↓          │ │ ↓          │ │ ↓          │
   │ pdf_to_csv │ │ pdf_to_csv │ │ pdf_to_csv │
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
         │ CSV string     │             │
         └────────┬───────┘─────────────┘
                  │  合并 + 排序
                  ▼
         ┌────────────────┐
         │  output.csv    │
         │  UTF-8 BOM     │
         └────────────────┘
```

### 6.2 单 PDF 处理细节（`pdf_to_csv`）

```
PDF 文件
  │
  ▼
┌─────────────────────────────────────┐
│ 阶段一：PDF → 图片（pdf_render.py）  │
│                                     │
│  fitz.open(pdf)                     │
│    │                                │
│    │ for each page (多进程并行):      │
│    ▼                                │
│  page.get_pixmap(matrix=3.0×)       │
│    │  → PIL Image (RGB)             │
│    ▼                                │
│  find_table_bounds()                │
│    │  亮度分析法检测表格区域           │
│    │  → (top, bottom, left, right)   │
│    ▼                                │
│  img.crop(bbox) → p{N}.png          │
│                                     │
│  输出: List[image_path] (按页码排序)  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 阶段二：图片 → OCR → CSV             │
│                                     │
│  for each page image:               │
│    │                                │
│    ▼                                │
│  engine.process_image(img)          │
│    │  PaddleOCR.predict()            │
│    │  → List[OCRItem]               │
│    │     {text, cx, cy, score}       │
│    ▼                                │
│  layout.group_rows(items, scale)     │
│    │  ① 按列坐标分配文字到字段        │
│    │  ② 按 Y 坐标分组为行             │
│    │  → List[Row]                   │
│    ▼                                │
│  layout.to_transactions(rows)       │
│    │  ③ BOC 列格式 → dict            │
│    │  ④ amount 分正负 → 收/支        │
│    │  → List[dict]                  │
│    ▼                                │
│  _write_csv(page_results)           │
│    │  按页序写出 13 列 CSV            │
│    ▼                                │
│  CSV 字符串                         │
└─────────────────────────────────────┘
```

### 6.3 BOC 列坐标体系（3.0× scale 基准）

```
┌──────────┬──────────┬────────┬────────┬────────┬──────────┬────────┬──────────┬────────┬──────────┬──────────┬──────────┐
│ 记账日期  │ 记账时间  │  币别  │  金额   │  余额   │ 交易名称  │  渠道  │ 网点名称  │  附言  │ 对方账户名│对方卡号/ │对方开户行 │
│  0-202   │ 202-380  │380-553 │553-737 │737-923 │ 923-1093 │1093-  │ 1266-    │1469-   │ 1689-    │ 账号     │ 2250-    │
│          │          │        │        │        │          │ 1266   │ 1469     │ 1689   │ 1909     │1909-2180 │ 9999     │
└──────────┴──────────┴────────┴────────┴────────┴──────────┴────────┴──────────┴────────┴──────────┴──────────┴──────────┘
```

列坐标硬编码在 `layout.py` 中，对应中国银行 2024-2026 年的账单格式。如未来银行改版，只需更新此坐标表。

### 6.4 数据转换规则

| OCR 原始值 | 转换逻辑 | 输出字段 |
|------------|----------|----------|
| 金额（负值/正值） | `raw_amount < 0 → tx_type="支出", amount=abs(raw_amount)` | `tx_type`, `amount` |
| 日期+时间 | `f"{date} {time}".strip()` | `date`, `time`, `dateTime`（组合后不再单独输出） |
| 空白字段 | 保持空字符串 | 各字段 |
| OCR 识别失败的行 | 跳过（行中 date 或 amount 为空） | — |
| OCR 置信度 < 0.3 | 过滤 | — |

---

## 7. 模块设计

### 7.1 `cli.py` — CLI 入口

```python
"""boc-pdf2csv CLI — 中国银行 PDF 对账单转 CSV"""

import argparse
import logging
import sys
from pathlib import Path

from boc_pdf2csv.pipeline import process_directory


def main():
    parser = argparse.ArgumentParser(
        prog="boc-pdf2csv",
        description="将中国银行 PDF 对账单转换为 CSV 文件",
    )
    parser.add_argument("input_dir", type=Path, help="包含中国银行 PDF 文件的目录")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出 CSV 路径")
    parser.add_argument("--scale", type=float, default=3.0, help="PDF 渲染倍率")
    parser.add_argument("--timeout", type=int, default=60, help="单文件超时（分钟）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()
    # ... 参数校验 + 调用 process_directory()
```

### 7.2 `engine.py` — OCR 引擎（从现有代码提取，适配 import 路径）

变化点：
- 去掉 `from apps.ocr_service.layouts.base import OCRItem`，改为 `from boc_pdf2csv.layout import OCRItem`
- 保持 `PaddleOCR(lang='ch')` 配置不变
- 保持 0.3 置信度阈值

### 7.3 `layout.py` — BOC 布局（合并 base.py + boc.py）

变化点：
- `OCRItem`、`Row` dataclass 从 `base.py` 迁入
- `find_table_bounds()`、`group_items_to_rows()` 从 `base.py` 迁入
- `COLUMNS_3X` 列定义 + `BocLayout.to_transactions()` 从 `boc.py` 迁入
- **去除 BankLayout 抽象类**：不需要多态，直接用函数
- 去除 PIL/numpy import（仅 `find_table_bounds` 需要，保留）
- 简化日志：`logging.getLogger("boc_pdf2csv.layout")`

### 7.4 `pdf_render.py` — PDF 渲染（从现有代码提取）

变化点：
- 改 import：`from apps.ocr_service.layouts.base import find_table_bounds` → `from boc_pdf2csv.layout import find_table_bounds`
- 简化日志
- 保持多进程并行渲染逻辑

### 7.5 `pipeline.py` — 管线编排

核心变化：
- 新增 `process_directory()` 函数：遍历目录 → 批量 `pdf_to_csv()` → 合并 → 写入
- `pdf_to_csv()` 和 `images_to_csv()` 保持现有逻辑，改 import 路径
- `_write_csv()` 添加 UTF-8 BOM 支持（`﻿`）
- `_esc_csv()` 保持不变
- 去除 `from tqdm import tqdm` 依赖（保留，CLI 工具需要进度条）

### 7.6 `__main__.py`

```python
"""python -m boc_pdf2csv 入口"""
from boc_pdf2csv.cli import main
main()
```

---

## 8. 依赖清单

### 8.1 `pyproject.toml`

```toml
[project]
name = "boc-pdf2csv"
version = "1.0.0"
description = "中国银行 PDF 对账单转 CSV 工具"
requires-python = ">=3.10, <3.14"
dependencies = [
    "paddleocr>=3.6.0",
    "PyMuPDF>=1.23.0",
    "opencv-python>=4.8.0",
    "Pillow>=10.0",
    "torch>=2.0.0",
    "tqdm>=4.60.0",
    "numpy>=1.24.0",
]

[project.optional-dependencies]
# CPU 用户
cpu = ["paddlepaddle>=2.6.0"]
# GPU 用户 (CUDA 12.6)
gpu = ["paddlepaddle-gpu>=2.6.0"]

[project.scripts]
boc-pdf2csv = "boc_pdf2csv.cli:main"

[tool.uv]
package = true

[[tool.uv.index]]
name = "paddle-cpu"
url = "https://www.paddlepaddle.org.cn/packages/stable/cpu/"
explicit = true

[[tool.uv.index]]
name = "paddle-gpu"
url = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
explicit = true

[tool.uv.sources]
paddlepaddle = { index = "paddle-cpu" }
paddlepaddle-gpu = { index = "paddle-gpu" }
```

### 8.2 依赖对比（精简前 vs 精简后）

| 类别 | 精简前（paycheck-backend） | 精简后（boc-pdf2csv） |
|------|--------------------------|----------------------|
| **Web 框架** | django, djangorestframework, django-cors-headers, django-filter | — |
| **异步队列** | celery, sqlalchemy, django-celery-results | — |
| **表格处理** | openpyxl | — |
| **OCR 核心** | paddleocr, paddlepaddle, PyMuPDF, opencv-python, Pillow, torch, tqdm | ✅ 全部保留 |
| **新增** | — | numpy（显式声明） |
| **总包数** | ~15 | 6（+ paddlepaddle CPU/GPU 二选一） |

**依赖从 ~15 个缩减到 ~6 个，去除所有 Web/数据库/异步队列依赖。**

### 8.3 运行时依赖体积估算

| 组件 | 大小 |
|------|------|
| `boc-pdf2csv` 包本身 | < 100 KB |
| PyMuPDF | ~60 MB |
| opencv-python | ~30 MB |
| PaddlePaddle (CPU) | ~400 MB |
| PaddleOCR | ~10 MB |
| PyTorch (CPU) | ~150 MB |
| PaddleOCR 模型（首次运行自动下载） | ~100 MB |
| **总计** | **~750 MB** |

PaddlePaddle + PyTorch 是体积大头，但这是 OCR 的硬性成本，精简前也是这个量级。

---

## 9. 迁移策略

### 9.1 迁移原则

- **提取而非重写**：从现有代码中提取核心逻辑，保持已验证的 OCR 配置和列坐标
- **最小化接口变更**：`process_image()`、`pdf_to_images()`、`pdf_to_csv()` 的函数签名尽量不变
- **import 路径系统化替换**：`apps.ocr_service.*` → `boc_pdf2csv.*`
- **硬编码替代抽象**：BankLayout 抽象 → 直接使用 BOC 函数

### 9.2 文件映射

| 源文件 | 目标文件 | 操作 |
|--------|----------|------|
| `backend/apps/ocr_service/engine.py` | `src/boc_pdf2csv/engine.py` | 提取 + import 替换 |
| `backend/apps/ocr_service/layouts/base.py` | `src/boc_pdf2csv/layout.py` | 合并 + 去抽象化 |
| `backend/apps/ocr_service/layouts/boc.py` | （同上） | 合并到 layout.py |
| `backend/apps/ocr_service/layouts/__init__.py` | — | 删除 |
| `backend/apps/ocr_service/pipeline.py` | `src/boc_pdf2csv/pipeline.py` | 提取 + 新增 process_directory() |
| `backend/apps/ocr_service/pdf_render.py` | `src/boc_pdf2csv/pdf_render.py` | 提取 + import 替换 |
| `backend/apps/ingest/parsers/boc.py` | — | 删除（CLI 不需要回读 CSV） |
| `backend/apps/ingest/csv_utils.py` | — | 删除 |
| — | `src/boc_pdf2csv/cli.py` | 新建 |
| — | `src/boc_pdf2csv/__main__.py` | 新建 |
| `pyproject.toml` | `pyproject.toml` | 重写 |
| — | `README.md` | 新建 |

### 9.3 代码适配要点

#### `layout.py` 适配

```python
# 删除前（base.py）：
class BankLayout(ABC):
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def columns(self) -> List[Tuple[str, int, int]]: ...
    @abstractmethod
    def to_transactions(self, rows: List[Row]) -> List[dict]: ...

class BocLayout(BankLayout):
    @property
    def name(self) -> str:
        return "boc"
    @property
    def columns(self) -> List[Tuple[str, int, int]]:
        return COLUMNS_3X
    def to_transactions(self, rows: List[Row]) -> List[dict]: ...

# 适配后（layout.py）：
COLUMNS = COLUMNS_3X  # 直接导出列定义
# OCRItem, Row 保持不变
# find_table_bounds, group_items_to_rows 改为模块级函数
# to_transactions 改为模块级函数
def rows_to_transactions(rows: List[Row]) -> List[dict]:
    """BOC 行 → 交易记录"""
    # 原 BocLayout.to_transactions() 逻辑
```

#### `pipeline.py` 适配

```python
# 删除前：
from apps.ocr_service.layouts import get_layout
layout = get_layout(layout_name)  # 参数化选择银行
rows = layout.group_rows(items, scale)
txns = layout.to_transactions(rows)

# 适配后：
from boc_pdf2csv.layout import group_items_to_rows, rows_to_transactions
rows = group_items_to_rows(items, scale, COLUMNS)  # 硬编码 BOC
txns = rows_to_transactions(rows)
```

### 9.4 实施步骤

```
Phase 1                Phase 2              Phase 3              Phase 4
新建项目骨架          提取核心模块          测试 & 文档           发布
(15 min)              (45 min)              (30 min)             (15 min)
```

**Phase 1：新建项目骨架**
1. 创建目录结构 `src/boc_pdf2csv/`
2. 编写 `pyproject.toml`
3. 编写 `cli.py` 框架（argparse）
4. `uv sync` 初始化虚拟环境

**Phase 2：提取核心模块**
1. `engine.py`：从 `ocr_service/engine.py` 复制 + 改 import
2. `layout.py`：合并 `base.py` 的 Row/OCRItem/分组逻辑 + `boc.py` 的列定义/to_transactions
3. `pdf_render.py`：从 `ocr_service/pdf_render.py` 复制 + 改 import
4. `pipeline.py`：从 `ocr_service/pipeline.py` 复制 + 改 import + 新增 process_directory()
5. 确认 `uv run boc-pdf2csv --help` 正常

**Phase 3：测试 & 文档**
1. 编写 `README.md`（安装说明 + 使用示例）
2. 用示例 PDF 端到端测试
3. 边界情况测试（空目录、非 PDF 文件、损坏的 PDF）

**Phase 4：发布**
1. git commit + push
2. 可选：发布到 PyPI（`uv publish`）
3. 验证 `uv tool install boc-pdf2csv` 或 `pip install boc-pdf2csv`

### 9.5 删除清单

新仓库 `boc-pdf2csv` 仅包含上述文件。原 PayCheck 仓库保持不变，两者独立维护。

如需在原仓库中清理，删除以下内容：
- `backend/`（除 `ocr_service/` 和 `ingest/csv_utils.py` 外）
- `frontend/`
- `PayCheck/`
- `design/`
- `pyproject.toml`（根）
- 所有 Django/Celery/React 相关配置

---

## 10. 核心决策记录（ADR）

### ADR-001：硬编码 BOC 布局，取消 BankLayout 插件体系

**背景**：当前代码有 `BankLayout` 抽象基类和布局注册表，支持多银行扩展。

**决策**：去除 BankLayout 抽象，直接在 `layout.py` 中硬编码 BOC 列定义和处理函数。

**理由**：
1. YAGNI — 目前只需要 BOC，没有第二个银行的需求
2. 减少 ~200 行抽象代码（ABC、注册表、属性访问器）
3. 若未来需要支持第二家银行（如 ICBC），届时再抽象化，成本可控（BOC 列坐标是最宝贵的资产，抽象不会改变它）
4. CLI 工具不需要 `layout_name` 参数

**代价**：未来新增银行需重构 layout.py。

---

### ADR-002：不保留 parse_boc_csv 函数

**背景**：现有 `ingest/parsers/boc.py` 提供了 `parse_boc_csv()` 用于将 pipeline 生成的 CSV 回读为 dict 列表（用于写入 Django 数据库）。

**决策**：不纳入 `boc-pdf2csv` 包。

**理由**：
1. CLI 工具直接输出 CSV 给用户，不需要回读
2. `parse_boc_csv` 的 dict 结构是 Django 模型适配层，脱离 Django 无意义
3. pipeline 内部的 `_write_csv` 已经完成 CSV 序列化，不需要额外的解析层

---

### ADR-003：多 PDF 合并到单一 CSV，不去重

**背景**：用户可能把一个月的多份 PDF 放在同一目录。

**决策**：所有 PDF 交易记录合并到一个 CSV，按日期+时间排序，不去重。

**理由**：
1. 若去重，误剔除的风险（两笔相同金额的真实交易 → 丢失一笔）远大于重复的风险
2. 用户可在 Excel 中自行去重
3. 不同 PDF 通常是不同时段，交易日期不同，自然不重复

---

### ADR-004：UTF-8 with BOM 作为 CSV 输出编码

**背景**：CSV 文件需要在 Excel 中直接打开。

**决策**：输出 UTF-8 with BOM（`﻿` 前缀）。

**理由**：
1. Excel 对无 BOM 的 UTF-8 CSV 会错误解释中文字符
2. BOM 是一个字符的开销，换来零配置的 Excel 兼容性
3. 中国银行账单用户以中文 Windows + Excel 为主

---

### ADR-005：max_workers 默认值

**背景**：`pdf_render.py` 使用多进程渲染 PDF 页面。

**决策**：`max_workers = min(os.cpu_count() or 4, 10)`，与现有代码保持一致。

**理由**：
1. PDF 渲染是 I/O + CPU 混合，多进程有真实加速
2. 上限 10 避免在高端服务器上过度并行导致内存压力
3. 单份 BOC 账单通常 1-3 页，并行收益有限但保留代码不变

---

> **文档结束**。本文档作为 TCY-78 的 STAGE_DESIGN 产出物，覆盖 `boc-pdf2csv` 包的完整架构设计。
>
> 实施由后续 CODE 阶段执行。
