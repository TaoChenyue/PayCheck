"""PaddleOCR 引擎封装 — 银行无关，只做文字检测与识别

输入: 图片 (numpy BGR 或文件路径)
输出: list[OCRItem]  — 识别到的文字块及其坐标
"""

import logging
import time
import warnings
from typing import List, Union

import cv2
import numpy as np

from paycheck.ocr.layouts.base import OCRItem

# 在子进程中提前压制 requests 的版本警告（paddleocr 会触发）
warnings.filterwarnings("ignore", message=".*urllib3.*or.*chardet.*doesn't match")

log = logging.getLogger("paycheck.ocr")


_ocr = None


def _get_engine():
    """获取 PaddleOCR 引擎（惰性初始化，全局单例）"""
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        log.info("加载 PaddleOCR 模型...")
        try:
            _ocr = PaddleOCR(
                lang='ch',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                show_log=False,
            )
        except (TypeError, ValueError):
            _ocr = PaddleOCR(lang='ch')
    return _ocr


def process_image(
    image_input: Union[str, np.ndarray],
    timeout_sec: float = 600,
) -> List[OCRItem]:
    """识别图片中的文字

    Args:
        image_input: 图片路径 (str) 或 BGR numpy 数组
        timeout_sec: 超时秒数
    Returns:
        OCRItem 列表
    """
    engine = _get_engine()
    start_time = time.time()

    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            log.warning("无法读取图像: %s", image_input)
            return []
    else:
        img = image_input

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

    return items
