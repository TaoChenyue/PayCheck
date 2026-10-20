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

# 强制重新导出：同名 CSV 已存在时覆盖而不是跳过
boc-pdf2csv ./statements/ --force

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

`2025-01.pdf` 转换后得到同目录下的 `2025-01.csv`；若该 CSV 已存在则默认跳过此 PDF，删除对应 CSV 或加 `--force` 可重新转换（`--force` 会覆盖已有 CSV）。

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

# 文件夹批量处理默认跳过已有同名 CSV，force=True 时覆盖重新导出
result = process_folder("./statements/", force=True)
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


---

## 账单工作台（paycheck-workbench）

本地 Web 工具：BOC / 支付宝 / 微信三源账单的 HTML 展示 + SQLite 导入（Python 标准库 HTTP 服务，无 Web 框架）。

```bash
# 启动（默认库文件 paycheck.db，相对启动目录；端口 8765）
paycheck-workbench
# 自定义库文件与端口，并自动打开浏览器
paycheck-workbench --db ./my.db --port 8765 --open
# 或通过模块运行
python -m paycheck_workbench
```

功能：

- 三数据源 Tab 切换（BOC CSV / 支付宝 GBK CSV / 微信 XLSX，兼容 CSV 变体），自动跳过文件信息头定位表头
- 解析预览（列样例、日期范围、收/支分布）+ 去重比对（新增/重复跳过）→ 确认后写入 SQLite，重复导入幂等
- 导入入口支持一次选择多个文件（多选/拖拽，按当前 Tab 限定类型）：逐文件统计 + 合并去重比对，确认后逐文件写入并显示进度与结果，类型不符的文件明确提示且不写入
- 明细表格：排序、分页、行展开详情、列显隐；汇总卡片随筛选联动（收入/支出/不计收支/期末余额或笔数）
- 左侧筛选栏：日期快捷档位、收/支多选、分类多选、金额区间、关键词搜索（300ms 防抖）
- 三张表 `boc_transactions` / `alipay_transactions` / `wechat_transactions`：源明细列全量入库 + `source_file` / `imported_at` / `dedup_key`（UNIQUE）

## 开发

```bash
uv sync          # 安装全部依赖
uv run pytest    # 运行测试（解析层/存储层/HTTP 服务）
```
