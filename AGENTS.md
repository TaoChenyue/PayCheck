# PayCheck 开发指南

## 快速命令

```bash
uv run --directory paycheck-tools paycheck pdf2image <input_dir>   # ① PDF → 裁剪后 PNG
uv run --directory paycheck-tools paycheck image2csv <bank_dir>    # ② OCR → CSV
uv run --directory paycheck-tools paycheck analyse <input_dir>     # ③ 分析 → JSON 报表
```

## 项目结构

`paycheck-tools/paycheck/` — CLI 工具，package name 为 `paycheck`。

`paycheck-react/` — React 前端报表可视化（Vite + React + TypeScript + ECharts）。

模块层级（从 __main__.py 的 handlers 可以看出完整调用链）：

```
__main__.py                    ← CLI: pdf2image / image2csv / analyse
  core/log.py                  ← logging 配置（RotatingFileHandler, 10MB×5）
  core/models.py               ← Transaction dataclass（唯一数据模型）
  ingest/scanner.py            ← 按子目录名自动归类文件
  ingest/csv_utils.py          ← CSV 引号字段解析
  ingest/parsers/__init__.py   ← 解析器派发（基于路径中的目录名）
  ingest/parsers/wechat.py     ← .xlsx → Transaction
  ingest/parsers/alipay.py     ← .csv → Transaction（GBK 自动探测）
  ingest/parsers/boc.py        ← .csv → Transaction（UTF-16 LE/UTF-8 BOM）
  ocr/engine.py                ← PaddleOCR 单例封装（惰性加载）
  ocr/pdf_render.py            ← PDF 多进程渲染 + 表格裁剪
  ocr/pipeline.py              ← 图片→CSV 串联（OCR 是串行的）
  ocr/layouts/base.py          ← BankLayout 抽象基类 + 行分组
  ocr/layouts/boc.py           ← 中国银行（BOC）布局实现
  ocr/layouts/__init__.py      ← 布局注册表（register_layout / get_layout）
  analysis/filters.py          ← 内部转账检测
  analysis/stats.py            ← 多维度聚合统计
  report/html_reporter.py      ← ECharts HTML 报表生成
```

## 输入目录约定

```
<input_dir>/
├── wechat/          ← .xlsx
├── ant/             ← .csv（支付宝）
└── boc/             ← .pdf 或 .csv（中国银行）
```

银行子目录名 = layout 名称 = `ocr/layouts/__init__.py` 中注册的 key。
`scan_directory()` 按子目录名分发，`parse_file()` 按路径中的目录名选择解析器。

## 关键约束

- **Python 3.10–3.11 限定** — PaddlePaddle 兼容性要求
- **无测试基础设施** — 没有 pytest、没有测试文件、没有 CI。不要寻找或假设测试存在
- **无 lint/typecheck** — 没有 ruff、mypy、pyright 配置。不要求类型严格
- **OCR 是串行的** — `images_to_csv()` 逐页 for 循环调用 `_image_worker()`，没有多进程。`_image_worker` 名字中的 "worker" 是误导
- **PDF 渲染是多进程的** — `pdf_to_images()` 使用 `ProcessPoolExecutor`。仅在 `pdf_render.py` 中
- **日志自动写入 `log/paycheck.log`**（10MB 轮转 × 5 份），控制台输出需 `--verbose`
- **所有子包 `__init__.py` 均为空** — 只有 `ocr/layouts/__init__.py`（布局注册表）和 `ingest/parsers/__init__.py`（派发函数）有实际代码

## GPU 与 OCR 坑

- GPU 需要 CUDA 12.6（查看 pyproject.toml 中的自定义索引 URL）
- 无 GPU 时设环境变量 `CUDA_VISIBLE_DEVICES=""` 回退 CPU
- `setup_logging()` 会自动压制 paddle/ppocr/PIL/matplotlib/fitz 等第三方库的日志到 WARNING

## 扩展：新增银行

1. `ocr/layouts/{name}.py` — 实现 `BankLayout`（定义列坐标、行分组、转 dict）
2. `ocr/layouts/__init__.py` — `register_layout("{name}", {Name}Layout)`
3. `ingest/parsers/{name}.py` — 解析 CSV 为 `Transaction`（可选，处理已有 CSV 时）
4. 输入放入 `<input_dir>/{name}/*.pdf`

不需要修改现有代码。

## 内部转账规则（analysis/filters.py）

| 平台 | 规则 |
|---|---|
| alipay | `tx_type == "不计收支"` |
| wechat | category 含 "充值" / "提现" / "零钱" |

## 文件编码

| 平台 | 编码 |
|---|---|
| 微信 .xlsx | openpyxl 直接读取 |
| 支付宝 .csv | GBK → UTF-8 自动探测 |
| 银行 .csv | UTF-16 LE / UTF-8 BOM / UTF-8 自动探测 |
| OCR 产出 .csv | UTF-8 |

## 与 README 的差异

- 如果 README 提到 `pdf2csv` 快捷命令或"多进程 OCR"——那是错的，以本文件和代码为准
