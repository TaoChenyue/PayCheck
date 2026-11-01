# 文档索引

| 文档 | 内容 |
|------|------|
| [installation.md](installation.md) | 安装说明（CPU / GPU、pip 备选、依赖表） |
| [boc-pdf2csv.md](boc-pdf2csv.md) | boc-pdf2csv 使用说明（命令、Python API、CSV 格式、退出码） |
| [pdf-options.md](pdf-options.md) | PDF 转换各选项说明（scale / timeout / device / force / verbose） |
| [workbench.md](workbench.md) | 账单工作台操作说明 |
| [logging.md](logging.md) | 日志说明（工作台 paycheck.log、CLI 文件日志、隐私红线） |

## 两个工具与工作流总览

PayCheck 包含两个工具：

- **boc-pdf2csv**：中国银行（BOC）PDF 对账单 → 标准 CSV 的命令行转换工具。处理管线：`PDF → 高清图片 (PyMuPDF) → OCR 识别 (PaddleOCR) → 版面解析 → 交易去重排序 → CSV`。
- **paycheck**：本地账单工作台（Python 标准库 HTTP 服务，无 Web 框架）。BOC / 支付宝 / 微信三源原始账单导入 SQLite 后 HTML 展示，收支属性与标签统一在「总账户」视图管理。

整体工作流：**原始账单导入（数据源视图，只读）→ 总账户做收支与标签管理（三源合并视图）**。

两者关系：boc-pdf2csv 产出的 BOC CSV 可直接作为工作台的 BOC 数据源导入；工作台内置「转换 PDF」入口，在浏览器里完成同样的 PDF 转换（见 [workbench.md](workbench.md)），转换出的 CSV 与 PDF 同名存入转换目录，不导入也可直接取用。

## 项目结构

```
src/
├── boc_pdf2csv/           # PDF → CSV 转换工具
│   ├── cli.py             # 命令行入口 (argparse) 与文件日志配置
│   ├── pdf_render.py      # PDF → 高清图片
│   ├── ocr_engine.py      # PaddleOCR 识别引擎
│   ├── layout.py          # OCR 版面解析 → 交易行
│   ├── pipeline.py        # 管线编排：单 PDF / 批量文件夹
│   ├── csv_writer.py      # 交易 → 13 列 CSV
│   ├── __main__.py        # python -m 入口
│   └── __init__.py        # 公开 API
└── paycheck_workbench/    # 账单工作台
    ├── cli.py             # 命令行入口 (argparse)
    ├── db.py              # SQLite 存储层：明细表 / 导入 / 筛选 / 覆盖 / 标签
    ├── server.py          # 标准库 HTTP 服务 + JSON API
    ├── sources.py         # 三源列定义、逻辑列与去重键
    ├── total.py           # 总账户统一映射 / 有效属性 / 标签 / 分页
    ├── convert.py         # BOC PDF 转换后台任务
    ├── applog.py          # 工作台文件日志（paycheck.log）
    ├── parsing/           # BOC / 支付宝 / 微信解析器（表头定位）
    ├── static/            # 单页前端 index.html
    ├── __main__.py        # python -m 入口
    └── __init__.py
tests/                     # pytest：解析层 / 存储层 / HTTP 服务 / 总账户 / 标签 / CLI 日志
```

## 开发与测试

```bash
uv sync          # 安装全部依赖
uv run pytest    # 运行全部测试
```

测试约定：

- **合成样本恒跑**：解析层、存储层、HTTP 服务等测试全部使用合成样本，无需外部数据，默认全量运行。
- **真实样本按需跑**：部分冒烟/回归用例需要真实账单样本，通过环境变量 `PAYCHECK_SAMPLE_DIR` 指定样本目录（约定该目录下有 `BOC/` 等子目录存放对应类型的样本文件）。未设置该环境变量时相关用例自动跳过，不影响常规回归。
- 测试代码不属于产品代码；产品代码改动需同步补测试（如新增 CLI 文件日志时的 `tests/test_cli_logging.py`）。
