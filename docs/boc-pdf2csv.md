# boc-pdf2csv 使用说明

中国银行（BOC）PDF 对账单 → 标准 CSV 的命令行转换工具。
处理管线：`PDF → 高清图片 (PyMuPDF) → OCR 识别 (PaddleOCR) → 版面解析 → 交易去重排序 → CSV`。

## 基本用法

```bash
# 基本用法：文件夹内每个 PDF → 同名 CSV（已存在则跳过）
uv run boc-pdf2csv ./statements/

# 强制重新导出：同名 CSV 已存在时覆盖而不是跳过
uv run boc-pdf2csv ./statements/ --force

# 调整渲染精度（低配机器可用 2.0）
uv run boc-pdf2csv ./statements/ --scale 2.0

# 延长超时（大批量文件）
uv run boc-pdf2csv ./statements/ --timeout 120

# 查看版本 / 帮助
uv run boc-pdf2csv --version
uv run boc-pdf2csv --help

# 详细日志
uv run boc-pdf2csv ./statements/ --verbose

# 通过 Python 模块调用
uv run python -m boc_pdf2csv ./statements/
```

> 以上示例基于推荐的 uv 安装方式；`pip install -e .` 安装后可直接运行 `boc-pdf2csv`（不带 `uv run` 前缀）。

行为约定：

- 文件夹内**每个 PDF 输出同名 CSV**（`2025-01.pdf` → 同目录 `2025-01.csv`）
- 同名 CSV 已存在时默认**跳过**该 PDF；删除对应 CSV 或加 `--force` 可重新转换（`--force` 会覆盖已有 CSV）
- 自动剔除重复交易（按 日期 + 金额 + 对方账户名），自动按日期 + 时间排序
- 输出 UTF-8 BOM 编码的 13 列标准 CSV
- 强制使用 GPU 推理；未检测到 GPU 时直接报错退出（退出码 3，不会静默回退）
- 每次运行会在输入目录写入运行日志 `boc-pdf2csv.log`（见 [logging.md](logging.md)）

各选项的详细语义（`--scale` / `--timeout` / `--force` / `--verbose`）见 [pdf-options.md](pdf-options.md)。

## 作为 Python API 使用

```python
from boc_pdf2csv import process_folder, process_pdf

# 批量处理文件夹：每个 PDF → 同名 CSV（已存在则跳过），返回汇总
result = process_folder("./statements/")
result.processed  # {PDF 路径: CSV 路径}
result.skipped    # 跳过的 PDF（同名 CSV 已存在）
result.failed     # 处理失败的 PDF
result.total_transactions  # 提取到的交易总数（去重后）

# 处理单个 PDF
csv_content = process_pdf("./statements/2025-01.pdf", output_path="2025-01.csv")

# 文件夹批量处理默认跳过已有同名 CSV，force=True 时覆盖重新导出；
# 推理强制使用 GPU，无 GPU 时抛 RuntimeError
result = process_folder("./statements/", force=True)
```

> API 参数与命令行一致：`process_folder(folder_path, scale=3.0, timeout_minutes=60, verbose=False, force=False)`。

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
| 3 | 处理失败（全部 PDF 处理出错，如无可用 GPU） |
| 4 | 未提取到任何交易记录 |
