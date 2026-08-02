# boc-pdf2csv Python 包架构设计

> **作者**: 架构师
> **日期**: 2026-08-03
> **版本**: 1.0
> **关联 Issue**: TCY-78（父 Issue: TCY-77）

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [现状分析：现有代码盘点](#2-现状分析现有代码盘点)
3. [方案设计](#3-方案设计)
4. [项目结构](#4-项目结构)
5. [模块设计](#5-模块设计)
6. [CLI 设计](#6-cli-设计)
7. [核心数据流](#7-核心数据流)
8. [依赖清单](#8-依赖清单)
9. [从现有代码的迁移策略](#9-从现有代码的迁移策略)
10. [ADR：核心架构决策](#10-adr核心架构决策)
11. [实施步骤](#11-实施步骤)
12. [风险与注意事项](#12-风险与注意事项)

---

## 1. 背景与目标

### 1.1 问题陈述

当前 PayCheck 是一个 Django + React 全栈项目，包含渠道管理、交易标签、统计分析、OCR 管线等多个子系统。但用户的核心需求只有一个：**将中国银行导出的 PDF 对账单转换为 CSV 文件**。

其他功能（支付宝/微信解析、标签系统、Web 前端、REST API）均非核心需求，却显著增加了项目的维护负担：
- Django + DRF 框架带来大量样板代码
- 前端 React 项目独立维护
- 多渠道解析器增加了不必要的抽象层
- Celery/ThreadPool 任务调度为单机场景过度设计

### 1.2 目标

将核心的"中国银行 PDF → CSV"功能从 PayCheck 中剥离，创建一个独立的 Python 包：

| 属性 | 说明 |
|------|------|
| 包名 | `boc-pdf2csv` |
| 项目形式 | `uv` 管理的 Python 项目 |
| CLI 命令 | `boc-pdf2csv` |
| CLI 接口 | 输入文件夹路径 → 输出一个 CSV 文件 |
| 功能范围 | 仅支持中国银行 PDF 对账单，不扩展其他银行 |
| Python 版本 | `>=3.10, <3.14` |

---

## 2. 现状分析：现有代码盘点

### 2.1 相关模块清单

现有 PayCheck 后端中与 BOC PDF→CSV 相关的模块：

```
backend/apps/
├── ocr_service/
│   ├── layouts/
│   │   ├── __init__.py       # 布局注册表（register_layout / get_layout）
│   │   ├── base.py           # BankLayout ABC + OCRItem/Row + table检测 + 行分组
│   │   └── boc.py            # BOC 列坐标 + BocLayout 实现
│   ├── engine.py             # PaddleOCR 引擎封装（惰性初始化单例）
│   ├── pdf_render.py         # PyMuPDF 渲染 PDF → 裁剪后 PNG（多进程）
│   └── pipeline.py           # 管线编排：pdf_to_images → images_to_csv
├── ingest/
│   ├── csv_utils.py          # CSV 行解析（处理引号包裹字段）
│   ├── executor.py           # ThreadPoolExecutor 单例（Django 内异步任务）
│   └── parsers/
│       └── boc.py            # BOC CSV 解析器（OCR 产物 → dict 列表）
```

### 2.2 代码评估

| 模块 | 行数 | 保留价值 | 评估 |
|------|------|----------|------|
| `ocr_service/layouts/base.py` | ~218 | ★★★ 核心 | 表格检测算法 + 行分组逻辑，直接复用 |
| `ocr_service/layouts/boc.py` | ~105 | ★★★ 核心 | BOC 列坐标 + 交易转换，直接复用 |
| `ocr_service/layouts/__init__.py` | ~40 | ★☆☆ 冗余 | 布局注册表模式，单银行场景不需要 |
| `ocr_service/engine.py` | ~113 | ★★★ 核心 | PaddleOCR 封装，去掉 Django 日志路径即可 |
| `ocr_service/pdf_render.py` | ~136 | ★★★ 核心 | PDF 渲染 + 裁剪，去掉 Django 模块引用即可 |
| `ocr_service/pipeline.py` | ~276 | ★★★ 核心 | 管线编排 + CSV 写出，直接复用 |
| `ingest/csv_utils.py` | ~28 | ★★☆ 工具 | CSV 行解析，直接复用 |
| `ingest/parsers/boc.py` | ~134 | ★☆☆ 多余 | OCR 产物 CSV 再解析，新包不需要此二次解析 |
| `ingest/executor.py` | ~82 | ★☆☆ 不需要 | Django 内的线程池，新包使用 multiprocessing 即可 |

### 2.3 依赖关系图（现状）

```
ingest/parsers/boc.py ──→ ingest/csv_utils.py
                              ↑
pipeline.py ──→ engine.py ──→ layouts/__init__.py ──→ layouts/base.py
    │                                           └──→ layouts/boc.py
    ├──→ pdf_render.py ──→ layouts/base.py (find_table_bounds)
    └──→ (csv 写出：内联 _esc_csv + _write_csv)
```

---

## 3. 方案设计

### 3.1 方案对比

#### 方案 A：最小化封装（推荐 ✅）

直接将 OCR 管线模块从 Django 中剥离，合并冗余文件，硬编码 BOC 布局。

- **优点**：代码量最小（~500 行），维护成本低，无多余抽象
- **缺点**：不支持未来扩展其他银行（但这不是目标）
- **适用场景**：单一银行、单一功能，即当前需求

#### 方案 B：保留注册表模式

保留 `BankLayout` ABC + 注册表，仅注册 BOC，预留扩展点。

- **优点**：未来加银行只需加 layout 文件
- **缺点**：为"可能不会发生"的需求保留抽象，违反 YAGNI
- **适用场景**：预期短期内会加入多家银行

#### 方案 C：完整迁移 + 精简

将整个 `ocr_service` + `ingest/parsers` 完整迁移，保留所有现有 parser（支付宝/微信/BOC），仅移除 Django 依赖。

- **优点**：功能最完整
- **缺点**：与"精简化"目标矛盾，用户明确只要 BOC
- **适用场景**：需要多平台支持的场景

### 3.2 推荐方案

**选择方案 A — 最小化封装**。

理由：
1. **YAGNI**：用户明确只需要中国银行 PDF 转 CSV，无多银行扩展计划
2. **简单优先**：移除注册表、ABC、多渠道 parser 等抽象层，降低认知负担
3. **可演进性**：如果未来确实需要加银行，可以将 `layout.py` 中的 BOC 常量提取为参数，成本很低
4. **代码量对比**：方案 A ~500 行 vs 方案 C ~1200 行

---

## 4. 项目结构

### 4.1 目录树

```
boc-pdf2csv/
├── pyproject.toml                 # uv 项目配置 + 依赖 + CLI 入口
├── README.md                      # 使用文档
├── LICENSE                        # MIT
├── src/
│   └── boc_pdf2csv/
│       ├── __init__.py            # 版本号 + 公开 API
│       ├── __main__.py            # python -m boc_pdf2csv 入口
│       ├── cli.py                 # argparse CLI + main()
│       ├── pdf_render.py          # PDF → 裁剪后 PNG 图片
│       ├── ocr_engine.py          # PaddleOCR 引擎封装（单例）
│       ├── layout.py              # BOC 列布局 + 表格检测 + 行分组 + 交易转换
│       ├── pipeline.py            # 管线编排：PDF → OCR → CSV
│       └── csv_writer.py          # CSV 写出 + CSV 行解析工具
└── tests/
    ├── __init__.py
    ├── test_layout.py             # 表格检测 + 行分组单元测试
    ├── test_csv_writer.py         # CSV 写出单元测试
    └── test_pipeline.py           # 端到端管线集成测试
```

### 4.2 与现有代码的映射

| 新模块 | 来源 | 变更说明 |
|--------|------|----------|
| `pdf_render.py` | `ocr_service/pdf_render.py` | 移除 `apps.*` 导入，调整 import 路径 |
| `ocr_engine.py` | `ocr_service/engine.py` | 移除 `apps.*` 导入，移除 PaddleX 日志接管逻辑 |
| `layout.py` | `layouts/base.py` + `layouts/boc.py` + `layouts/__init__.py` | **三合一**：ABC + 注册表 → 具体实现，删除未使用的 `detect_table` 覆写点 |
| `pipeline.py` | `ocr_service/pipeline.py` | 移除 `apps.*` 导入，内联 `get_layout` 调用为直接 import |
| `csv_writer.py` | `ingest/csv_utils.py` + pipeline 中的 `_write_csv`/`_esc_csv` | **二合一**：CSV 解析 + 写出在同一模块 |
| `cli.py` | 全新 | argparse CLI，替代 Django management command |
| `__main__.py` | 全新 | `python -m boc_pdf2csv` 入口 |

---

## 5. 模块设计

### 5.1 `__init__.py` — 包入口

```python
"""boc-pdf2csv: 中国银行 PDF 对账单 → CSV 转换工具"""
__version__ = "1.0.0"

from boc_pdf2csv.pipeline import process_folder, process_pdf
```

公开 API：
- `process_pdf(pdf_path, output_path, scale, timeout)` — 单个 PDF → CSV
- `process_folder(folder_path, output_path, scale, timeout)` — 文件夹批量处理

### 5.2 `cli.py` — 命令行接口

纯 argparse，无第三方依赖。

```python
def main():
    parser = argparse.ArgumentParser(
        prog="boc-pdf2csv",
        description="将中国银行 PDF 对账单转换为 CSV 文件",
    )
    parser.add_argument("input", help="包含 PDF 文件的文件夹路径")
    parser.add_argument("--output", "-o", default="output.csv", help="输出 CSV 文件路径（默认: output.csv）")
    parser.add_argument("--scale", type=float, default=3.0, help="PDF 渲染倍率（默认: 3.0）")
    parser.add_argument("--timeout", type=int, default=60, help="单个 PDF 超时分钟数（默认: 60）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")
    parser.add_argument("--version", action="version", version=f"boc-pdf2csv {__version__}")
    args = parser.parse_args()
    # → 调用 pipeline.process_folder()
```

### 5.3 `pdf_render.py` — PDF 渲染

**职责**：将 PDF 每页渲染为裁剪后的 PNG 图片。

**公开函数**：
- `render_page(pdf_path, page_num, scale)` → `PIL.Image` — 单页渲染 + 裁剪（内存）
- `pdf_to_images(pdf_path, scale, output_dir, max_workers)` → `List[str]` — 批量渲染到文件

**核心依赖**：`fitz`（PyMuPDF）、`PIL`（Pillow）

**关键算法**：
1. `fitz.Matrix(scale, scale)` 渲染页面为 pixmap
2. `PIL.Image.frombytes()` 转为 PIL Image
3. `find_table_bounds()` 裁剪到表格区域

**变更点**：移除 `from apps.ocr_service.layouts.base import find_table_bounds` → `from boc_pdf2csv.layout import find_table_bounds`

### 5.4 `ocr_engine.py` — OCR 引擎

**职责**：封装 PaddleOCR，提供简洁的文字识别接口。

**公开函数**：
- `warmup_engine()` — 预加载 OCR 模型（避免首张图片等待）
- `process_image(image_input)` → `List[OCRItem]` — 识别图片中的文字块

**内部数据**：模块级 `_ocr` 单例（惰性初始化）

**核心依赖**：`paddleocr`、`cv2`（opencv-python）、`numpy`

**变更点**：
- 移除 PaddleX 日志接管逻辑（`_paddlex_log` handler 清理）— 新包不需要
- 移除 `from apps.ocr_service.layouts.base import OCRItem` → 本地定义

### 5.5 `layout.py` — BOC 布局（核心模块）

**职责**：定义 BOC 银行流水单的列坐标、OCR 结果结构化、表格检测。

**公开数据类**：
- `OCRItem(text, cx, cy)` — OCR 识别文字块
- `Row(date, time, currency, amount, balance, tx_name, channel, branch, counterparty, memo, cp_account, cp_bank)` — 一行交易

**公开函数**：
- `find_table_bounds(pil_image)` → `(top, bottom, left, right)` — 亮度分析法检测表格区域
- `group_items_to_rows(items, scale)` → `List[Row]` — OCR 文字块 → 行数据
- `rows_to_transactions(rows)` → `List[dict]` — 行数据 → 标准交易字典列表

**常量**：
- `BOC_COLUMNS` — 12 列坐标定义（基于 3.0x 缩放，字段名 + x_min + x_max）
- `FIELD_*` / `BANK_COL_*` — 字段名常量

**关键算法 — 表格检测**（`find_table_bounds`）：
```
1. PIL Image → numpy 亮度矩阵 (H×W)
2. 逐行统计深色像素数（亮度 < 220）
3. 合并相邻内容行（间隔 ≤ 5px 视为同一块）
4. 取最大块 = 表格区域
5. 在表格行范围内逐列扫描，确定水平边界
```

**关键算法 — 行分组**（`group_items_to_rows`）：
```
1. 按 scale 缩放列坐标
2. 将每个 OCR 文字块按其 cx 分配到对应列
3. 以 date 列的 Y 坐标作为行锚点
4. 其余列的文字块按 Y 轴最近邻匹配到相应行（距离 ≤ 40*scale）
```

**变更点**：合并 base.py + boc.py 为单文件，移除 `BankLayout` ABC 和注册表模式。

**BOC 列坐标**（3.0x 缩放基准，共 12 列）：
```
记账日期(0-202)  记账时间(202-380)  币别(380-553)  金额(553-737)  余额(737-923)
交易名称(923-1093)  渠道(1093-1266)  网点名称(1266-1469)  附言(1469-1689)
对方账户名(1689-1909)  对方卡号/账号(1909-2180)  对方开户行(2180-9999)
```

### 5.6 `pipeline.py` — 管线编排

**职责**：编排 PDF → 图片 → OCR → CSV 的完整流程。

**公开函数**：
- `process_pdf(pdf_path, output_path=None, scale=3.0, timeout_minutes=60, verbose=False)` → `str` — 单个 PDF 处理，返回 CSV 内容
- `process_folder(folder_path, output_path, scale=3.0, timeout_minutes=60, verbose=False)` → `str` — 批量处理文件夹内所有 PDF，合并输出

**内部流程**（`process_pdf`）：
```
1. 验证 PDF 文件存在
2. pdf_to_images(pdf_path, scale) → 临时目录中的 PNG 文件
3. 逐页：warmup_engine() → process_image(png) → group_items_to_rows() → rows_to_transactions()
4. 按页码排序后 merge 所有交易
5. write_csv(transactions, output_path) → 写出 CSV
```

**内部流程**（`process_folder`）：
```
1. 扫描文件夹中所有 .pdf 文件
2. 每个 PDF 调用 process_pdf()
3. 合并所有 PDF 的交易记录
4. 去重（按日期+金额+对方账户名）
5. 按时间排序
6. write_csv() → 单个 CSV 输出
```

**CSV 输出格式**（13 列）：
```csv
date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank
```

### 5.7 `csv_writer.py` — CSV 工具

**职责**：CSV 读写工具。

**公开函数**：
- `write_csv(transactions, output_path)` → `str` — 写 CSV 文件，返回内容字符串
- `parse_csv_line(line)` → `List[str]` — 解析单行 CSV（处理引号包裹字段）

---

## 6. CLI 设计

### 6.1 命令格式

```bash
# 基本用法：转换文件夹内所有 PDF
boc-pdf2csv ./statements/

# 指定输出文件
boc-pdf2csv ./statements/ --output result.csv
boc-pdf2csv ./statements/ -o result.csv

# 调整渲染精度（低配机器可用 2.0）
boc-pdf2csv ./statements/ --scale 2.0

# 延长超时（大批量文件）
boc-pdf2csv ./statements/ --timeout 120

# 查看版本
boc-pdf2csv --version

# 详细日志
boc-pdf2csv ./statements/ --verbose
```

### 6.2 参数规范

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input` | 位置参数 | 必填 | 包含 PDF 文件的文件夹路径 |
| `--output`, `-o` | str | `output.csv` | 输出 CSV 文件路径 |
| `--scale` | float | `3.0` | PDF 渲染倍率，影响 OCR 精度和速度 |
| `--timeout` | int | `60` | 单个 PDF 超时分钟数 |
| `--verbose`, `-v` | flag | False | 开启 DEBUG 级别日志 |
| `--version` | flag | — | 打印版本号并退出 |

### 6.3 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 输入路径不存在或非目录 |
| 2 | 未找到 PDF 文件 |
| 3 | 处理失败（部分或全部 PDF） |
| 4 | 未提取到任何交易记录 |

### 6.4 进度显示

使用 `tqdm` 显示进度，分两层：
- 外层：PDF 文件进度（"处理 PDF: statement1.pdf [2/5]"）
- 内层：每页的 OCR 进度（通过 `pdf_to_images` 内部 tqdm）

`--verbose` 模式下额外输出：
- 每页 OCR 识别到的文字块数量
- 每页提取的交易记录条数
- PaddleOCR 模型加载时间

---

## 7. 核心数据流

### 7.1 端到端数据流

```
┌─────────────────┐
│  PDF 文件夹       │
│  ├── 1月.pdf     │
│  ├── 2月.pdf     │
│  └── 3月.pdf     │
└──────┬──────────┘
       │ CLI: boc-pdf2csv ./folder/ -o out.csv
       ▼
┌─────────────────┐
│  cli.py          │  argparse 解析参数
│  main()          │  调用 pipeline.process_folder()
└──────┬──────────┘
       │
       ▼ （每个 PDF）
┌─────────────────┐
│  pdf_render.py   │  PyMuPDF 渲染每页
│  pdf_to_images() │  → 3.0x 缩放 → 表格区域裁剪
│                  │  → 临时 PNG 文件列表
└──────┬──────────┘
       │ 每页一张 PNG
       ▼
┌─────────────────┐
│  ocr_engine.py   │  PaddleOCR 识别
│  process_image() │  → OCRItem(text, cx, cy) 列表
└──────┬──────────┘
       │ OCR 文字块列表
       ▼
┌─────────────────┐
│  layout.py        │  按 BOC 列坐标分配
│  group_items_    │  → 以 date 列为锚点行分组
│  to_rows()       │  → Row 数据对象列表
│  rows_to_        │  → List[dict] 标准交易记录
│  transactions()  │
└──────┬──────────┘
       │ 交易 dict 列表
       ▼
┌─────────────────┐
│  csv_writer.py   │  CSV 格式化 + 写出
│  write_csv()     │  → output.csv
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  output.csv      │  13 列标准 CSV
└─────────────────┘
```

### 7.2 状态机

```
                    ┌─────────────┐
                    │  IDLE       │
                    └──────┬──────┘
                           │ CLI 调用
                           ▼
                    ┌─────────────┐
                    │  SCANNING   │ 扫描文件夹内 PDF
                    └──────┬──────┘
                           │ 找到 PDF 列表
                           ▼
              ┌─────────────────────┐
              │  RENDERING          │ PDF → PNG（多进程）
              │  (per PDF)          │
              └──────────┬──────────┘
                         │ PNG 文件列表
                         ▼
              ┌─────────────────────┐
              │  OCR                │ PaddleOCR 识别（逐页）
              │  (per page)         │
              └──────────┬──────────┘
                         │ OCRItem 列表
                         ▼
              ┌─────────────────────┐
              │  STRUCTURING        │ 列分配 + 行分组
              │  (per page)         │
              └──────────┬──────────┘
                         │ Row 列表
                         ▼
              ┌─────────────────────┐
              │  WRITING            │ CSV 格式化 + 写出
              │                     │
              └──────────┬──────────┘
                         │
                         ▼
                    ┌─────────────┐
                    │  DONE       │ → 退出码
                    └─────────────┘
```

### 7.3 事务字典格式

```python
# 每个交易记录的内部结构（pipeline 内部流转）
{
    "date":         "2024-01-15",       # 记账日期
    "time":         "10:23:45",         # 记账时间
    "tx_type":      "支出",             # 交易类型（支出/收入）
    "amount":       1500.00,            # 金额（正数）
    "counterparty":  "张三",             # 对方账户名
    "channel":      "手机银行",          # 交易渠道
    "balance":      25000.50,           # 余额
    "memo":         "转账",             # 附言
    "tx_name":      "个人转账支出",       # 交易名称
    "currency":     "人民币",            # 币别
    "branch":       "北京分行",          # 网点名称
    "cp_account":   "6222****1234",     # 对方卡号/账号
    "cp_bank":      "中国工商银行",       # 对方开户行
}
```

---

## 8. 依赖清单

### 8.1 必需依赖

| 包名 | 版本约束 | 用途 | 备注 |
|------|----------|------|------|
| `paddleocr` | `>=3.6.0` | OCR 文字识别引擎 | 核心依赖，体积大（~500MB 含模型） |
| `paddlepaddle` | `>=2.6.0` | PaddleOCR 深度学习后端（CPU 版） | 默认 CPU 版本 |
| `PyMuPDF` | `>=1.23.0` | PDF 渲染为图片 | 轻量，约 20MB |
| `opencv-python` | `>=4.8.0` | 图片加载与预处理 | `cv2.imread()` |
| `Pillow` | `>=10.0` | PIL Image 操作 | PyMuPDF 输出格式转换 |
| `numpy` | `>=1.24` | 数组运算（表格检测） | paddleocr 也会安装 |
| `tqdm` | `>=4.60.0` | 进度条显示 | 轻量，纯 Python |
| `torch` | `>=2.0.0` | PyTorch 运行时 | paddleocr 依赖 |

### 8.2 可选依赖

| 包名 | 版本约束 | 用途 |
|------|----------|------|
| `paddlepaddle-gpu` | `>=2.6.0` | GPU 加速（替代 `paddlepaddle`） |

### 8.3 pyproject.toml 配置

```toml
[project]
name = "boc-pdf2csv"
version = "1.0.0"
description = "中国银行 PDF 对账单 → CSV 转换工具"
requires-python = ">=3.10, <3.14"
dependencies = [
    "paddleocr>=3.6.0",
    "paddlepaddle>=2.6.0",
    "PyMuPDF>=1.23.0",
    "opencv-python>=4.8.0",
    "Pillow>=10.0",
    "numpy>=1.24",
    "tqdm>=4.60.0",
    "torch>=2.0.0",
]

[project.optional-dependencies]
gpu = ["paddlepaddle-gpu>=2.6.0"]

[project.scripts]
boc-pdf2csv = "boc_pdf2csv.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

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

### 8.4 依赖说明

1. **PaddleOCR + paddlepaddle + torch 是最重的依赖**（合计 ~2GB），但这正是现有 PayCheck 项目的核心依赖，无法避免
2. **PyMuPDF** 用于 PDF 渲染，比 pdf2image + poppler 更轻量且无需系统级依赖
3. **不使用 Django/DRF/Celery** 等 Web 框架，安装体积大幅减小
4. **GPU 加速可选**：`uv sync --extra gpu` 安装 GPU 版本 paddlepaddle

---

## 9. 从现有代码的迁移策略

### 9.1 总体策略

**三步走**：提取核心 → 合并精简 → 添加新层（CLI）

```
Phase 1: 提取核心模块           Phase 2: 合并精简             Phase 3: 添加 CLI + 包配置
─────────────────────────     ────────────────────────     ───────────────────────────
ocr_service/pdf_render.py  →  pdf_render.py                cli.py (新增)
ocr_service/engine.py      →  ocr_engine.py                __main__.py (新增)
ocr_service/pipeline.py    →  pipeline.py                  pyproject.toml (新增)
layouts/base.py            ┐                               README.md (新增)
layouts/boc.py             ├→ layout.py (三合一)
layouts/__init__.py        ┘
ingest/csv_utils.py        ┐
pipeline._write_csv        ┘→ csv_writer.py (二合一)
ingest/parsers/boc.py      →  X  不迁移（二次解析不需要）
ingest/executor.py         →  X  不迁移（Django 专属）
```

### 9.2 代码变更详情

#### Phase 1: 提取（复制 + 去 Django 化）

每个文件的变更模式：
```diff
- from apps.ocr_service.layouts.base import BankLayout, Row, OCRItem, find_table_bounds
- from apps.ocr_service.layouts import get_layout
+ from boc_pdf2csv.layout import Row, OCRItem, find_table_bounds, BOC_COLUMNS, group_items_to_rows, rows_to_transactions

- from apps.ocr_service.engine import process_image, warmup_engine
+ from boc_pdf2csv.ocr_engine import process_image, warmup_engine

- from apps.ocr_service.pdf_render import pdf_to_images
+ from boc_pdf2csv.pdf_render import pdf_to_images
```

#### Phase 2: 合并精简

**layout.py 合并**：
- `base.py` 的 `OCRItem`、`Row` 数据类 + `find_table_bounds()` + `group_items_to_rows()` → 保留
- `boc.py` 的 `BOC_COLUMNS` 常量 + `BocLayout.to_transactions()` → 重命名为 `rows_to_transactions()` 保留
- `__init__.py` 的注册表 → **删除**，BOC 布局直接硬编码调用

**csv_writer.py 合并**：
- `csv_utils.py` 的 `parse_csv_line()` → 保留（虽然当前管线不直接使用 CSV 解析，但保留作为工具函数）
- `pipeline.py` 的 `_write_csv()` + `_esc_csv()` → 提取为 `write_csv()`，从私有改为公开

#### Phase 3: 新建

- `cli.py`：从头编写 argparse CLI
- `pyproject.toml`：参考现有根 `pyproject.toml` 和 `backend/pyproject.toml`
- `README.md`：包含安装说明、使用示例、CSV 输出格式说明

### 9.3 不迁移的模块

| 模块 | 原因 |
|------|------|
| `ingest/parsers/boc.py` | 该模块解析 OCR 已生成的 CSV 文件（二次解析），新包直接从 OCR 输出写 CSV，不需要此中间步骤 |
| `ingest/executor.py` | Django 内的线程池任务调度，新包使用直接函数调用 + multiprocessing |
| `ingest/parsers/alipay.py` | 支付宝解析，不在需求范围 |
| `ingest/parsers/wechat.py` | 微信解析，不在需求范围 |
| `ocr_service/layouts/__init__.py` | 注册表模式，单银行场景冗余 |
| `transactions/*` | Django 模型 + 标签系统，不在需求范围 |
| `analysis/*` | 统计分析，不在需求范围 |
| `channels/*` | 渠道管理，不在需求范围 |

---

## 10. ADR：核心架构决策

### ADR-009：选择独立 Python 包而非 Django 子模块

**状态**：提议

**背景**：现有 BOC PDF 解析功能嵌入在 Django 项目中。用户需要将该功能独立出来。

**决策**：创建独立的 `boc-pdf2csv` Python 包，完全移除 Django 依赖。

**理由**：
- 用户明确只需要 CLI 工具，不需要 Web 界面
- Django 带来大量不必要的依赖（DRF、django-filter、django-cors-headers 等）
- 独立包可通过 `pip install` 或 `uv add` 直接使用，分发更便捷

**后果**：
- ✅ 安装体积减小 ~80%（无需 Django 生态）
- ✅ 可在任意 Python 环境中使用，不依赖 Django project 结构
- ❌ 与 PayCheck 后端的代码共享变为手动同步（可接受——新包是"精简版"，PayCheck 后端保留完整功能做参考）

### ADR-010：移除布局注册表，硬编码 BOC 布局

**状态**：提议

**背景**：现有 `ocr_service/layouts/` 使用 `BankLayout` ABC + 注册表模式支持多家银行布局。

**决策**：在 `boc-pdf2csv` 中移除 ABC 和注册表，将 BOC 布局硬编码为具体函数。

**理由**：
- 目前仅有 BOC 一种布局被实际使用和测试
- 注册表模式为"可能不会发生"的扩展保留抽象
- 如果未来需要加银行，将函数参数化即可（例如传入自定义列坐标）

**后果**：
- ✅ 减少 3 个文件 → 1 个文件（base.py + boc.py + __init__.py → layout.py）
- ✅ 代码行数减少 ~40%
- ❌ 未来加银行需要重构 layout.py（但影响面可控）

### ADR-011：两阶段管线：PDF→图片→OCR→CSV（保留现有架构）

**状态**：提议

**背景**：现有管线分两阶段——先用 PyMuPDF 渲染 PDF 为图片，再用 PaddleOCR 识别图片中的文字。

**决策**：保留两阶段管线架构不变。

**理由**：
- 阶段分离使得调试更容易（中间图片可检查）
- 图片文件缓存便于 OCR 失败时重试（只重跑 OCR，不用重新渲染）
- PyMuPDF 的渲染和 PaddleOCR 的识别是两个正交的耗时操作
- 这一架构已在生产环境验证可行

**后果**：
- ✅ 架构稳定可靠，已在现有 PayCheck 中验证
- ❌ 需要临时存储中间图片（使用 `tempfile.TemporaryDirectory`，自动清理）
- ❌ 两阶段比直接 PDF→OCR 多一步 I/O（但简化了 OCR 实现——PaddleOCR 只处理图片）

### ADR-012：CSV 直接写出，无需二次解析

**状态**：提议

**背景**：现有 PayCheck 管线是 PDF→OCR→CSV（写入文件）→再解析 CSV（读取文件）→入库。这是因为 Django ingest 流程的设计。`ingest/parsers/boc.py` 负责二次解析。

**决策**：新包直接从 OCR 结构化数据写出 CSV，跳过"写 CSV→再读 CSV"的循环。

**理由**：
- OCR 结构化后的交易数据已经在内存中（`List[dict]`），直接写出即可
- 不必为了"统一入库接口"而做多余的序列化/反序列化
- 减少一个 io 循环，也消除了 CSV 解析中的编码问题

**后果**：
- ✅ 管线更简洁：1 次写入 vs 1 次写入 + 1 次读取
- ❌ `csv_utils.py` 中的 `parse_csv_line()` 在当前管线中不再使用（保留作为工具函数备用）

---

## 11. 实施步骤

### 第一阶段：创建项目骨架（预计 30 分钟）

1. 创建 `boc-pdf2csv/` 目录结构
2. 编写 `pyproject.toml`（含依赖 + CLI 入口 + paddle 源配置）
3. 编写 `README.md`
4. `uv sync` 验证依赖可安装

### 第二阶段：迁移核心模块（预计 1 小时）

1. 复制 `pdf_render.py`，调整 import
2. 复制 `ocr_engine.py`，调整 import
3. 合并 `layout.py`（三合一）
4. 合并 `csv_writer.py`（二合一）
5. 迁移 `pipeline.py`，调整 import，添加 `process_folder()`

### 第三阶段：添加 CLI 层（预计 30 分钟）

1. 编写 `cli.py`
2. 编写 `__main__.py`
3. 端到端测试：`uv run boc-pdf2csv ./test-data/ -o out.csv`

### 第四阶段：测试验证（预计 30 分钟）

1. 单元测试：表格检测、行分组、CSV 写出
2. 集成测试：取一份真实 BOC PDF，验证端到端流程
3. 与现有 PayCheck 后端的输出对比，确保 CSV 格式一致

### 第五阶段：文档与发布（预计 30 分钟）

1. 完善 README（安装说明 + 使用示例 + 输出格式）
2. 推送到 GitHub 独立仓库或本仓库子目录
3. 可选：发布到 PyPI

---

## 12. 风险与注意事项

### 12.1 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| PaddleOCR 模型下载失败 | 中 | 高 | README 中说明离线安装方案；考虑 pre-download 模型到包内 |
| BOC 银行修改 PDF 格式 | 低 | 高 | 列坐标作为常量定义，修改只需更新 `BOC_COLUMNS` |
| 大 PDF（100+ 页）处理超时 | 中 | 中 | `--timeout` 参数可调节；分批处理建议写在 README |
| CPU 版本 paddlepaddle 安装失败 | 中 | 中 | 提供 GPU 版本作为 fallback；注明 paddle 官方源 URL |
| Windows 编码问题 | 低 | 中 | BOC PDF 含中文，CSV 统一用 UTF-8 BOM 保证 Excel 兼容 |

### 12.2 注意事项

1. **CSV 编码**：输出使用 UTF-8 with BOM，确保 Windows Excel 双击即可正常打开中文
2. **PDF 文件名**：建议用户使用有意义的文件名（如 "2024年1月.pdf"），管线不依赖文件名解析
3. **临时文件清理**：使用 `tempfile.TemporaryDirectory` 作为上下文管理器，确保异常退出时也能清理
4. **日志级别**：默认 WARNING（仅错误和警告），`--verbose` 开启 INFO，便于排查问题
5. **并发安全**：PaddleOCR 的 `_ocr` 单例在多进程 worker 中每个进程独立一份（通过 `ProcessPoolExecutor` 隔离），无竞态问题

---

## 附录 A：与现有 PayCheck 的关系

```
现有 PayCheck（Django 全栈）          新 boc-pdf2csv（独立包）
─────────────────────────────        ─────────────────────────
backend/apps/ocr_service/*     →     src/boc_pdf2csv/*（精简版）
backend/apps/ingest/parsers/boc →     （不再需要二次解析）
backend/apps/ingest/csv_utils   →     src/boc_pdf2csv/csv_writer.py
backend/apps/transactions/*     →     （不迁移）
backend/apps/channels/*         →     （不迁移）
frontend/*                      →     （不迁移）
```

PayCheck 后端保留完整代码作为参考实现，`boc-pdf2csv` 只包含核心管线。

## 附录 B：CSV 输出示例

```csv
date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank
2024-01-15,10:23:45,支出,1500.00,张三,手机银行,25000.50,转账,个人转账支出,人民币,北京分行,6222****1234,中国工商银行
2024-01-16,14:05:12,收入,8000.00,李四,网上银行,33000.50,工资,工资收入,人民币,北京分行,6228****5678,中国建设银行
2024-01-17,09:30:00,支出,200.00,中国移动,手机银行,32800.50,话费充值,手机充值,人民币,北京分行,10086,,中国移动通信
```
