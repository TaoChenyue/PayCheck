# boc-pdf2csv

中国银行 PDF 对账单 → CSV 转换工具。

## 安装

```bash
# 使用 uv（推荐）
uv sync

# 安装 GPU 加速（可选）
uv sync --extra gpu
```

## 使用

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

# 通过 Python 模块调用
python -m boc_pdf2csv ./statements/ -o out.csv
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
| 3 | 处理失败（部分或全部 PDF） |
| 4 | 未提取到任何交易记录 |

## 依赖

- PaddleOCR + paddlepaddle + torch（合计 ~2GB，OCR 引擎）
- PyMuPDF（PDF 渲染）
- opencv-python + Pillow + numpy（图像处理）
- tqdm（进度条）

## 许可证

MIT
