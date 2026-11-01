<p align="center">
  <h1 align="center">📄 PayCheck</h1>
  <p align="center"><strong>中国银行 PDF 对账单 → CSV 转换工具 + 本地账单工作台</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.1.0-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/GPU-CUDA%2012.6-orange?logo=nvidia" alt="CUDA">
</p>

## 简介

本项目包含两个工具：

- **boc-pdf2csv**：中国银行（BOC）PDF 对账单 → 标准 CSV 的命令行转换工具。
- **paycheck**：本地账单工作台（Python 标准库 HTTP 服务，无 Web 框架）：BOC / 支付宝 / 微信三源原始账单导入 SQLite 后 HTML 展示，收支属性与标签统一在「总账户」视图管理。

整体工作流：**原始账单导入（数据源视图，只读）→ 总账户做收支与标签管理（三源合并视图）**。

boc-pdf2csv 处理管线：

```
PDF → 高清图片 (PyMuPDF) → OCR 识别 (PaddleOCR) → 版面解析 → 交易去重排序 → CSV
```

- 文件夹内每个 PDF 输出同名 CSV，同名 CSV 已存在则自动跳过
- 自动剔除重复交易（按 日期 + 金额 + 对方账户名），自动按日期 + 时间排序
- 输出 UTF-8 BOM 编码的 13 列标准 CSV
- 默认强制使用 GPU（CUDA）推理，无 GPU 时可显式 `--device cpu`

## 快速开始

```bash
uv sync                          # 安装全部依赖（含工作台 paycheck）

uv run boc-pdf2csv ./statements/ # BOC PDF 文件夹 → 同名 CSV
uv run paycheck --open           # 启动账单工作台并打开浏览器
```

## 文档

详细使用说明见 docs 目录：

| 文档 | 内容 |
|------|------|
| [docs/index.md](docs/index.md) | 文档索引：两工具关系、项目结构、开发与测试 |
| [docs/installation.md](docs/installation.md) | 安装说明（CPU / GPU、pip 备选、依赖表） |
| [docs/boc-pdf2csv.md](docs/boc-pdf2csv.md) | boc-pdf2csv 使用说明（命令、Python API、CSV 格式、退出码） |
| [docs/pdf-options.md](docs/pdf-options.md) | PDF 转换各选项说明（scale / timeout / device / force / verbose） |
| [docs/workbench.md](docs/workbench.md) | 账单工作台操作说明 |
| [docs/logging.md](docs/logging.md) | 日志说明（工作台 paycheck.log、CLI 文件日志、隐私红线） |

## 许可证

[MIT](LICENSE)
