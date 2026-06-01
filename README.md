<p align="center">
  <h1 align="center">📊 PayCheck</h1>
  <p align="center"><strong>个人账单统计工具</strong></p>
  <p align="center">聚合微信 · 支付宝 · 银行三渠道账单，自动剔除内部转账，生成交互式 HTML 分析报告</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-0.2.0-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/GPU-CUDA%2012.6-orange?logo=nvidia" alt="CUDA">
</p>

---

## 📋 目录

- [简介](#简介)
- [前置依赖](#前置依赖)
- [安装](#安装)
- [快速开始](#快速开始)
- [数据流](#数据流)
- [核心能力](#核心能力)
  - [多平台账单解析](#多平台账单解析)
  - [银行流水 OCR](#银行流水-ocr)
  - [内部转账过滤](#内部转账过滤)
  - [分析维度](#分析维度)
- [扩展：新增银行](#扩展新增银行)
- [故障排查](#故障排查)
- [依赖](#依赖)
- [许可](#许可)

---

## 简介

**PayCheck** 是一款个人账单聚合分析工具。它将分散在微信、支付宝、中国银行（BOC）等多个渠道的账单汇总到统一管线下，经过 **PDF 渲染 → OCR 识别 → 结构化解析 → 聚合统计** 流程，最终生成 ECharts 驱动的交互式 HTML 报表。

核心特性：

- **多源聚合** — 微信 `.xlsx`、支付宝 `.csv`、银行 `.pdf` / `.csv` 统一处理
- **自动 OCR** — 基于 PaddleOCR 的银行流水 PDF 识别管线，支持表格自动检测与裁剪
- **智能过滤** — 自动剔除"充值/提现/零钱"等内部转账，还原真实消费
- **可视化报表** — ECharts 5 交互式 HTML，含月度趋势、平台对比、类别分布
- **可扩展** — 新增银行只需实现布局接口 + 注册，无需改动现有代码

---

## 前置依赖

- **操作系统**: Windows / macOS / Linux
- **Python**: 3.10 ~ 3.11（PaddlePaddle 兼容性要求）
- **GPU**（推荐）: NVIDIA GPU + CUDA 12.6，用于加速 OCR 推理
- **Package Manager**: [uv](https://docs.astral.sh/uv/)（推荐）或 pip

> 无 GPU 也可运行（自动回退 CPU），但 OCR 速度会明显降低。

---

## 安装

### 1. 安装 uv（如未安装）

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆并安装依赖

```bash
git clone <repo-url>
cd paycheck
uv sync
```

`uv sync` 会自动从自定义索引拉取 PaddlePaddle GPU 版和 PyTorch（CUDA 12.6）。如需 CPU 版本，手动修改 `pyproject.toml` 中的索引 URL。

### 3. 验证安装

```bash
uv run paycheck --help
```

---

## 快速开始

```bash
# ---------- 三阶段工作流（推荐，可任意重跑某一步） ----------
uv run paycheck pdf2image <input_dir>          # ① PDF → 页面图片
uv run paycheck image2csv <input_dir>/boc/     # ② 图片 → CSV
uv run paycheck analyse <input_dir>            # ③ 分析 → 报表

# 快捷方式（合并前两步）
uv run paycheck pdf2image <input_dir>          # ① PDF → 图片
uv run paycheck image2csv <input_dir>/boc/     # ② 图片 → CSV
uv run paycheck analyse <input_dir> -o report.html
```

**输入目录结构约定**：

```
<input_dir>/
├── wechat/          ← 微信支付 (.xlsx)
│   └── *.xlsx
├── ant/             ← 支付宝 (.csv)
│   └── *.csv
└── boc/             ← 中国银行 (.pdf / .csv)
    └── *.pdf
```

---

## 数据流

三阶段管道，渲染 / OCR / 分析完全解耦：

```
第一阶段: pdf2image               第二阶段: image2csv             第三阶段: analyse
┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────────┐
│ <input_dir>/boc/*.pdf    │    │ <input_dir>/boc/          │    │ <input_dir>/                  │
│       ↓                  │    │  *_p*.png 图片           │    │ ├── wechat/*.xlsx           │
│  PDF → 图片渲染          │ ──→│       ↓                  │    │ ├── ant/*.csv               │
│  + 表格裁剪              │    │  OCR → Layout → CSV      │    │ ├── boc/*.csv               │
│       ↓                  │    │       ↓                  │    │       ↓                      │
│  *_p*.png 图片           │    │  boc/*.csv (输出)       │ ──→│  CSV/XLSX → Transaction     │
└──────────────────────────┘    └──────────────────────────┘    │       ↓                      │
                                                                  │  聚合统计 → HTML 报表        │
                                                                  └──────────────────────────────┘

```

### 处理管线

| 步骤 | 函数 | 说明 |
|---|---|---|
| ① | `pdf_to_images()` | PDF 逐页渲染 → 亮度分析裁剪表格 → PNG 图片 |
| ② | `images_to_csv()` | 图片 → PaddleOCR → 布局结构化 → CSV 写入 |
| ③ | `scan_directory()` | 按子目录名（wechat/ant/boc）自动归类文件 |
| ④ | `parse_file()` | 根据平台调用对应解析器：CSV/XLSX → Transaction 列表 |
| ⑤ | `aggregate()` | 过滤内部转账 → 多维度聚合统计 |
| ⑥ | `generate_html()` | ECharts 5 交互式 HTML 报表输出 |




## 核心能力

### 多平台账单解析

| 平台 | 文件格式 | 自动检测 | 编码处理 |
|---|---|---|---|
| 微信支付 | `.xlsx` | 子目录 `wechat/` | openpyxl 直接读取 |
| 支付宝 | `.csv` | 子目录 `ant/` | GBK → UTF-8 自动探测 |
| 中国银行（BOC） | `.pdf` / `.csv` | 子目录 `boc/` | UTF-16 LE / UTF-8 BOM 自动探测 |

### 银行流水 OCR

- **PaddleOCR** 中文识别引擎 — 惰性加载、全局单例，避免重复初始化
- **亮度分析法** — 自动检测表格边界并精确裁剪，消除无关背景
- **逐页容错** — 任一页 OCR 失败即终止并报错，避免生成残缺数据
- **布局注册表** — 新增银行只需实现 `BankLayout` 接口 + 注册，不改现有代码

### 内部转账过滤

自动识别并剔除不影响总资产的内部资金流动，确保消费统计反映真实支出：

| 平台 | 判定规则 |
|---|---|
| 支付宝 | `tx_type == "不计收支"` |
| 微信 | category 含"充值"/"提现"/"零钱" |

报表中独立展示内部转账金额，消费统计仅基于真实外部交易。

### 分析维度

- **总支出 / 总收入 / 月均支出**
- **各平台消费统计与对比**
- **月度趋势** — 可切换平台查看
- **消费类别分布** — 饼图 + 条形图 + 排名列表

---

## 扩展：新增银行（以 ICBC 为例）

三步完成，**不修改现有代码**：

1. **`ocr/layouts/icbc.py`** — 实现 `IcbcLayout(BankLayout)`，定义列坐标、行分组、转 Transaction
2. **`ocr/layouts/__init__.py`** — 注册 `register_layout("icbc", IcbcLayout)`
3. **`ingest/parsers/icbc.py`** — 解析 ICBC 格式 CSV 为 Transaction

输入目录放入 `<input_dir>/icbc/*.pdf`，然后：

```bash
paycheck pdf2image <input_dir>            # 渲染 PDF → 图片
paycheck image2csv <input_dir>/icbc/      # OCR → CSV
paycheck analyse <input_dir>              # 分析 → 报表
# 或一步到位:
paycheck pdf2image <input_dir> && paycheck image2csv <input_dir>/icbc/ && paycheck analyse <input_dir>
```

---

## 故障排查

| 问题 | 排查方向 |
|---|---|
| `PaddleOCR` 初始化失败 | 检查 CUDA 版本是否匹配（本项目使用 CUDA 12.6）；GPU 显存不足时设置 `CUDA_VISIBLE_DEVICES=""` 回退 CPU |
| OCR 识别结果乱码 | 确认 PDF 为可渲染的扫描件（非图片嵌入型 PDF）；检查 `boc/` 目录下 PNG 图片是否裁剪正确 |
| CSV 编码错误 | 支付宝默认 GBK，银行默认 UTF-16 LE，工具会自动探测；如仍失败，手动转为 UTF-8 再试 |
| 微信 XLSX 解析失败 | 确认微信导出的为 `.xlsx` 格式（非 `.csv`）；检查文件是否被加密或损坏 |
| 报表显示空白 | ECharts 通过 CDN 加载，检查网络连接；或手动下载 ECharts 5 替换 CDN 引用 |

---

## 依赖

- Python 3.10–3.11
- PaddleOCR ≥ 3.6.0 + PaddlePaddle（中文 OCR 引擎）
- PyMuPDF（PDF 渲染）
- Pillow（图像处理）
- openpyxl（微信 XLSX 解析）
- opencv-python（图像处理）
- torch（PaddleOCR 底层）
- ECharts 5（报表图表，CDN 加载）

---

## 许可

[MIT](LICENSE) © PayCheck Contributors
