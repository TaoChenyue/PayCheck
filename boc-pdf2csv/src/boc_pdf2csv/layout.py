"""BOC 银行流水单布局 — 列坐标、表格检测、行分组、交易转换

合并自:
  - ocr_service/layouts/base.py  (OCRItem, Row, find_table_bounds, group_items_to_rows)
  - ocr_service/layouts/boc.py   (BOC_COLUMNS, rows_to_transactions)
  - ocr_service/layouts/__init__.py (注册表 — 已删除)
"""

import logging
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PIL import Image

# ── 字段名常量 ──
FIELD_TIME = "time"
FIELD_AMOUNT = "amount"
FIELD_COUNTERPARTY = "counterparty"
FIELD_TX_TYPE = "tx_type"
FIELD_BALANCE = "balance"
FIELD_CURRENCY = "currency"
FIELD_BRANCH = "branch"
FIELD_CP_ACCOUNT = "cp_account"
FIELD_CP_BANK = "cp_bank"
BANK_COL_DATE = "date"
BANK_COL_CHANNEL = "channel"
BANK_COL_MEMO = "memo"
BANK_COL_TX_NAME = "tx_name"

log = logging.getLogger("boc_pdf2csv.layout")

# ── BOC 列坐标（3.0x 缩放基准，共 12 列）──
# 各列: (字段名, x_min, x_max)
BOC_COLUMNS: List[Tuple[str, int, int]] = [
    (BANK_COL_DATE,       0,    202),
    (FIELD_TIME,          202,  380),
    (FIELD_CURRENCY,      380,  553),
    (FIELD_AMOUNT,        553,  737),
    (FIELD_BALANCE,       737,  923),
    (BANK_COL_TX_NAME,    923,  1093),
    (BANK_COL_CHANNEL,    1093, 1266),
    (FIELD_BRANCH,        1266, 1469),
    (BANK_COL_MEMO,       1469, 1689),
    (FIELD_COUNTERPARTY,  1689, 1909),
    (FIELD_CP_ACCOUNT,    1909, 2180),
    (FIELD_CP_BANK,       2180, 9999),
]

BBox = Tuple[int, int, int, int]  # top, bottom, left, right


@dataclass
class OCRItem:
    """OCR 识别出的单个文字块"""
    text: str
    cx: float   # 中心 X 坐标
    cy: float   # 中心 Y 坐标


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


# =========================================================================
# 表格检测（亮度分析法）
# =========================================================================

def find_table_bounds(pil_image: Image.Image) -> BBox:
    """检测图像中最大的连续深色内容块（表格区域）

    使用 numpy 向量化计算，比纯 Python 逐像素循环快 ~10x。

    Returns:
        (top, bottom, left, right)
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
    col_dark = (brightness[t: b + 1, :] < DARK).sum(axis=0)
    left = int((col_dark > MIN_COL).argmax())
    right = int(width - 1 - (col_dark[::-1] > MIN_COL).argmax())

    pad = 4
    top = max(0, t - pad)
    bottom = min(height, b + pad)
    left = max(0, left - pad)
    right = min(width, right + pad)
    log.debug("表格检测: %dx%d, 区域 top=%d bottom=%d left=%d right=%d",
              width, height, top, bottom, left, right)
    return (top, bottom, left, right)


# =========================================================================
# 行分组逻辑
# =========================================================================

def group_items_to_rows(
    items: List[OCRItem],
    scale: float,
    columns: List[Tuple[str, int, int]] = BOC_COLUMNS,
    base_scale: float = 3.0,
) -> List[Row]:
    """将 OCR 项按列映射并分组为交易行

    以 date 列的文字 Y 坐标做锚点，其余列的文字按 Y 最近邻归属。

    Args:
        items: OCR 文字块列表
        scale: 实际渲染缩放倍率
        columns: 列坐标定义（默认 BOC_COLUMNS）
        base_scale: 列坐标的基准缩放倍率

    Returns:
        Row 列表（每行一条交易）
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
    dates = sorted(col_map.get(BANK_COL_DATE, []), key=lambda x: x.cy)
    if not dates:
        return []

    rows: List[Row] = [Row() for _ in dates]
    ycs = [d.cy for d in dates]
    MAX_ROW_DIST = 40 * factor

    for key, its in col_map.items():
        if key == BANK_COL_DATE:
            for j, d in enumerate(dates):
                setattr(rows[j], BANK_COL_DATE, d.text)
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


# =========================================================================
# 交易转换（BOC 专属）
# =========================================================================

def rows_to_transactions(rows: List[Row]) -> List[dict]:
    """将 BOC 行数据转为标准交易记录

    不做字符级清洗，完全依赖 OCR 原始值。
    amount 正数为收入，负数为支出。

    Returns:
        交易字典列表，字段: date, time, tx_type, amount, counterparty,
        channel, balance, memo, tx_name, currency, branch, cp_account, cp_bank
    """
    transactions = []
    for r in rows:
        if not r.date and not r.amount:
            continue

        try:
            raw_amount = float(r.amount.replace(",", ""))
        except (ValueError, TypeError):
            continue

        tx_type = "支出" if raw_amount < 0 else "收入"
        amount = abs(raw_amount)

        try:
            balance = float(r.balance.replace(",", ""))
        except (ValueError, TypeError):
            balance = 0.0

        cp = r.counterparty.strip()

        transactions.append({
            BANK_COL_DATE: r.date,
            FIELD_TIME: r.time,
            FIELD_AMOUNT: amount,
            FIELD_BALANCE: balance,
            BANK_COL_TX_NAME: r.tx_name.strip(),
            BANK_COL_CHANNEL: r.channel.strip(),
            FIELD_COUNTERPARTY: cp,
            BANK_COL_MEMO: r.memo.strip(),
            FIELD_TX_TYPE: tx_type,
            FIELD_CURRENCY: r.currency.strip(),
            FIELD_BRANCH: r.branch.strip(),
            FIELD_CP_ACCOUNT: r.cp_account.strip(),
            FIELD_CP_BANK: r.cp_bank.strip(),
        })
    log.info("BOC转换: %d 行 → %d 条交易", len(rows), len(transactions))
    return transactions
