"""BankLayout 抽象基类 + 共用工具函数"""

import logging

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image


log = logging.getLogger("paycheck.layout")


@dataclass
class OCRItem:
    """OCR 识别出的单个文字块"""
    text: str
    cx: float  # 中心 X 坐标
    cy: float  # 中心 Y 坐标


@dataclass
class Row:
    """一行交易记录的各字段原始值"""
    date: str = ""
    time: str = ""
    currency: str = ""
    amount: str = ""
    balance: str = ""
    tx_name: str = ""
    channel: str = ""
    branch: str = ""
    counterparty: str = ""
    memo: str = ""
    cp_account: str = ""
    cp_bank: str = ""


BBox = Tuple[int, int, int, int]  # top, bottom, left, right


class BankLayout(ABC):
    """银行流水单布局接口 — 新增银行需实现此接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """布局名称，与输入目录下的子目录名一致"""

    @property
    @abstractmethod
    def columns(self) -> List[Tuple[str, int, int]]:
        """列定义: [(字段名, x_min, x_max), ...]（基准缩放 3.0x 下）"""

    @property
    def base_scale(self) -> float:
        return 3.0

    # ── 可选覆盖 ──

    def detect_table(self, image: Image.Image) -> BBox:
        """检测表格区域，默认使用亮度分析法"""
        return find_table_bounds(image)

    def group_rows(self, items: List[OCRItem], scale: float) -> List[Row]:
        """将 OCR 项按行分组，返回 Row 列表

        默认以 date 列的文字 Y 坐标做锚点，
        其他列的文字按 Y 轴最近邻匹配归属。
        """
        return group_items_to_rows(items, scale, self.columns, self.base_scale)

    # ── 必须实现 ──

    @abstractmethod
    def to_transactions(self, rows: List[Row]) -> List[dict]:
        """将 Row 列表转为标准交易记录 dict 列表

        输出字段: date, time, tx_type, amount, counterparty,
                  channel, balance, memo, tx_name
        """


# =========================================================================
# 默认表格检测（亮度分析法）
# =========================================================================

def find_table_bounds(pil_image: Image.Image) -> BBox:
    """检测图像中最大的连续深色内容块（表格区域）

    使用 numpy 向量化计算，比纯 Python 逐像素循环快 ~10x。
    """
    width, height = pil_image.size

    # 转灰度亮度矩阵 [H, W]
    arr = np.array(pil_image, dtype=np.uint8)
    brightness = arr.astype(np.float32).mean(axis=2)

    DARK = 220
    MAX_GAP = 5
    MIN_CONTENT = max(10, width * 0.02)
    MIN_COL = max(5, height * 0.005)

    # 逐行扫描：统计每行深色像素数
    dark_per_row = (brightness < DARK).sum(axis=1)
    content_rows = dark_per_row > MIN_CONTENT

    # 合并相邻内容行形成块
    blocks = []
    start = -1
    empty_run = 0
    for y in range(height):
        if content_rows[y]:
            if start == -1:
                start = y
                empty_run = 0
            else:
                empty_run = 0
        else:
            if start != -1:
                empty_run += 1
                if empty_run > MAX_GAP:
                    blocks.append((start, y - empty_run))
                    start = -1
                    empty_run = 0
    if start != -1:
        blocks.append((start, height - 1))

    if not blocks:
        return (0, height, 0, width)

    # 取最大块作为表格区域
    table = max(blocks, key=lambda b: b[1] - b[0])
    t, b = table

    # 水平边界：在表格行范围内逐列统计深色像素
    col_dark = (brightness[t : b + 1, :] < DARK).sum(axis=0)
    left = int((col_dark > MIN_COL).argmax())
    right = int(width - 1 - (col_dark[::-1] > MIN_COL).argmax())

    pad = 4
    top = max(0, t - pad)
    bottom = min(height, b + pad)
    left = max(0, left - pad)
    right = min(width, right + pad)
    log.debug("表格检测: %dx%d, 区域 top=%d bottom=%d left=%d right=%d", width, height, top, bottom, left, right)
    return (top, bottom, left, right)


# =========================================================================
# 默认行分组逻辑
# =========================================================================

def group_items_to_rows(
    items: List[OCRItem],
    scale: float,
    columns: List[Tuple[str, int, int]],
    base_scale: float = 3.0,
) -> List[Row]:
    """将 OCR 项按列映射并分组为交易行

    以 date 列的文字 Y 坐标做锚点，其余列的文字按 Y 最近邻归属。
    """
    if not items:
        return []

    # 按 scale 缩放列坐标
    factor = scale / base_scale
    scaled_cols = [
        (key, int(min_x * factor), int(max_x * factor))
        for key, min_x, max_x in columns
    ]

    def get_col_key(cx: float) -> str:
        for key, min_x, max_x in scaled_cols:
            if min_x <= cx < max_x:
                return key
        return ""

    # 按列分配文字块
    col_map: dict = {}
    for it in items:
        key = get_col_key(it.cx)
        if key:
            col_map.setdefault(key, []).append(it)

    # 以 date 列做行锚点
    dates = sorted(col_map.get("date", []), key=lambda x: x.cy)
    if not dates:
        return []

    rows: List[Row] = [Row() for _ in dates]
    ycs = [d.cy for d in dates]
    MAX_ROW_DIST = 40 * factor

    for key, its in col_map.items():
        if key == "date":
            for j, d in enumerate(dates):
                setattr(rows[j], "date", d.text)
            continue
        for it in its:
            best = float("inf")
            best_ri = 0
            for j, yc in enumerate(ycs):
                d = abs(it.cy - yc)
                if d < best:
                    best = d
                    best_ri = j
            if best <= MAX_ROW_DIST:
                existing = getattr(rows[best_ri], key, "")
                setattr(rows[best_ri], key, existing + it.text)

    log.debug("行分组: %d 个OCR块 → %d 行", len(items), len(rows))
    return rows
