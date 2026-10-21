"""总账户虚拟源：三源统一字段映射、筛选、内部转账规则求值与三区划分（TCY-15/TCY-18）

规则仅在查询时求值（不落库打标）：本地库数千行级，全量取回后在内存中完成
统一映射 → 筛选 → 启用规则匹配 → 三区划分 → 分区排序 → 分页，避免多表 UNION
下复杂 SQL 与打标数据过期的一致性问题。

三区口径（TCY-20 设计 §2）：
  未命中任何启用规则，方向=收入 → 真实收入
  未命中任何启用规则，方向=支出 → 真实支出
  命中启用规则（fold/hide）或未命中的不计收支行 → 内部流动
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

_TOTAL_SORT_KEYS = {"datetime", "amount", "counterparty"}

# 通道对映射（TCY-20 设计 §3.1）：内置预设规则名 → 通道对（服务器常量，随预设维护）。
# 自定义规则自成一个通道对（名 = 规则名）；未命中规则的不计收支行按来源归组。
FLOW_PAIRS: Dict[str, str] = {
    "余额宝-转入转出": "支付宝 ↔ BOC",
    "支付宝余额-提现": "支付宝 ↔ BOC",
    "支付宝小荷包": "支付宝 ↔ BOC",
    "银行卡快捷支付-渠道行（支付宝）": "支付宝 ↔ BOC",
    "银行卡渠道退款（支付宝）": "支付宝 ↔ BOC",
    "平台提现入账": "支付宝 ↔ BOC",
    "基金/平台入账（蚂蚁）": "支付宝 ↔ BOC",
    "基金/平台入账（支付宝）": "支付宝 ↔ BOC",
    "零钱通-转入转出": "微信 ↔ BOC",
    "微信零钱-充值提现": "微信 ↔ BOC",
    "银行卡快捷支付-渠道行（财付通）": "微信 ↔ BOC",
    "银行卡渠道退款（财付通）": "微信 ↔ BOC",
    "基金/平台入账（财付通）": "微信 ↔ BOC",
    "花呗还款-支付宝侧": "花呗",
    "花呗还款-银行侧": "花呗",
    "同名账户互转": "同名账户",
}

# 跨区引用提示的平台名（设计 §3.2）：渠道重复组的真身在真实支出区
PAIR_PLATFORMS = {"支付宝 ↔ BOC": "支付宝", "微信 ↔ BOC": "微信"}


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


def _zone_of(row: dict) -> str:
    """三区划分（TCY-20 设计 §2）：命中规则或不计收支未命中 → flow，其余按方向进真实区。"""
    if row["_hits"]:
        return "flow"
    if row["direction"] == "收入":
        return "income"
    if row["direction"] == "支出":
        return "expense"
    return "flow"  # 不计收支（含微信中性交易映射）等未命中行，不污染真实收支


def _mark_of(row: dict) -> dict:
    """内部流动行标记（存储值不变，仅含义重新表述）：hide→重复记录、fold→内部流动。"""
    names = [h["name"] for h in row["_hits"]]
    label = "duplicate" if any(h["action"] == "hide" for h in row["_hits"]) else "flow"
    return {"mark": label, "rule_names": names}


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
    return {k: v for k, v in row.items() if k not in ("_id", "_hits")}


def _flow_public(row: dict) -> dict:
    """内部流动行对外字段：统一字段 + 标记与命中规则名。"""
    public = _public(row)
    public.update(_mark_of(row))
    return public


def _pair_of(row: dict) -> str:
    """行所属通道对：优先取命中规则的内置映射，其次自定义规则名，未命中按来源归组。"""
    names = [h["name"] for h in row["_hits"]]
    for name in names:
        if name in FLOW_PAIRS:
            return FLOW_PAIRS[name]
    if names:
        return names[0]  # 自定义规则自成一个通道对（名 = 规则名）
    return SOURCE_CONFIGS[row["source"]].label


def _pick_main(rows_desc: List[dict]) -> dict:
    """组主记录（设计 §3.2）：组内方向=收入的最新一行 → 支出最新 → 时间最新。"""
    for row in rows_desc:
        if row["direction"] == "收入":
            return row
    for row in rows_desc:
        if row["direction"] == "支出":
            return row
    return rows_desc[0]


def _group_flows(rows: List[dict]) -> List[dict]:
    """内部流动行按「通道对 × 日期」分组（聚合级，不逐笔配对），组按主记录时间倒序。"""
    buckets: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        buckets.setdefault((_pair_of(row), row["date"]), []).append(row)
    groups: List[dict] = []
    for (pair, date), members in buckets.items():
        desc = sorted(members, key=lambda r: r["time"] or "", reverse=True)
        main = _pick_main(desc)
        others = [r for r in desc if r is not main]
        others.sort(key=lambda r: r["time"] or "")  # 成员时间正序
        has_dup = any(_mark_of(r)["mark"] == "duplicate" for r in members)
        has_platform = any(r["source"] in (SOURCE_ALIPAY, SOURCE_WECHAT) for r in members)
        platform = PAIR_PLATFORMS.get(pair, "")
        main_public = _flow_public(main)
        main_public["member_count"] = len(others)
        groups.append({
            "key": f"{pair}|{date}",
            "pair": pair,
            "date": date,
            "main": main_public,
            "members": [_flow_public(r) for r in others],
            # 渠道重复行的真身在真实支出区：组内只有银行侧行时提示跨区引用（设计 §3.2）
            "cross_ref": bool(has_dup and not has_platform and platform),
            "platform": platform,
        })
    groups.sort(key=lambda g: g["main"]["time"] or "", reverse=True)
    return groups


def _zone_rows(conn, selected, **filters) -> Tuple[List[dict], List[dict], List[dict]]:
    """取回所选源并返回三区行列表（income, expense, flow）。

    真实区应用收/支筛选；流动区不按方向筛选（TCY-20 设计 §3.4），筛选后重新
    分组与主记录递补由分组层处理。
    """
    base = fetch_rows(conn, selected)
    rules = [r for r in db.list_rules(conn) if r["enabled"]]
    apply_rules(conn, base, rules)
    real = filter_rows(base, **filters)
    flow_filters = {**filters, "directions": None}
    flow = filter_rows(base, **flow_filters)
    income = [r for r in real if _zone_of(r) == "income"]
    expense = [r for r in real if _zone_of(r) == "expense"]
    flow_rows = [r for r in flow if _zone_of(r) == "flow"]
    return income, expense, flow_rows


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
    sort: str = "datetime",
    order: str = "desc",
    income_page: int = 1,
    expense_page: int = 1,
    flow_page: int = 1,
    page_size: int = db._DEFAULT_PAGE_SIZE,
) -> dict:
    """总账户明细查询：统一映射 + 筛选 + 启用规则求值 → 三区结构 + 各区独立分页。

    真实收入/真实支出区沿用排序与按行分页；内部流动区固定按组主记录时间倒序、
    按组数分页（TCY-20 设计 §3.3）。
    """
    if page_size not in db._PAGE_SIZES:
        page_size = db._DEFAULT_PAGE_SIZE
    if sort not in _TOTAL_SORT_KEYS:
        sort = "datetime"
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    income, expense, flow_rows = _zone_rows(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )
    sort_rows(income, sort, order)
    sort_rows(expense, sort, order)

    def page_of(rows: List[dict], page: int) -> dict:
        page = max(page, 1)
        offset = (page - 1) * page_size
        return {
            "total": len(rows), "page": page, "page_size": page_size,
            "rows": [_public(r) for r in rows[offset : offset + page_size]],
        }

    groups = _group_flows(flow_rows)
    flow_page = max(flow_page, 1)
    flow_offset = (flow_page - 1) * page_size
    return {
        "income": page_of(income, income_page),
        "expense": page_of(expense, expense_page),
        "flow": {
            "total": len(groups), "page": flow_page, "page_size": page_size,
            "row_total": len(flow_rows),
            "groups": groups[flow_offset : flow_offset + page_size],
        },
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
    """总账户汇总（真实口径，TCY-20 设计 §1）：真实收入 / 真实支出 / 净收支 / 真实笔数，
    另返回内部流动的组数与行数（不计入真实收支），取代旧的 counted/transfer/hidden 三口径。"""
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    income, expense, flow_rows = _zone_rows(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )

    def agg(rows: List[dict]) -> dict:
        return {"count": len(rows), "sum": round(sum(_amount(r) for r in rows), 2)}

    income_agg, expense_agg = agg(income), agg(expense)
    return {
        "income": income_agg,
        "expense": expense_agg,
        "net": round(income_agg["sum"] - expense_agg["sum"], 2),
        "count": income_agg["count"] + expense_agg["count"],
        "flow": {"groups": len(_group_flows(flow_rows)), "rows": len(flow_rows)},
    }
