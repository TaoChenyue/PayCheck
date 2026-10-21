"""SQLite 存储层：三源明细表、去重导入、筛选查询、汇总、内部转账规则

表结构（设计 3.4）：
  <source>_transactions
    id            INTEGER PRIMARY KEY AUTOINCREMENT
    ...源明细列全部保留原样（TEXT）...
    source_file   TEXT
    imported_at   TEXT
    dedup_key     TEXT UNIQUE   -- 去重键（设计 4.3）
  transfer_rules（内部转账规则，设计 3.5）
    id / name / source / conditions(JSON) / action / enabled / preset_id / created_at / updated_at
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from paycheck_workbench.parsing import ParseResult
from paycheck_workbench.rules import conditions_sql, rule_key
from paycheck_workbench.sources import (
    SORT_COLUMNS,
    SOURCE_CONFIGS,
    SOURCES,
    SourceConfig,
    dedup_key,
)

DEFAULT_DB_PATH = Path("paycheck.db")  # 相对启动时的工作目录

_PAGE_SIZES = (10, 50, 100, 200)
_DEFAULT_PAGE_SIZE = 50


class DataError(Exception):
    """存储层错误（表缺失、参数非法等）"""


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _create_table(conn: sqlite3.Connection, cfg: SourceConfig) -> None:
    cols = ", ".join(f'"{c}" TEXT' for c in cfg.columns)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{cfg.table}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {cols},
            source_file TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            dedup_key TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.commit()


def _create_rules_table(conn: sqlite3.Connection) -> None:
    """内部转账规则表（设计 3.5），幂等。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transfer_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            conditions TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'fold',
            enabled INTEGER NOT NULL DEFAULT 1,
            preset_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def init_db(db_path) -> None:
    """建库建表（幂等）。库文件目录不存在时自动创建。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        for source in SOURCES:
            _create_table(conn, SOURCE_CONFIGS[source])
        _create_rules_table(conn)


def source_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts = {}
    for source in SOURCES:
        try:
            row = conn.execute(
                f'SELECT COUNT(*) AS n FROM "{SOURCE_CONFIGS[source].table}"'
            ).fetchone()
            counts[source] = row["n"] if row else 0
        except sqlite3.OperationalError:
            counts[source] = 0  # 表尚未创建
    return counts


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------

def existing_dedup_keys(conn: sqlite3.Connection, source: str) -> set:
    """表中已有去重键集合（本地单用户库，规模可控，全量取出用于预览比对）。"""
    table = SOURCE_CONFIGS[source].table
    try:
        rows = conn.execute(f'SELECT dedup_key FROM "{table}"').fetchall()
    except sqlite3.OperationalError as exc:
        raise DataError(f"数据表 {table} 不存在，请先初始化") from exc
    return {r["dedup_key"] for r in rows}


def import_parse_result(
    conn: sqlite3.Connection, source: str, parsed: ParseResult, file_name: str
) -> dict:
    """按去重键写入明细（幂等）。返回 {inserted, skipped, failed, failures}。

    - 重复键（含同文件内重复与库内已有）→ skipped
    - 解析层报错的行 → failed（附行号与原因）
    - 去重键为空的异常行 → failed
    """
    cfg = SOURCE_CONFIGS[source]
    table = cfg.table
    columns = cfg.columns
    existing = existing_dedup_keys(conn, source)
    seen: set = set()

    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join('"{}"'.format(c) for c in columns)
    sql = f'INSERT OR IGNORE INTO "{table}" ({column_sql}, source_file, imported_at, dedup_key) VALUES ({placeholders}, ?, ?, ?)'

    inserted = skipped = 0
    failures: List[dict] = []
    with conn:
        for row in parsed.rows:
            values = dict(zip(columns, row.values))
            key = dedup_key(source, values)
            if not key:
                failures.append({"row": row.row_number, "reason": "去重键为空（缺少订单号与时间/金额/对方）"})
                continue
            if key in existing or key in seen:
                skipped += 1
                continue
            seen.add(key)
            cur = conn.execute(sql, [*row.values, file_name, imported_at, key])
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
    for err in parsed.errors:
        failures.append({"row": err["row"], "reason": err["reason"]})
    return {"inserted": inserted, "skipped": skipped, "failed": len(failures), "failures": failures}


# ---------------------------------------------------------------------------
# 筛选 / 查询 / 汇总
# ---------------------------------------------------------------------------

def _like_pattern(text: str) -> str:
    """转义 LIKE 通配符后包 %。"""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _date_expr(cfg: SourceConfig) -> str:
    """日期范围比较用的 SQL 表达式（BOC 用 date 列，其余用时间列前 10 位）。"""
    if cfg.time_col:
        return f'"{cfg.date_col}"'
    return f'substr("{cfg.date_col}", 1, 10)'


def _build_where(
    cfg: SourceConfig,
    *,
    q: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    directions: Optional[List[str]],
    categories: Optional[List[str]],
    amount_min: Optional[float],
    amount_max: Optional[float],
) -> Tuple[str, List]:
    clauses: List[str] = []
    params: List = []

    if q:
        search = " OR ".join(
            f'"{c}" LIKE ? ESCAPE "\\"' for c in cfg.search_cols
        )
        clauses.append(f"({search})")
        pattern = _like_pattern(q)
        params.extend([pattern] * len(cfg.search_cols))

    if date_from:
        clauses.append(f"{_date_expr(cfg)} >= ?")
        params.append(date_from)
    if date_to:
        clauses.append(f"{_date_expr(cfg)} <= ?")
        params.append(date_to)

    if directions:
        marks = ", ".join("?" for _ in directions)
        clauses.append(f'"{cfg.direction_col}" IN ({marks})')
        params.extend(directions)

    if categories:
        marks = ", ".join("?" for _ in categories)
        clauses.append(f'"{cfg.category_col}" IN ({marks})')
        params.extend(categories)

    if amount_min is not None:
        clauses.append(f'CAST("{cfg.amount_col}" AS REAL) >= ?')
        params.append(amount_min)
    if amount_max is not None:
        clauses.append(f'CAST("{cfg.amount_col}" AS REAL) <= ?')
        params.append(amount_max)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def query_rows(
    conn: sqlite3.Connection,
    source: str,
    *,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    sort: str = "datetime",
    order: str = "desc",
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    directions: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
) -> dict:
    """筛选 + 排序 + 分页查询。默认按时间倒序（设计 3.5）。"""
    cfg = SOURCE_CONFIGS[source]
    table = cfg.table
    if page_size not in _PAGE_SIZES:
        page_size = _DEFAULT_PAGE_SIZE
    if sort not in SORT_COLUMNS[source]:
        sort = "datetime"
    order_sql = "DESC" if order != "asc" else "ASC"

    where, params = _build_where(
        cfg,
        q=q,
        date_from=date_from,
        date_to=date_to,
        directions=directions,
        categories=categories,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    count_row = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"{where}', params).fetchone()
    total = count_row["n"] if count_row else 0

    sort_cols = SORT_COLUMNS[source][sort]
    if sort == "amount":
        # 金额为文本列，按数值排序
        order_expr = f'CAST("{sort_cols}" AS REAL) {order_sql}'
    else:
        order_expr = ", ".join(f'"{c}" {order_sql}' for c in sort_cols.split(", "))

    offset = (max(page, 1) - 1) * page_size
    rows = conn.execute(
        f'SELECT * FROM "{table}"{where} ORDER BY {order_expr} LIMIT ? OFFSET ?',
        [*params, page_size, offset],
    ).fetchall()
    return {"total": total, "page": page, "page_size": page_size, "rows": [dict(r) for r in rows]}


def query_summary(
    conn: sqlite3.Connection,
    source: str,
    *,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    directions: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
) -> dict:
    """汇总卡片数据：收入/支出/(不计收支)合计、笔数、期末余额（仅 BOC）。"""
    cfg = SOURCE_CONFIGS[source]
    table = cfg.table
    where, params = _build_where(
        cfg,
        q=q,
        date_from=date_from,
        date_to=date_to,
        directions=directions,
        categories=categories,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    amount_expr = f'CAST("{cfg.amount_col}" AS REAL)'
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN "{cfg.direction_col}" = '收入' THEN {amount_expr} END) AS income_sum,
               SUM(CASE WHEN "{cfg.direction_col}" = '支出' THEN {amount_expr} END) AS expense_sum,
               SUM(CASE WHEN "{cfg.direction_col}" = ? THEN {amount_expr} END) AS neutral_sum
        FROM "{table}"{where}
        """,
        [cfg.neutral_direction or "__none__", *params],
    ).fetchone()

    summary: dict = {
        "count": row["n"] or 0,
        "income_sum": round(row["income_sum"] or 0, 2),
        "expense_sum": round(row["expense_sum"] or 0, 2),
    }
    if cfg.has_neutral_card:
        summary["neutral_sum"] = round(row["neutral_sum"] or 0, 2)

    if cfg.balance_col:
        # BOC 期末余额：筛选范围内最后一笔（设计 2 汇总卡片）
        balance_where = (
            f'{where} AND "{cfg.balance_col}" != \'\''
            if where
            else f'WHERE "{cfg.balance_col}" != \'\''
        )
        balance_row = conn.execute(
            f"""
            SELECT "{cfg.balance_col}" AS b FROM "{table}"{balance_where}
            ORDER BY "date" DESC, "time" DESC LIMIT 1
            """,
            params,
        ).fetchone()
        summary["last_balance"] = balance_row["b"] if balance_row else ""
    return summary


def distinct_categories(conn: sqlite3.Connection, source: str) -> List[str]:
    """分类多选的可选项（BOC: 渠道；支付宝: 交易分类；微信: 交易类型）。"""
    cfg = SOURCE_CONFIGS[source]
    col = cfg.category_col
    rows = conn.execute(
        f'SELECT DISTINCT "{col}" AS v FROM "{cfg.table}" WHERE "{col}" != "" ORDER BY "{col}"'
    ).fetchall()
    return [r["v"] for r in rows]


# ---------------------------------------------------------------------------
# 内部转账规则（transfer_rules）
# ---------------------------------------------------------------------------

def _rule_dict(row: sqlite3.Row) -> dict:
    rule = dict(row)
    rule["conditions"] = json.loads(rule["conditions"])
    rule["enabled"] = bool(rule["enabled"])
    return rule


def list_rules(conn: sqlite3.Connection) -> List[dict]:
    """全部规则（按源、名称排序）。"""
    rows = conn.execute("SELECT * FROM transfer_rules ORDER BY source, name, id").fetchall()
    return [_rule_dict(r) for r in rows]


def get_rule(conn: sqlite3.Connection, rule_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM transfer_rules WHERE id = ?", [rule_id]).fetchone()
    return _rule_dict(row) if row else None


def save_rule(conn: sqlite3.Connection, rule: dict, rule_id: Optional[int] = None) -> dict:
    """新建或整体更新规则（更新含启停开关）。返回落库后的规则。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if rule_id is None:
        cur = conn.execute(
            """
            INSERT INTO transfer_rules (name, source, conditions, action, enabled, preset_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                rule["name"], rule["source"], json.dumps(rule["conditions"], ensure_ascii=False),
                rule["action"], int(bool(rule.get("enabled", True))), rule.get("preset_id"), now, now,
            ],
        )
        rule_id = cur.lastrowid
    else:
        existing = get_rule(conn, rule_id)
        preset_id = existing["preset_id"] if existing and "preset_id" not in rule else rule.get("preset_id")
        conn.execute(
            """
            UPDATE transfer_rules
            SET name = ?, source = ?, conditions = ?, action = ?, enabled = ?, preset_id = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                rule["name"], rule["source"], json.dumps(rule["conditions"], ensure_ascii=False),
                rule["action"], int(bool(rule.get("enabled", True))), preset_id, now, rule_id,
            ],
        )
    conn.commit()
    return get_rule(conn, rule_id)


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    conn.execute("DELETE FROM transfer_rules WHERE id = ?", [rule_id])
    conn.commit()


def find_duplicate_rule(conn: sqlite3.Connection, name: str, conditions: List[dict]) -> Optional[dict]:
    """同名且同条件（AND 顺序无关）的既有规则；预设导入时用于跳过。"""
    key = rule_key(conditions)
    for rule in list_rules(conn):
        if rule["name"] == name and rule_key(rule["conditions"]) == key:
            return rule
    return None


def count_rule_hits(conn: sqlite3.Connection, rule: dict) -> int:
    """规则在当前库中的命中笔数（查询时求值，不落库打标，设计 §3.6）。"""
    cfg = SOURCE_CONFIGS[rule["source"]]
    where, params = conditions_sql(rule["conditions"])
    row = conn.execute(f'SELECT COUNT(*) AS n FROM "{cfg.table}"{where}', params).fetchone()
    return row["n"] if row else 0


def rule_match_ids(conn: sqlite3.Connection, rule: dict) -> set:
    """规则命中的明细行 id 集合（总账户视图逐行打标用）。"""
    cfg = SOURCE_CONFIGS[rule["source"]]
    where, params = conditions_sql(rule["conditions"])
    rows = conn.execute(f'SELECT id FROM "{cfg.table}"{where}', params).fetchall()
    return {r["id"] for r in rows}
