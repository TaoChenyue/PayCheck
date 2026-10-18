<p align="center">
  <h1 align="center">📄 boc-pdf2csv</h1>
  <p align="center"><strong>中国银行 PDF 对账单 → CSV 转换工具</strong></p>
  <p align="center">纯 Python 命令行工具：PDF 渲染 → OCR 识别 → 结构化 CSV，无需任何 Web 框架</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.0.0-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/GPU-CUDA%2012.6-orange?logo=nvidia" alt="CUDA">
</p>

---

## 简介

**boc-pdf2csv** 是一个独立的 Python 包，将中国银行（BOC）PDF 对账单批量转换为标准 CSV 文件。

处理管线：

```
PDF → 高清图片 (PyMuPDF) → OCR 识别 (PaddleOCR) → 版面解析 → 交易去重排序 → CSV
```

- 文件夹内每个 PDF 输出同名 CSV，同名 CSV 已存在则自动跳过
- 自动剔除重复交易（按 日期 + 金额 + 对方账户名）
- 自动按日期 + 时间排序
- 输出 UTF-8 BOM 编码的 13 列标准 CSV
- 默认强制使用 GPU（CUDA）推理，无 GPU 时可显式 `--device cpu`
- 无任何前后端框架依赖，纯命令行使用

## 安装

```bash
# 使用 uv（推荐，自动从 Paddle 官方源安装 CPU 版）
uv sync

# 安装 GPU 加速版（可选，CUDA 12.6）
uv sync --extra gpu
```

> 也可用 pip 安装：`pip install -e .`（CPU 版需自行指定 paddlepaddle 源）。

GPU 版 paddle 不内置 CUDA 运行库，Windows 上还需安装 NVIDIA 的 pip 包提供
cudart / cublas / cudnn DLL（程序会自动把它们加入 DLL 搜索路径）：

```bash
uv pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## 使用

```bash
# 基本用法：文件夹内每个 PDF → 同名 CSV（已存在则跳过）
boc-pdf2csv ./statements/

# 调整渲染精度（低配机器可用 2.0）
boc-pdf2csv ./statements/ --scale 2.0

# 延长超时（大批量文件）
boc-pdf2csv ./statements/ --timeout 120

# 无 GPU 机器使用 CPU 推理（默认强制 GPU）
boc-pdf2csv ./statements/ --device cpu

# 查看版本 / 帮助
boc-pdf2csv --version
boc-pdf2csv --help

# 详细日志
boc-pdf2csv ./statements/ --verbose

# 通过 Python 模块调用
python -m boc_pdf2csv ./statements/
```

`2025-01.pdf` 转换后得到同目录下的 `2025-01.csv`；若该 CSV 已存在则跳过此 PDF，删除对应 CSV 后可重新转换。

默认强制使用 GPU 推理；未检测到 GPU 时直接报错（不会静默回退 CPU），无 GPU 的机器需显式加 `--device cpu`。

### 作为 Python API 使用

```python
from boc_pdf2csv import process_folder, process_pdf

# 批量处理文件夹：每个 PDF → 同名 CSV（已存在则跳过），返回汇总
result = process_folder("./statements/")
result.processed  # {PDF 路径: CSV 路径}
result.skipped    # 跳过的 PDF（同名 CSV 已存在）
result.failed     # 处理失败的 PDF

# 处理单个 PDF
csv_content = process_pdf("./statements/2025-01.pdf", output_path="2025-01.csv")

# 推理设备默认强制 GPU（device='gpu'），无 GPU 时显式指定 CPU
csv_content = process_pdf("./statements/2025-01.pdf", device="cpu")
```

## CSV 输出格式

输出为 UTF-8 BOM 编码的 13 列标准 CSV：

| 列名 | 说明 |
|------|------|
| date | 记账日期 |
| time | 记账时间 |
| tx_type | 交易类型（支出/收入） |
| amount | 金额（正数） |
| counterparty | 对方账户名 |
| channel | 交易渠道 |
| balance | 余额 |
| memo | 附言 |
| tx_name | 交易名称 |
| currency | 币别 |
| branch | 网点名称 |
| cp_account | 对方卡号/账号 |
| cp_bank | 对方开户行 |

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 输入路径不存在或非目录 |
| 2 | 未找到 PDF 文件 |
| 3 | 处理失败（全部 PDF 处理出错） |
| 4 | 未提取到任何交易记录 |

## 项目结构

```
src/boc_pdf2csv/
├── cli.py        # 命令行入口 (argparse)
├── pdf_render.py # PDF → 高清图片
├── ocr_engine.py # PaddleOCR 识别引擎
├── layout.py     # OCR 版面解析 → 交易行
├── pipeline.py   # 管线编排：单 PDF / 批量文件夹
├── csv_writer.py # 交易 → 13 列 CSV
├── __main__.py   # python -m 入口
└── __init__.py   # 公开 API
```

## 依赖

| 依赖 | 用途 |
|------|------|
| PaddleOCR + paddlepaddle + torch | OCR 识别引擎（合计约 2GB） |
| PyMuPDF | PDF 渲染为高清图片 |
| opencv-python + Pillow + numpy | 图像处理 |
| tqdm | 进度条 |

## 许可证

[MIT](LICENSE)
