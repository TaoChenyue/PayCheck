"""总账户虚拟源：三源统一字段映射、筛选、内部转账规则求值与三种显示模式（TCY-15）

规则仅在查询时求值（设计 §3.6，不落库打标）：本地库数千行级，全量取回后在
内存中完成统一映射 → 筛选 → 启用规则匹配 → 模式过滤 → 排序 → 分页，避免
多表 UNION 下复杂 SQL 与打标数据过期的一致性问题。

显示模式（设计 §2.3）：
  show  全部显示：规则临时关闭，全部行计入汇总
  fold  折叠标灰（默认）：fold 命中行保留在列表并标记、不计入汇总；hide 命中行隐藏
  hide  隐藏：命中行全部隐藏、不计入汇总
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from paycheck_workbench import db
from paycheck_workbench.sources import (
    SOURCE_ALIPAY,
    SOURCE_BOC,
    SOURCE_CONFIGS,
    SOURCE_WECHAT,
    SOURCES,
)

TRANSFER_MODES = ("show", "fold", "hide")
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
        "_hits": [],
    }


def fetch_rows(conn, sources: List[str]) -> List[dict]:
    """取回所选源的全部明细行并做统一映射（未筛选、未应用规则）。"""
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
# 筛选 / 规则求值 / 模式处理
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
) -> List[dict]:
    """统一字段筛选（关键词搜对方+摘要，设计 §2.1）。"""
    needle = (q or "").strip().casefold()

    def match(row: dict) -> bool:
        if needle and needle not in f"{row['counterparty']}{row['summary']}".casefold():
            return False
        if date_from and row["date"] < date_from:
            return False
        if date_to and row["date"] > date_to:
            return False
        if directions and row["direction"] not in directions:
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
        return True

    return [r for r in rows if match(r)]


def apply_rules(conn, rows: List[dict], rules: List[dict]) -> None:
    """为每行打上命中的启用规则（写入 _hits，原地）。规则查询时求值，不落库。"""
    for row in rows:
        row["_hits"] = []
    by_source: Dict[str, List[dict]] = {}
    for rule in rules:
        by_source.setdefault(rule["source"], []).append(rule)
    for source, src_rules in by_source.items():
        for rule in src_rules:
            ids = db.rule_match_ids(conn, rule)
            if not ids:
                continue
            for row in rows:
                if row["source"] == source and row["_id"] in ids:
                    row["_hits"].append(rule)


def apply_mode(rows: List[dict], mode: str) -> Tuple[List[dict], List[dict]]:
    """按显示模式拆分（可见行, 隐藏行）。fold 模式下 hide 命中的行仍隐藏（设计 §1）。"""
    if mode == "show":
        for row in rows:
            row["transfer"] = None
        return rows, []
    visible: List[dict] = []
    hidden: List[dict] = []
    for row in rows:
        hits = row["_hits"]
        if not hits:
            row["transfer"] = None
            visible.append(row)
            continue
        names = [h["name"] for h in hits]
        if mode == "hide" or any(h["action"] == "hide" for h in hits):
            row["transfer"] = {"rule_names": names, "action": "hide"}
            hidden.append(row)
        else:
            row["transfer"] = {"rule_names": names, "action": "fold"}
            visible.append(row)
    return visible, hidden


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


def _hidden_stats(hidden: List[dict]) -> dict:
    """隐藏行统计（折叠模式下的提示条：数量 + 涉及规则名）。"""
    names: List[str] = []
    for row in hidden:
        for name in row["transfer"]["rule_names"]:
            if name not in names:
                names.append(name)
    return {"count": len(hidden), "rule_names": names}


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("_id", "_hits")}


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
    page: int = 1,
    page_size: int = db._DEFAULT_PAGE_SIZE,
    sort: str = "datetime",
    order: str = "desc",
    transfer: str = "fold",
) -> dict:
    """总账户明细查询：统一映射 + 筛选 + 启用规则求值 + 模式过滤 + 分页。"""
    if transfer not in TRANSFER_MODES:
        transfer = "fold"
    if page_size not in db._PAGE_SIZES:
        page_size = db._DEFAULT_PAGE_SIZE
    if sort not in _TOTAL_SORT_KEYS:
        sort = "datetime"
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]

    rows = fetch_rows(conn, selected)
    rows = filter_rows(
        rows,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )
    sort_rows(rows, sort, order)
    if transfer == "show":
        visible, hidden = apply_mode(rows, "show")
    else:
        rules = [r for r in db.list_rules(conn) if r["enabled"]]
        apply_rules(conn, rows, rules)
        visible, hidden = apply_mode(rows, transfer)

    offset = (max(page, 1) - 1) * page_size
    return {
        "total": len(visible),
        "page": page,
        "page_size": page_size,
        "rows": [_public(r) for r in visible[offset : offset + page_size]],
        "hidden": _hidden_stats(hidden),
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
) -> dict:
    """总账户汇总：计入/不计入（fold 命中）/隐藏（hide 命中）三套口径一次返回，
    前端切换显示模式免重查（设计 §3.5）。"""
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    rows = fetch_rows(conn, selected)
    rows = filter_rows(
        rows,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )
    rules = [r for r in db.list_rules(conn) if r["enabled"]]
    apply_rules(conn, rows, rules)
    counted, transfer_rows, hidden_rows = [], [], []
    for row in rows:
        if not row["_hits"]:
            counted.append(row)
        elif any(h["action"] == "hide" for h in row["_hits"]):
            hidden_rows.append(row)
        else:
            transfer_rows.append(row)

    def agg(bucket: List[dict]) -> dict:
        income = expense = 0.0
        for row in bucket:
            try:
                amount = float(row["amount"] or 0)
            except ValueError:
                amount = 0.0
            if row["direction"] == "收入":
                income += amount
            elif row["direction"] == "支出":
                expense += amount
        return {"count": len(bucket), "income_sum": round(income, 2), "expense_sum": round(expense, 2)}

    return {
        "counted": agg(counted),
        "transfer": agg(transfer_rows),
        "hidden": agg(hidden_rows),
    }
