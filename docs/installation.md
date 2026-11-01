# 安装说明

## 环境要求

- Python 3.10 ~ 3.13（项目声明 `>=3.10, <3.14`）
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖；也可用 pip（见下文备选方案）
- GPU 加速需 NVIDIA GPU + CUDA 12.6（见下文）

## 使用 uv 安装（推荐）

```bash
# 默认安装 CPU 版：自动从 Paddle 官方源安装 paddlepaddle CPU 版，含工作台 paycheck 全部依赖
uv sync

# 安装 GPU 加速版（可选，CUDA 12.6）
uv sync --extra gpu
```

> CPU 版即可满足全部功能，仅推理速度较慢；GPU 版显著加速 OCR 推理。

### GPU 版补充：nvidia-*-cu12 运行库

GPU 版 paddlepaddle 不内置 CUDA 运行库，Windows 上还需额外安装 NVIDIA 的 pip 包提供
cudart / cublas / cudnn DLL（程序会自动把这些 DLL 加入搜索路径）：

```bash
uv pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
```

缺少这些 DLL 时，GPU 探测会报不可用并说明原因（不会静默降级，见 [pdf-options.md](pdf-options.md) 的 `--device` 说明）。

## pip 备选方案

```bash
# CPU 版（paddlepaddle 需自行指定 Paddle 官方源）
pip install -e .

# GPU 版
pip install -e ".[gpu]"
```

pip 安装后可直接运行 `boc-pdf2csv` / `paycheck` 命令（不带 `uv run` 前缀）；
uv 安装方式下则统一用 `uv run <命令>` 前缀。

## 依赖

| 依赖 | 用途 |
|------|------|
| PaddleOCR + paddlepaddle + torch | OCR 识别引擎（合计约 2GB） |
| PyMuPDF | PDF 渲染为高清图片 |
| opencv-python + Pillow + numpy | 图像处理 |
| tqdm | 进度条 |
| openpyxl | 微信账单 XLSX 解析（工作台） |

> GPU 版为可选依赖组 `gpu`（`paddlepaddle-gpu>=2.6.0`，CUDA 12.6 官方源）。

## 验证安装

```bash
uv run boc-pdf2csv --version   # 应打印 boc-pdf2csv 1.1.0
uv run paycheck --version      # 应打印 paycheck 1.1.0
```
