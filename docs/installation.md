# 安装说明

## 环境要求

- Python 3.10 ~ 3.13（项目声明 `>=3.10, <3.14`）
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖；也可用 pip（见下文备选方案）

## 安装方式（默认 / 含 PDF）

PDF / OCR 相关依赖只被 PDF → CSV 链路使用，已拆为可选 extras（`pdf`）：

| 安装命令 | 安装内容 | 适用场景 |
|----------|----------|----------|
| `uv sync` | 工作台 + 微信 XLSX 解析等轻量依赖 | 只用账单工作台、CSV / Excel 导入 |
| `uv sync --extra pdf` | 追加 PaddleOCR、paddlepaddle-gpu、nvidia-*-cu12、PyMuPDF、opencv-python、Pillow、numpy、tqdm、torch | 需要 `boc-pdf2csv` 或工作台「转换 PDF」 |

```bash
uv sync                 # 默认安装（不下载 PDF / OCR 依赖）
uv sync --extra pdf     # 需要 PDF 转换时追加安装
```

未安装 extras 时，工作台启动、支付宝 / 微信 / BOC CSV 与 Excel 导入、总账户与标签
照常可用；触发 PDF 功能时才提示安装命令（CLI 退出码 5，工作台转换弹窗给出安装提示），
不会启动即崩或裸抛 ImportError。

### PDF 转换的 GPU 要求

- **需 NVIDIA GPU + CUDA 12.6 驱动**：PDF 转换强制使用 GPU，无 GPU 的机器无法执行转换（见 [pdf-options.md](pdf-options.md)）。
- 安装 `pdf` extras 即自动安装 GPU 版 paddlepaddle（Paddle CUDA 12.6 官方源）。

### nvidia-*-cu12 运行库（随 pdf extras 安装）

nvidia-cuda-runtime-cu12 / nvidia-cublas-cu12 / nvidia-cudnn-cu12 三个包随 `pdf` extras
自动安装，提供 cudart / cublas / cudnn DLL，程序会自动把它们加入 DLL 搜索路径，
无需手动 `uv pip install`。

## pip 备选方案

```bash
pip install -e .            # 仅工作台
pip install -e ".[pdf]"     # 含 PDF / OCR 依赖
```

> paddlepaddle-gpu 需自行指定 Paddle CUDA 12.6 官方源（`https://www.paddlepaddle.org.cn/packages/stable/cu126/`）。

pip 安装后可直接运行 `paycheck` / `boc-pdf2csv` 命令（不带 `uv run` 前缀）；
uv 安装方式下则统一用 `uv run <命令>` 前缀。

## 依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| openpyxl | 微信账单 XLSX 解析（工作台） | 默认 |
| PaddleOCR + paddlepaddle-gpu + torch | OCR 识别引擎（合计约 2GB） | `pdf` extras |
| nvidia-cuda-runtime-cu12 / nvidia-cublas-cu12 / nvidia-cudnn-cu12 | CUDA 12.6 运行库（cudart / cublas / cudnn DLL） | `pdf` extras |
| PyMuPDF | PDF 渲染为高清图片 | `pdf` extras |
| opencv-python + Pillow + numpy | 图像处理 | `pdf` extras |
| tqdm | 进度条 | `pdf` extras |

## 验证安装

```bash
uv run paycheck --version      # 应打印 paycheck 1.1.0
uv run boc-pdf2csv --version   # 需已安装 pdf extras，应打印 boc-pdf2csv 1.1.0
```

## 运行测试

```bash
uv sync --extra pdf   # 完整测试需要 PDF extras；未安装时 PDF 相关用例自动跳过
uv run pytest
```
