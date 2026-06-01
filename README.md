# PayCheck — 个人账单统计工具

聚合微信、支付宝、银行三渠道账单，自动剔除内部转账，生成 ECharts 交互式 HTML 分析报告。

## 快速开始

```bash
# ---------- 三阶段工作流（推荐，可任意重跑某一步） ----------
uv run paycheck pdf2image <input_dir>          # ① PDF → 页面图片
uv run paycheck image2csv <input_dir>/boc/     # ② 图片 → CSV
uv run paycheck analyse <input_dir>            # ③ 分析 → 报表

# 快捷方式（合并前两步）
uv run paycheck pdf2csv <input_dir>            # ①+② PDF → CSV
uv run paycheck analyse <input_dir> -o report.html
```

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

快捷: pdf2csv  =  pdf2image + image2csv（图片用临时目录，自动清理）

处理管线:
  ① pdf_to_images()      → PDF → 裁剪后 PNG 图片（per-page）
  ② images_to_csv()      → 图片 → OCR → layout 结构化 → CSV
  ③ scan_directory()     → 自动识别子目录，归类文件
  ④ parse_file()         → CSV/XLSX → Transaction 列表
  ⑤ aggregate()          → 过滤内部转账 → 多维度聚合统计
  ⑥ generate_html()      → ECharts HTML 报表输出
```

## 架构（5 层模块）

```
__main__.py              ← CLI 入口（subparsers: pdf2image | image2csv | pdf2csv | analyse）
├── core/log.py          ← 日志系统（文件 + 控制台）
├── core/models.py       ← Transaction 统一数据模型
├── ingest/scanner.py    ← 扫描目录，按子目录名匹配平台
├── ingest/csv_utils.py  ← CSV 行解析工具（引号字段处理）
├── ingest/parsers/      ← 各平台解析器
│   ├── wechat.py        ← 微信 .xlsx → Transaction
│   ├── alipay.py        ← 支付宝 .csv → Transaction
│   └── boc.py           ← BOC 银行 .csv → Transaction
├── ocr/engine.py        ← PaddleOCR 引擎封装
├── ocr/pdf_render.py    ← PDF → 图片 + 表格检测裁剪（含 pdf_to_images 多进程渲染）
├── ocr/pipeline.py      ← 图片 → CSV 管线编排（images_to_csv + pdf_to_csv 组合）
├── ocr/layouts/         ← 银行流水布局体系
│   ├── base.py          ← BankLayout 抽象基类 + 表格检测 + 行分组
│   ├── boc.py           ← 中国银行布局实现
│   └── __init__.py      ← 布局注册表
├── analysis/filters.py  ← 内部转账检测规则（支付宝/微信）
├── analysis/stats.py    ← 聚合统计（月度/平台/类别维度）
└── report/html_reporter.py  ← HTML + ECharts 报表生成
```

## 核心能力

### 多平台账单解析

| 平台 | 文件格式 | 自动检测 | 编码处理 |
|---|---|---|---|
| 微信支付 | `.xlsx` | 子目录 `wechat/` | openpyxl 直接读取 |
| 支付宝 | `.csv` | 子目录 `ant/` | GBK → UTF-8 自动探测 |
| 银行（BOC） | `.pdf` / `.csv` | 子目录 `boc/` | UTF-16 LE / UTF-8 BOM 自动探测 |

### 银行流水 OCR

- **PaddleOCR** 中文识别引擎（惰性加载、全局单例）
- **亮度分析法** 自动检测表格边界并裁剪
- **多进程并行** 逐页 OCR，任意页失败即取消剩余任务（容错）
- **布局注册表** 新增银行只需实现 `BankLayout` 接口 + 注册，不改现有代码

### 内部转账过滤

自动识别并剔除不影响总资产的内部资金流动：

| 平台 | 判定规则 |
|---|---|
| 支付宝 | `tx_type == "不计收支"` |
| 微信 | category 含"充值"/"提现"/"零钱" |

报表中独立展示内部转账金额，消费统计仅基于真实外部交易。

### 分析维度

- 总支出 / 总收入 / 月均支出
- 各平台消费统计与对比
- 月度趋势（可切换平台查看）
- 消费类别分布（饼图 + 条形图 + 排名列表）

## 扩展：新增银行（以 ICBC 为例）

三步完成，不修改现有代码：

1. `ocr/layouts/icbc.py` — 实现 `IcbcLayout(BankLayout)`（定义列坐标、行分组、转 Transaction）
2. `ocr/layouts/__init__.py` — 注册 `register_layout("icbc", IcbcLayout)`
3. `ingest/parsers/icbc.py` — 解析 ICBC 格式 CSV 为 Transaction

输入目录放入 `<input_dir>/icbc/*.pdf`，然后：
```bash
paycheck pdf2image <input_dir>            # 渲染 PDF → 图片
paycheck image2csv <input_dir>/icbc/      # OCR → CSV
paycheck analyse <input_dir>              # 分析 → 报表
# 或一步到位:
paycheck pdf2csv <input_dir> && paycheck analyse <input_dir>
```

## 依赖

- Python 3.10–3.13
- PaddleOCR + PaddlePaddle（中文 OCR）
- PyMuPDF（PDF 渲染）
- Pillow（图像处理）
- openpyxl（微信 XLSX 解析）
- ECharts 5（报表图表，CDN 加载）
