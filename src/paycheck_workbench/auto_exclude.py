"""BOC 重复账单自动不计（TCY-52 方案 A）：匹配核心

铁律范围化例外：TCY-27 设计 v2 规定全程无任何自动标注，本需求经成员拍板
（TCY-52），自动逻辑只在本模块内生效——只写 counted=0、永不写 counted=1、
只作用于 BOC 行；查询/汇总路径一概不动。

主规则（高置信，自动执行）：时间精确到分钟一致 + 金额精确到分一致
（容差 0.005 元）+ 方向一致，三者同时成立才匹配。

降误判设计：
  - 同距多候选（同一分钟+金额+方向有多个支付宝/微信行）为歧义，跳过不标记
  - 中性行（支付宝「不计收支」/ 微信「中性交易」）不参与匹配
  - 非人民币（BOC currency 非空且不含「人民币」）跳过
  - total_overrides 已有记录的行跳过（幂等 + 尊重用户手动设置）
  - 一对一贪心：候选只被消费一次，杜绝一对多/多对一过度标记
"""

from __future__ import annotations

import re
import sqlite3
from typing import Dict, List, Optional, Tuple

from paycheck_workbench import db, total
from paycheck_workbench.sources import SOURCE_BOC

# 功能开关（拍板决策 5：常量开关先行，UI 开关后置）
AUTO_EXCLUDE_ENABLED = True

_AMOUNT_TOLERANCE = 0.005  # 金额容差（元）：防浮点误差
_MINUTE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def _parse_amount(text: str) -> Optional[float]:
    """金额文本 → 数值：剥离货币符号与千分位逗号；无法解析返回 None。"""
    cleaned = (
        str(text or "")
        .replace("￥", "")
        .replace("¥", "")
        .replace(",", "")
        .replace("，", "")
        .replace(" ", "")
        .strip()
    )
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _minute(row: dict) -> str:
    """统一映射后的时间 → YYYY-MM-DD HH:MM；不足 16 位（BOC 缺 time 等）返回空串。"""
    value = str(row["time"] or "").strip()
    return value[:16] if _MINUTE_RE.match(value) else ""


def _row_ref(row: dict) -> dict:
    """预览展示用的行摘要（对方/摘要用于弹窗成对明细）。"""
    return {
        "id": f'{row["source"]}:{row["_id"]}',
        "source": row["source"],
        "time": row["time"],
        "amount": row["amount"],
        "direction": row["direction"],
        "counterparty": row["counterparty"],
        "summary": row["summary"],
    }


def _candidates(conn: sqlite3.Connection) -> Tuple[List[dict], List[dict]]:
    """载入参与匹配的行：无覆盖的 BOC 行与支付宝/微信收支候选行。

    跳过：已有覆盖的 BOC 行、方向非支出/收入的双方行、时间不可辨（缺 time
    或格式不符）、非人民币的 BOC 行、金额无法解析的行。
    """
    overrides = db.fetch_overrides(conn)
    rows = total.fetch_rows(conn, ["boc", "alipay", "wechat"])
    boc_rows: List[dict] = []
    others: List[dict] = []
    for row in rows:
        if row["direction"] not in ("支出", "收入"):
            continue  # 中性行（不计收支/中性交易）不参与匹配
        minute = _minute(row)
        if not minute or _parse_amount(row["amount"]) is None:
            continue
        if row["source"] == SOURCE_BOC:
            if f'{row["source"]}:{row["_id"]}' in overrides:
                continue  # 已有覆盖的行跳过（用户手动设置优先）
            currency = (row["raw"].get("currency") or "").strip()
            if currency and "人民币" not in currency:
                continue  # 非人民币跳过
            boc_rows.append({**row, "_minute": minute})
        else:
            others.append({**row, "_minute": minute})
    boc_rows.sort(key=lambda r: (r["_minute"], r["_id"]))
    return boc_rows, others


def scan(conn: sqlite3.Connection) -> dict:
    """全量扫描（只读，不写入）。返回 {"matches": [...], "ambiguous": [...]}。

    - matches：唯一命中对 {boc, other}（行摘要，含 id），可自动标记或预览勾选
    - ambiguous：同距多候选的 BOC 行 {boc, candidates}，仅预览提示、不自动标记
    """
    boc_rows, others = _candidates(conn)
    buckets: Dict[Tuple, List[dict]] = {}
    for row in others:
        key = (row["_minute"], row["direction"])
        buckets.setdefault(key, []).append(row)

    matches: List[dict] = []
    ambiguous: List[dict] = []
    for boc in boc_rows:
        amount = _parse_amount(boc["amount"])
        # 金额按容差比对（精确到分，防浮点误差）；同距多候选为歧义
        candidates = [
            c for c in buckets.get((boc["_minute"], boc["direction"]), [])
            if abs(_parse_amount(c["amount"]) - amount) <= _AMOUNT_TOLERANCE
        ]
        if not candidates:
            continue
        if len(candidates) > 1:
            # 任意配对都可能误标，跳过进预览供人工判断
            ambiguous.append({"boc": _row_ref(boc), "candidates": [_row_ref(c) for c in candidates]})
            continue
        other = candidates[0]
        buckets[(boc["_minute"], boc["direction"])].remove(other)  # 一对一贪心：候选只被消费一次
        matches.append({"boc": _row_ref(boc), "other": _row_ref(other)})
    return {"matches": matches, "ambiguous": ambiguous}


def apply_matches(conn: sqlite3.Connection, boc_ids: List[str]) -> int:
    """按 BOC 行 id 批量写入不计覆盖（counted=0，upsert）。只接受 boc 源行。"""
    keys: List[Tuple[str, int]] = []
    for item in boc_ids:
        source, sep, row_id = str(item).partition(":")
        if not sep or not row_id.isdigit() or source != SOURCE_BOC:
            raise db.DataError(f"行标识无效（仅支持 BOC 行）：{item}")
        keys.append((source, int(row_id)))
    return db.set_overrides(conn, keys, 0)


def run_auto_exclude(conn: sqlite3.Connection) -> dict:
    """导入确认后的自动标记：扫描 + 写入 counted=0。返回写入数与扫描明细。"""
    result = scan(conn)
    marked = apply_matches(conn, [m["boc"]["id"] for m in result["matches"]]) if result["matches"] else 0
    return {"auto_excluded": marked, **result}
