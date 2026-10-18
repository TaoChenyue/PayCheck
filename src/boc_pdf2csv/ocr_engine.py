"""PaddleOCR 引擎封装 — 银行无关，只做文字检测与识别

输入: 图片 (numpy BGR 或文件路径)
输出: list[OCRItem] — 识别到的文字块及其坐标

默认强制使用 GPU（device='gpu'）：未检测到 GPU 时抛错，不静默回退 CPU。
"""

import logging
import os
import time
import warnings
from typing import Any, Dict, List, Union

import cv2
import numpy as np

from boc_pdf2csv.layout import OCRItem

# 在子进程中提前压制 requests 的版本警告（paddleocr 会触发）
warnings.filterwarnings("ignore", message=".*urllib3.*or.*chardet.*doesn't match")

log = logging.getLogger("boc_pdf2csv.ocr")

# device → PaddleOCR 引擎实例（惰性初始化，按设备缓存）
_ocrs: Dict[str, Any] = {}


def _add_nvidia_dll_dirs() -> None:
    """将 pip 安装的 NVIDIA CUDA 运行库加入 DLL 搜索路径（仅 Windows）

    GPU 版 paddle 依赖 cudart / cublas / cudnn 等 DLL。通过 pip 安装的
    nvidia-*-cu12 包把 DLL 放在 site-packages/nvidia/*/bin 下，不在系统
    PATH 中，paddle 的运行时加载器找不到，需手动加入搜索路径。
    """
    if os.name != "nt":
        return

    import paddle

    site_packages = os.path.dirname(os.path.dirname(os.path.abspath(paddle.__file__)))
    nvidia_root = os.path.join(site_packages, "nvidia")
    if not os.path.isdir(nvidia_root):
        return

    for name in os.listdir(nvidia_root):
        bin_dir = os.path.join(nvidia_root, name, "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            log.debug("已加入 DLL 搜索路径: %s", bin_dir)


def _get_engine(device: str = "gpu"):
    """获取 PaddleOCR 引擎（惰性初始化，按 device 缓存单例）

    Args:
        device: 推理设备，"gpu"（默认，强制 GPU）或 "cpu"

    Raises:
        RuntimeError: device='gpu' 但未检测到可用 GPU
    """
    global _ocrs
    if device not in _ocrs:
        # torch 必须先于 paddle 导入：Windows 上 paddle 的 DLL 搜索路径会干扰
        # torch 加载自身的 shm.dll（WinError 127）
        import torch  # noqa: F401
        import paddle
        from paddleocr import PaddleOCR

        if device == "gpu":
            if not paddle.device.is_compiled_with_cuda() or paddle.device.cuda.device_count() == 0:
                raise RuntimeError(
                    "强制使用 GPU，但未检测到可用 GPU：请确认安装的是 GPU 版 paddlepaddle "
                    "且机器上有可用的 NVIDIA GPU（如确需 CPU 推理，请显式指定 device='cpu'）"
                )
            _add_nvidia_dll_dirs()

        log.info("加载 PaddleOCR 模型 (device=%s)...", device)

        try:
            _ocrs[device] = PaddleOCR(
                lang='ch',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device=device,
            )
        except (TypeError, ValueError):
            _ocrs[device] = PaddleOCR(lang='ch', device=device)
    return _ocrs[device]


def warmup_engine(device: str = "gpu"):
    """预加载 OCR 模型，避免在进度条出现后才开始加载"""
    _get_engine(device)


def process_image(
    image_input: Union[str, np.ndarray],
    timeout_sec: float = 600,
    device: str = "gpu",
) -> List[OCRItem]:
    """识别图片中的文字

    Args:
        image_input: 图片路径 (str) 或 BGR numpy 数组
        timeout_sec: 超时秒数
        device: 推理设备，"gpu"（默认）或 "cpu"
    Returns:
        OCRItem 列表
    """
    engine = _get_engine(device)
    start_time = time.time()

    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            log.warning("无法读取图像: %s", image_input)
            return []
    else:
        img = image_input

    h, w = img.shape[:2]
    log.info("OCR识别图片: %dx%d", h, w)

    remaining = timeout_sec - (time.time() - start_time)
    if remaining <= 0:
        raise TimeoutError("图片加载已超时")

    result = engine.predict(img)

    items = []
    if result and len(result) > 0:
        r = result[0]
        dt_polys = r.get('dt_polys') or []
        rec_texts = r.get('rec_texts') or []
        rec_scores = r.get('rec_scores') or []

        for i, poly in enumerate(dt_polys):
            if i >= len(rec_texts):
                break
            text = rec_texts[i]
            score = rec_scores[i] if i < len(rec_scores) else 0.0
            if score < 0.3:
                continue
            # poly 格式: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            items.append(OCRItem(text=text, cx=cx, cy=cy))

    log.debug("OCR结果: %d 个文字块 (过滤前 %d)", len(items), len(rec_texts))
    return items
