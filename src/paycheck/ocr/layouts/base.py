"""BankLayout 抽象基类 + 共用工具函数"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image


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
    amount: str = ""
    balance: str = ""
    tx_name: str = ""
    channel: str = ""
    counterparty: str = ""
    memo: str = ""


BBox = Tuple[int, int, int, int]  # top, bottom, left, right


class BankLayout(ABC):
    """银行流水单布局接口 — 新增银行需实现此接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """布局名称，与 resource/ 下的子目录名一致"""

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
    """检测图像中最大的连续深色内容块（表格区域）"""
    width, height = pil_image.size
    pixels = pil_image.load()

    DARK_BRIGHTNESS = 220
    MIN_CONTENT = max(10, width * 0.02)
    MAX_GAP = 5

    # 逐行统计深色像素
    is_content = [0] * height
    for y in range(height):
        dark_count = 0
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            brightness = (r + g + b) / 3
            if brightness < DARK_BRIGHTNESS:
                dark_count += 1
        is_content[y] = 1 if dark_count > MIN_CONTENT else 0

    # 合并相邻行形成块
    blocks = []
    start = -1
    empty_run = 0
    for y in range(height):
        if is_content[y]:
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

    # 取最大块
    table = max(blocks, key=lambda b: b[1] - b[0])

    # 水平边界
    MIN_COL = max(5, height * 0.005)
    left, right = 0, width - 1
    for x in range(width):
        dark_count = 0
        for y in range(table[0], table[1] + 1):
            r, g, b = pixels[x, y][:3]
            brightness = (r + g + b) / 3
            if brightness < DARK_BRIGHTNESS:
                dark_count += 1
        if dark_count > MIN_COL:
            left = x
            break
    for x in range(width - 1, -1, -1):
        dark_count = 0
        for y in range(table[0], table[1] + 1):
            r, g, b = pixels[x, y][:3]
            brightness = (r + g + b) / 3
            if brightness < DARK_BRIGHTNESS:
                dark_count += 1
        if dark_count > MIN_COL:
            right = x
            break

    pad = 4
    return (
        max(0, table[0] - pad),
        min(height, table[1] + pad),
        max(0, left - pad),
        min(width, right + pad),
    )


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

    return rows
