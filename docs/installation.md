# 安装说明

## 环境要求

- Python 3.10 ~ 3.13（项目声明 `>=3.10, <3.14`）
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖；也可用 pip（见下文备选方案）
- **需 NVIDIA GPU + CUDA 12.6 驱动**：PDF 转换强制使用 GPU，无 GPU 的机器无法执行转换（见 [pdf-options.md](pdf-options.md)）

## 使用 uv 安装（推荐）

```bash
# 自动安装 GPU 版 paddlepaddle（CUDA 12.6 官方源）与 NVIDIA CUDA 运行库
uv sync
```

### nvidia-*-cu12 运行库（已内置）

nvidia-cuda-runtime-cu12 / nvidia-cublas-cu12 / nvidia-cudnn-cu12 三个包随依赖
自动安装，提供 cudart / cublas / cudnn DLL，程序会自动把它们加入 DLL 搜索路径，
无需手动 `uv pip install`。

## pip 备选方案

```bash
pip install -e .
```

> paddlepaddle-gpu 需自行指定 Paddle CUDA 12.6 官方源（`https://www.paddlepaddle.org.cn/packages/stable/cu126/`）。

pip 安装后可直接运行 `boc-pdf2csv` / `paycheck` 命令（不带 `uv run` 前缀）；
uv 安装方式下则统一用 `uv run <命令>` 前缀。

## 依赖

| 依赖 | 用途 |
|------|------|
| PaddleOCR + paddlepaddle-gpu + torch | OCR 识别引擎（合计约 2GB） |
| nvidia-cuda-runtime-cu12 / nvidia-cublas-cu12 / nvidia-cudnn-cu12 | CUDA 12.6 运行库（cudart / cublas / cudnn DLL） |
| PyMuPDF | PDF 渲染为高清图片 |
| opencv-python + Pillow + numpy | 图像处理 |
| tqdm | 进度条 |
| openpyxl | 微信账单 XLSX 解析（工作台） |

## 验证安装

```bash
uv run boc-pdf2csv --version   # 应打印 boc-pdf2csv 1.1.0
uv run paycheck --version      # 应打印 paycheck 1.1.0
```
