"""总账户虚拟源：三源统一字段映射、筛选、忽略规则求值与两区划分（TCY-15/TCY-24）

规则与配对仅在查询时计算（不落库打标）：本地库数千行级，全量取回后在内存中完成
统一映射 → 启用规则求值 → 同日同金额配对 → 两区划分 → 筛选 → 分区排序 → 分页，
避免多表 UNION 下复杂 SQL 与打标数据过期的一致性问题。

两区口径（TCY-23 设计 §2）：
  未被配对、未命中启用规则，方向=收入/支出 → 真实收支
  配对成功的银行侧渠道行 / 命中启用忽略规则 / 未命中的不计收支行 → 忽略区
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

# 银行渠道行候选（设计 §3.2）：BOC 中 tx_name 为「网上快捷支付 / 网上快捷退款」的行
_MIRROR_TX_NAMES = ("网上快捷支付", "网上快捷退款")

# 划转路径对端（设计 §4.1）：内置预设规则名 → 对端展示名；服务器常量，随预设维护，不落库。
# 「@counterparty」表示对端按行对方前缀推断（支付宝 / 财付通）。
TRANSFER_PATHS: Dict[str, str] = {
    "余额宝-转入转出": "银行卡（余额宝）",
    "零钱通-转入转出": "银行卡（零钱通）",
    "微信零钱-充值提现": "银行卡（零钱）",
    "支付宝余额-提现": "银行卡（余额）",
    "花呗还款-支付宝侧": "花呗（还款）",
    "花呗还款-银行侧": "支付宝（花呗还款）",
    "支付宝小荷包": "小荷包",
    "平台提现入账": "@counterparty",
    "基金/平台入账（蚂蚁）": "支付宝",
    "基金/平台入账（支付宝）": "支付宝",
    "基金/平台入账（财付通）": "微信",
    "同名账户互转": "本人其他账户",
}

# 划转标注中的本端名（设计 §4.1）：行来源 → 展示名（BOC 显示为「银行卡」）
TRANSFER_SELF: Dict[str, str] = {
    SOURCE_BOC: "银行卡",
    SOURCE_ALIPAY: "支付宝",
    SOURCE_WECHAT: "微信",
}


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


def _zone_of(row: dict, mirrored: Dict[int, str]) -> str:
    """两区划分（设计 §2）：镜像 / 命中启用规则 / 不计收支等未命中行 → 忽略区，
    其余按方向进真实收支区。"""
    if row["_id"] in mirrored or row["_hits"]:
        return "ignore"
    if row["direction"] in ("收入", "支出"):
        return "real"
    return "ignore"  # 不计收支（含微信中性交易映射）等未命中行，不污染真实收支


def _mark_of(row: dict, mirrored: Dict[int, str]) -> dict:
    """忽略区行标注（设计 §2，优先级：镜像 > 划转路径 > 不计收支）。"""
    platform = mirrored.get(row["_id"])
    if platform:
        label = "支付宝" if platform == SOURCE_ALIPAY else "微信"
        return {"mark": "mirror", "mark_label": f"镜像·{label}"}
    if row["_hits"]:
        names = [h["name"] for h in row["_hits"]]
        path = _transfer_path(row)
        return {"mark": "path", "mark_label": path or f"忽略（{names[0]}）", "rule_names": names}
    return {"mark": "neutral", "mark_label": "不计收支"}


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
    return {k: v for k, v in row.items() if k not in ("_id", "_hits", "_zone", "_mark")}


def _ignore_public(row: dict) -> dict:
    """忽略区行对外字段：统一字段 + 标注（镜像 / 划转路径 / 不计收支）。"""
    public = _public(row)
    public.update(row["_mark"])
    return public


def pair_mirrors(rows: List[dict]) -> Dict[int, str]:
    """同日同渠道同金额逐笔配对（设计 §3.2，独立算法，默认开启、无开关）。

    候选 = BOC 中 tx_name 为「网上快捷支付 / 网上快捷退款」的渠道行；平台侧 = 全部
    支付宝 / 微信行（不限方向）。渠道按 BOC 行 counterparty 前缀判定（「支付宝」→
    支付宝、「财付通」→ 微信，其余无渠道分组、不参与）。按（日期 × 渠道）分组，
    组内同金额按时间升序一对一配对（金额唯一时即直接配对）。
    返回 {银行行 _id: 平台来源}：银行行进忽略区标镜像，平台行不动（主记录）。
    """
    banks: List[Tuple[dict, str]] = []
    for row in rows:
        if row["source"] == SOURCE_BOC and row["raw"].get("tx_name", "") in _MIRROR_TX_NAMES:
            counterparty = row["counterparty"] or ""
            channel = None
            if counterparty.startswith("支付宝"):
                channel = SOURCE_ALIPAY
            elif counterparty.startswith("财付通"):
                channel = SOURCE_WECHAT
            if channel:
                banks.append((row, channel))
    bank_buckets: Dict[Tuple[str, str], List[dict]] = {}
    for row, channel in banks:
        bank_buckets.setdefault((row["date"], channel), []).append(row)
    platform_buckets: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        if row["source"] in (SOURCE_ALIPAY, SOURCE_WECHAT):
            platform_buckets.setdefault((row["date"], row["source"]), []).append(row)
    mirrored: Dict[int, str] = {}
    for (_date, channel), bank_rows in bank_buckets.items():
        platform_rows = platform_buckets.get((_date, channel), [])
        if not platform_rows:
            continue
        bank_rows.sort(key=lambda r: r["time"] or "")
        platform_rows.sort(key=lambda r: r["time"] or "")
        plats_by_amount: Dict[float, List[dict]] = {}
        for p in platform_rows:
            plats_by_amount.setdefault(abs(_amount(p)), []).append(p)
        for bank in bank_rows:
            queue = plats_by_amount.get(abs(_amount(bank)))
            if not queue:
                continue  # 金额对不上 → 未配对（按 DP2 留真实收支区）
            platform = queue.pop(0)  # 时间升序一一对应
            mirrored[bank["_id"]] = platform["source"]
    return mirrored


def _transfer_path(row: dict) -> str:
    """内置规则命中行的划转路径标注（设计 §4.1）：「对端 + 行方向 + 行来源」组合。

    收入 = 对端 → 本端；支出 = 本端 → 对端；其余（不计收支）= 本端 ↔ 对端。
    规则名不在 TRANSFER_PATHS（自定义规则）时返回空串（标注「忽略（规则名）」）。
    """
    name = next((h["name"] for h in row["_hits"] if h["name"] in TRANSFER_PATHS), None)
    if name is None:
        return ""
    peer = TRANSFER_PATHS[name]
    if peer == "@counterparty":
        counterparty = row["counterparty"] or ""
        if counterparty.startswith("支付宝"):
            peer = "支付宝"
        elif counterparty.startswith("财付通"):
            peer = "微信"
        else:
            peer = "支付平台"
    self_name = TRANSFER_SELF[row["source"]]
    if row["direction"] == "收入":
        return f"{peer} → {self_name}"
    if row["direction"] == "支出":
        return f"{self_name} → {peer}"
    return f"{self_name} ↔ {peer}"


def _zone_rows(conn, selected, **filters) -> Tuple[List[dict], List[dict]]:
    """取回三源并返回两区行列表（real, ignore）。

    配对与分区身份在全量数据上计算（设计 §3.1）：筛选（含来源多选）只决定显示，
    边界行身份不随筛选变化。收/支筛选统一作用于两区（忽略区按行方向过滤）。
    """
    base = fetch_rows(conn, SOURCES)
    rules = [r for r in db.list_rules(conn) if r["enabled"]]
    apply_rules(conn, base, rules)
    mirrored = pair_mirrors(base)
    for row in base:
        row["_zone"] = _zone_of(row, mirrored)
        row["_mark"] = _mark_of(row, mirrored)
    visible = [r for r in base if r["source"] in selected]
    visible = filter_rows(visible, **filters)
    real = [r for r in visible if r["_zone"] == "real"]
    ignore = [r for r in visible if r["_zone"] == "ignore"]
    return real, ignore


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
    real_page: int = 1,
    ignore_page: int = 1,
    page_size: int = db._DEFAULT_PAGE_SIZE,
) -> dict:
    """总账户明细查询：统一映射 + 规则求值 + 配对 → 两区结构 + 各区独立按行分页。"""
    if page_size not in db._PAGE_SIZES:
        page_size = db._DEFAULT_PAGE_SIZE
    if sort not in _TOTAL_SORT_KEYS:
        sort = "datetime"
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    real, ignore = _zone_rows(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )
    sort_rows(real, sort, order)
    sort_rows(ignore, sort, order)

    def page_of(rows: List[dict], page: int, public) -> dict:
        page = max(page, 1)
        offset = (page - 1) * page_size
        return {
            "total": len(rows), "page": page, "page_size": page_size,
            "rows": [public(r) for r in rows[offset : offset + page_size]],
        }

    return {
        "real": page_of(real, real_page, _public),
        "ignore": page_of(ignore, ignore_page, _ignore_public),
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
    """总账户汇总（真实口径，设计 §2.3）：真实收入 / 真实支出 / 净收支 / 真实笔数，
    忽略区返回笔数与细分（镜像 / 划转 / 不计收支，不计入真实收支）。"""
    selected = [s for s in (sources if sources is not None else SOURCES) if s in SOURCE_CONFIGS]
    real, ignore = _zone_rows(
        conn, selected,
        q=q, date_from=date_from, date_to=date_to, directions=directions,
        amount_min=amount_min, amount_max=amount_max,
    )

    def agg(rows: List[dict]) -> dict:
        return {"count": len(rows), "sum": round(sum(_amount(r) for r in rows), 2)}

    income = [r for r in real if r["direction"] == "收入"]
    expense = [r for r in real if r["direction"] == "支出"]
    income_agg, expense_agg = agg(income), agg(expense)
    marks = [r["_mark"]["mark"] for r in ignore]
    return {
        "income": income_agg,
        "expense": expense_agg,
        "net": round(income_agg["sum"] - expense_agg["sum"], 2),
        "count": income_agg["count"] + expense_agg["count"],
        "ignore": {
            "count": len(ignore),
            "mirror": marks.count("mirror"),
            "transfer": marks.count("path"),
            "neutral": marks.count("neutral"),
        },
    }
