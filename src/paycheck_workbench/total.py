"""总账户虚拟源：三源统一字段映射、覆盖合并、有效属性与单表筛选分页（TCY-27 设计 v2）

覆盖与标签在查询时合并（不落库打标）：本地库数千行级，全量取回后在内存中完成
统一映射 → 读覆盖/标签 → 有效属性计算（覆盖 > 原始方向）→ 筛选（含属性/标签维度）→ 排序 → 单表分页。

方向约束铁律（设计 v2 §2）：
  方向=收入的行只能是收入或不计；方向=支出的行只能是支出或不计；永不反向。
  不计收支/中性行默认不计，可改为计入，计入方向按金额符号定（正=收入、负=支出）。
全程无任何自动识别/自动标注/自动改属性。
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Set, Tuple

from paycheck_workbench import db
from paycheck_workbench.sources import (
    SOURCE_ALIPAY,
    SOURCE_BOC,
    SOURCE_CONFIGS,
    SOURCES,
)

_TOTAL_SORT_KEYS = {"datetime", "amount", "counterparty"}

# ---------------------------------------------------------------------------
# 统一字段映射（设计 §2.2）
# ---------------------------------------------------------------------------

def map_row(source: str, raw: dict) -> dict:
    """三源物理行 → 总账户统一字段。raw 为该源全部原始列（行详情展开用）。"""
    cfg = SOURCE_CONFIGS[source]
    if source == SOURCE_BOC:
        time_value = " ".join(filter(None, [raw.get("date", ""), raw.get("time", "")])).strip()
        direction = raw.get("tx_type", "")
        counterparty = raw.get("counterparty", "")
        summary = raw.get("tx_name", "")
        memo = raw.get("memo", "")
        if memo:
            summary = f"{summary}（{memo}）"
        category = raw.get("channel", "")
        status = ""
    elif source == SOURCE_ALIPAY:
        time_value = raw.get("交易时间", "")
        direction = raw.get("收/支", "")
        counterparty = raw.get("交易对方", "")
        summary = raw.get("商品说明", "")
        category = raw.get("交易分类", "")
        status = raw.get("交易状态", "")
    else:  # wechat
        time_value = raw.get("交易时间", "")
        direction = raw.get("收/支", "")
        if direction == "中性交易":
            direction = "不计收支"  # 微信「中性交易」统一展示为「不计收支」
        # 微信中性交易行「交易对方 / 商品」常为占位符 '/'，按空处理（商品空则用交易类型）
        counterparty = raw.get("交易对方", "")
        if counterparty == "/":
            counterparty = ""
        product = raw.get("商品", "")
        summary = product if product and product != "/" else raw.get("交易类型", "")
        category = raw.get("交易类型", "")
        status = raw.get("当前状态", "")
    return {
        "id": f"{source}:{raw['_id']}",
        "source": source,
        "time": time_value,
        "date": time_value[:10],
        "direction": direction,
        "amount": raw.get(cfg.amount_col, ""),
        "counterparty": counterparty,
        "summary": summary,
        "category": category,
        "status": status,
        "source_file": raw.get("source_file", ""),
        "imported_at": raw.get("imported_at", ""),
        "raw": {k: v for k, v in raw.items() if k != "_id"},
        "_id": raw["_id"],
    }


def fetch_rows(conn, sources: List[str]) -> List[dict]:
    """取回所选源的全部明细行并做统一映射（未合并覆盖/标签）。"""
    rows: List[dict] = []
    for source in sources:
        cfg = SOURCE_CONFIGS[source]
        try:
            db_rows = conn.execute(f'SELECT * FROM "{cfg.table}"').fetchall()
        except sqlite3.OperationalError as exc:
            raise db.DataError(f"数据表 {cfg.table} 不存在，请先初始化") from exc
        for r in db_rows:
            raw = dict(r)
            raw["_id"] = raw.pop("id")
            rows.append(map_row(source, raw))
    return rows


# ---------------------------------------------------------------------------
# 覆盖 / 标签合并与有效属性
# ---------------------------------------------------------------------------

def merge_attrs(conn, rows: List[dict]) -> None:
    """读覆盖与标签合并到行上（原地）。

    有效属性 = 覆盖 > 原始方向：有覆盖以覆盖为准；否则方向=收入/支出 → 计入，
    其余（不计收支/中性）→ 不计。没有其他任何自动逻辑（设计 v2 §2）。
    """
    overrides = db.fetch_overrides(conn)
    tags = db.fetch_row_tags(conn)
    for row in rows:
        override = overrides.get(row["id"])
        row["counted"] = bool(override) if override is not None else row["direction"] in ("收入", "支出")
        row["tags"] = tags.get(row["id"], [])


def _counted_direction(row: dict) -> str:
    """计入行的汇总方向：原始方向优先；不计收支/中性行按金额符号（正=收入、负=支出）。"""
    if row["direction"] == "收入":
        return "收入"
    if row["direction"] == "支出":
        return "支出"
    return "收入" if _amount(row) >= 0 else "支出"


# ---------------------------------------------------------------------------
# 筛选
# ---------------------------------------------------------------------------

def filter_rows(
    rows: List[dict],
    *,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    directions: Optional[List[str]] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    sources: Optional[List[str]] = None,
    counted: Optional[Set[str]] = None,
    tags: Optional[List[str]] = None,
) -> List[dict]:
    """统一字段筛选（关键词搜对方+摘要，设计 §2.1）。

    - counted：属性维度。None 不过滤；空集合匹配 0 行（「属性」两档全不勾选）；
      集合内含 "1"/"0" 按有效属性过滤。
    - tags：标签维度（OR 语义，设计 v2 §4）。空/None 不过滤（无标签行仅在全部未勾选时显示）。
    """
    needle = (q or "").strip().casefold()
    tag_ids: Set[int] = {int(t) for t in tags} if tags else set()
    source_set = set(sources) if sources is not None else None

    def match(row: dict) -> bool:
        if needle and needle not in f"{row['counterparty']}{row['summary']}".casefold():
            return False
        if date_from and row["date"] < date_from:
            return False
        if date_to and row["date"] > date_to:
            return False
        if directions and row["direction"] not in directions:
            return False
        if source_set is not None and row["source"] not in source_set:
            return False
        if amount_min is not None or amount_max is not None:
            try:
                amount = float(row["amount"] or 0)
            except ValueError:
                amount = 0.0
            if amount_min is not None and amount < amount_min:
                return False
            if amount_max is not None and amount > amount_max:
                return False
        if counted is not None and ("1" if row["counted"] else "0") not in counted:
            return False
        if tag_ids:
            row_tag_ids = {t["id"] for t in row["tags"]}
            if not (row_tag_ids & tag_ids):
                return False
        return True

    return [r for r in rows if match(r)]


def _amount(row: dict) -> float:
    try:
        return float(row["amount"] or 0)
    except ValueError:
        return 0.0


def sort_rows(rows: List[dict], sort: str, order: str) -> None:
    """原地排序（时间/金额/对方，与单源视图一致的维度）。"""
    reverse = order != "asc"
    if sort == "amount":

        def key(row):
            try:
                return float(row["amount"] or 0)
            except ValueError:
                return 0.0

    elif sort == "counterparty":
        key = lambda row: row["counterparty"] or ""  # noqa: E731
    else:
        key = lambda row: row["time"] or ""  # noqa: E731
    rows.sort(key=key, reverse=reverse)


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "_id"}


def _pipeline(conn, sources: List[str], **filters) -> List[dict]:
    """统一映射 → 合并覆盖/标签 → 筛选（含属性/标签维度）。"""
    rows = fetch_rows(conn, sources)
    merge_attrs(conn, rows)
    return filter_rows(rows, **filters)


# ---------------------------------------------------------------------------
# 查询 / 汇总（单表口径，标准分页）
# ---------------------------------------------------------------------------

def query_rows(
    conn,
    *,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    directions: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    counted: Optional[Set[str]] = None,
    tags: Optional[List[str]] = None,
    sort: str = "datetime",
    order: str = "desc",
    page: int = 1,
    page_size: int = db._DEFAULT_PAGE_SIZE,
) -> dict:
    """总账户明细查询：一张全部账单表（收支混排），标准 page 分页（与渠道页签同一套）。"""
    if page_size not in db._PAGE_SIZES:
        page_size = db._DEFAULT_PAGE_SIZE
    if sort not in _TOTAL_SORT_KEYS:
        sort = "datetime"
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    rows = _pipeline(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
        counted=counted, tags=tags,
    )
    sort_rows(rows, sort, order)
    page = max(page, 1)
    offset = (page - 1) * page_size
    return {
        "total": len(rows), "page": page, "page_size": page_size,
        "rows": [_public(r) for r in rows[offset : offset + page_size]],
    }


def query_summary(
    conn,
    *,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    directions: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    counted: Optional[Set[str]] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """总账户汇总（计入口径，设计 v2 §2）：收入合计 / 支出合计 / 净收支 / 计入笔数，
    不计行不进任何收支合计，仅计入 not_counted 笔数。"""
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    rows = _pipeline(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
        counted=counted, tags=tags,
    )

    def agg(candidate_rows: List[dict]) -> dict:
        return {"count": len(candidate_rows), "sum": round(sum(_amount(r) for r in candidate_rows), 2)}

    income = [r for r in rows if r["counted"] and _counted_direction(r) == "收入"]
    expense = [r for r in rows if r["counted"] and _counted_direction(r) == "支出"]
    income_agg, expense_agg = agg(income), agg(expense)
    return {
        "income": income_agg,
        "expense": expense_agg,
        "net": round(income_agg["sum"] - expense_agg["sum"], 2),
        "count": income_agg["count"] + expense_agg["count"],
        "not_counted": sum(1 for r in rows if not r["counted"]),
    }


def resolve_scope_rows(conn, body: dict) -> List[Tuple[str, int]]:
    """解析批量操作 scope → 行键列表 [(source, row_id), ...]（overrides 与 tags apply 共用）。

    - scope=ids：body["ids"] 为 ["source:row_id", ...]，不存在的行自动跳过。
    - scope=filter：body["filters"] 为与 /api/rows 一致的筛选参数（含 counted/tags 维度），
      作用于整个筛选结果（不只当前页）。
    """
    scope = body.get("scope")
    rows = fetch_rows(conn, list(SOURCES))
    merge_attrs(conn, rows)
    if scope == "ids":
        keys: Set[Tuple[str, int]] = set()
        for item in body.get("ids") or []:
            source, sep, row_id = str(item).partition(":")
            if not sep or source not in SOURCE_CONFIGS or not row_id.isdigit():
                raise db.DataError(f"行标识无效：{item}")
            keys.add((source, int(row_id)))
        return [(r["source"], r["_id"]) for r in rows if (r["source"], r["_id"]) in keys]
    if scope == "filter":
        f = body.get("filters") or {}
        counted = None
        if f.get("counted") is not None:
            counted = {str(v) for v in f["counted"] if str(v) in ("0", "1")}
        matched = filter_rows(
            rows,
            q=(f.get("q") or "").strip() or None,
            date_from=f.get("date_from") or None,
            date_to=f.get("date_to") or None,
            directions=[d for d in (f.get("directions") or []) if d] or None,
            amount_min=_opt_float(f.get("amount_min")),
            amount_max=_opt_float(f.get("amount_max")),
            sources=[s for s in (f.get("sources") or list(SOURCES)) if s in SOURCE_CONFIGS],
            counted=counted,
            tags=[str(t) for t in (f.get("tags") or [])] or None,
        )
        return [(r["source"], r["_id"]) for r in matched]
    raise db.DataError("scope 必须是 ids 或 filter")


def _opt_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise db.DataError(f"参数不是有效数字：{value}") from exc
