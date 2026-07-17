"""SQLite 本地存储 — 交易去重 + 汇总查询"""

import logging
import sqlite3
import os
from typing import Dict, List, Set

from paycheck.core.constants import (
    FIELD_PLATFORM, FIELD_TIME, FIELD_CATEGORY, FIELD_COUNTERPARTY,
    FIELD_DESCRIPTION, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_PAYMENT_METHOD,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK, FIELD_ID,
)

log = logging.getLogger("paycheck.database")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "log", "paycheck.db")

CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS transactions (
    {FIELD_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
    {FIELD_PLATFORM} TEXT NOT NULL,
    {FIELD_TIME} TEXT NOT NULL,
    {FIELD_CATEGORY} TEXT DEFAULT '',
    {FIELD_COUNTERPARTY} TEXT DEFAULT '',
    {FIELD_AMOUNT} REAL NOT NULL,
    {FIELD_TX_TYPE} TEXT DEFAULT '',
    {FIELD_PAYMENT_METHOD} TEXT DEFAULT '',
    {FIELD_DESCRIPTION} TEXT DEFAULT '',
    {FIELD_BALANCE} REAL DEFAULT 0,
    {FIELD_CURRENCY} TEXT DEFAULT '',
    {FIELD_BRANCH} TEXT DEFAULT '',
    {FIELD_CP_ACCOUNT} TEXT DEFAULT '',
    {FIELD_CP_BANK} TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE({FIELD_TIME}, {FIELD_AMOUNT}, {FIELD_COUNTERPARTY})
);
"""

CREATE_TAGS = """
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_TRANSACTION_TAGS = """
CREATE TABLE IF NOT EXISTS transaction_tags (
    transaction_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (transaction_id, tag_id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
"""

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_TAGS)
    conn.execute(CREATE_TRANSACTION_TAGS)
    conn.execute(CREATE_SETTINGS)
    return conn


def insert_transactions(transactions: List[Dict], path: str = DB_PATH) -> int:
    """批量插入交易，自动跳过重复（时间+金额+对方相同），返回新增条数"""
    if not transactions:
        return 0

    log.info("插入交易: %d 条", len(transactions))
    conn = _connect(path)
    added = 0
    for t in transactions:
        try:
            conn.execute(f"""
                INSERT OR IGNORE INTO transactions
                ({FIELD_PLATFORM}, {FIELD_TIME}, {FIELD_CATEGORY}, {FIELD_COUNTERPARTY}, {FIELD_AMOUNT}, {FIELD_TX_TYPE},
                 {FIELD_PAYMENT_METHOD}, {FIELD_DESCRIPTION}, {FIELD_BALANCE}, {FIELD_CURRENCY}, {FIELD_BRANCH},
                 {FIELD_CP_ACCOUNT}, {FIELD_CP_BANK})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get(FIELD_PLATFORM, ""),
                t.get(FIELD_TIME, ""),
                t.get(FIELD_CATEGORY, ""),
                t.get(FIELD_COUNTERPARTY, ""),
                t.get(FIELD_AMOUNT, 0),
                t.get(FIELD_TX_TYPE, ""),
                t.get(FIELD_PAYMENT_METHOD, ""),
                t.get(FIELD_DESCRIPTION, ""),
                t.get(FIELD_BALANCE, 0),
                t.get(FIELD_CURRENCY, ""),
                t.get(FIELD_BRANCH, ""),
                t.get(FIELD_CP_ACCOUNT, ""),
                t.get(FIELD_CP_BANK, ""),
            ))
            if conn.total_changes > added:
                added += 1
        except Exception as e:
            log.warning("插入交易失败: %s", e)
            continue

    conn.commit()
    log.info("插入完成: 新增%d, 跳过%d", added, len(transactions) - added)
    conn.close()
    return added


def get_all_transactions(path: str = DB_PATH) -> List[Dict]:
    """获取所有交易记录"""
    log.debug("查询所有交易")
    conn = _connect(path)
    rows = conn.execute(f"""
        SELECT {FIELD_ID}, {FIELD_PLATFORM}, {FIELD_TIME}, {FIELD_CATEGORY}, {FIELD_COUNTERPARTY}, {FIELD_AMOUNT}, {FIELD_TX_TYPE},
               {FIELD_PAYMENT_METHOD}, {FIELD_DESCRIPTION}, {FIELD_BALANCE}, {FIELD_CURRENCY},
               {FIELD_BRANCH}, {FIELD_CP_ACCOUNT}, {FIELD_CP_BANK}
        FROM transactions ORDER BY {FIELD_TIME} DESC
    """).fetchall()
    conn.close()

    log.debug("查询到 %d 条交易", len(rows))

    return [
        {
            FIELD_ID: r[0],
            FIELD_PLATFORM: r[1], FIELD_TIME: r[2], FIELD_CATEGORY: r[3],
            FIELD_COUNTERPARTY: r[4], FIELD_AMOUNT: r[5], FIELD_TX_TYPE: r[6],
            FIELD_PAYMENT_METHOD: r[7], FIELD_DESCRIPTION: r[8],
            FIELD_BALANCE: r[9], FIELD_CURRENCY: r[10], FIELD_BRANCH: r[11],
            FIELD_CP_ACCOUNT: r[12], FIELD_CP_BANK: r[13],
        }
        for r in rows
    ]


def get_summary(path: str = DB_PATH) -> Dict:
    """直接从 SQLite 计算汇总统计"""
    log.debug("查询汇总统计")
    conn = _connect(path)

    row = conn.execute(f"""
        SELECT
            COALESCE(SUM(CASE WHEN {FIELD_TX_TYPE} = '支出' THEN {FIELD_AMOUNT} ELSE 0 END), 0) AS total_expense,
            COALESCE(SUM(CASE WHEN {FIELD_TX_TYPE} = '收入' THEN {FIELD_AMOUNT} ELSE 0 END), 0) AS total_income,
            COUNT(CASE WHEN {FIELD_TX_TYPE} = '支出' THEN 1 END) AS total_count,
            COALESCE(SUM(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'wechat' THEN {FIELD_AMOUNT} ELSE 0 END), 0) AS wechat_total,
            COALESCE(SUM(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'alipay' THEN {FIELD_AMOUNT} ELSE 0 END), 0) AS alipay_total,
            COALESCE(SUM(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'bank' THEN {FIELD_AMOUNT} ELSE 0 END), 0) AS bank_total,
            COUNT(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'wechat' THEN 1 END) AS wechat_count,
            COUNT(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'alipay' THEN 1 END) AS alipay_count,
            COUNT(CASE WHEN {FIELD_TX_TYPE} = '支出' AND {FIELD_PLATFORM} = 'bank' THEN 1 END) AS bank_count
        FROM transactions
    """).fetchone()

    month_row = conn.execute(
        f"SELECT COUNT(DISTINCT substr({FIELD_TIME}, 1, 7)) FROM transactions WHERE {FIELD_TX_TYPE} = '支出'"
    ).fetchone()

    conn.close()

    months = month_row[0] if month_row else 0
    total_expense = row[0] or 0
    total_income = row[1] or 0
    total_count = row[2] or 0
    monthly_avg = round(total_expense / months, 2) if months > 0 else 0

    log.debug("汇总: 支出¥%.2f, 收入¥%.2f, 共%d条", total_expense, total_income, total_count)

    return {
        "total_expense": total_expense,
        "total_income": total_income,
        "total_count": total_count,
        "monthly_avg": monthly_avg,
        "wechat_total": row[3] or 0,
        "alipay_total": row[4] or 0,
        "bank_total": row[5] or 0,
        "wechat_count": row[6] or 0,
        "alipay_count": row[7] or 0,
        "bank_count": row[8] or 0,
    }


def get_all_tags(path: str = DB_PATH) -> List[Dict]:
    """获取所有标签及其使用次数（较慢，含 COUNT）"""
    log.debug("查询所有标签")
    conn = _connect(path)
    rows = conn.execute("""
        SELECT t.id, t.name, COUNT(tt.transaction_id) as count
        FROM tags t
        LEFT JOIN transaction_tags tt ON t.id = tt.tag_id
        GROUP BY t.id
        ORDER BY count DESC
    """).fetchall()
    conn.close()

    log.debug("查询到 %d 个标签", len(rows))
    return [
        {"id": r[0], "name": r[1], "count": r[2]}
        for r in rows
    ]


def get_tag_list(path: str = DB_PATH) -> List[Dict]:
    """获取所有标签（仅 id + name，无统计）"""
    conn = _connect(path)
    rows = conn.execute(
        "SELECT id, name FROM tags ORDER BY name"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]


def create_tag(name: str, path: str = DB_PATH) -> int:
    """创建新标签，返回标签ID"""
    log.info("创建标签: %s", name)
    conn = _connect(path)
    cursor = conn.execute(
        "INSERT INTO tags(name) VALUES (?)",
        (name,)
    )
    conn.commit()
    tag_id = cursor.lastrowid
    conn.close()
    log.debug("标签创建成功: id=%s", tag_id)
    return tag_id


def rename_tag(tag_id: int, new_name: str, path: str = DB_PATH) -> None:
    """重命名标签"""
    log.info("重命名标签: %d -> %s", tag_id, new_name)
    conn = _connect(path)
    conn.execute(
        "UPDATE tags SET name = ? WHERE id = ?",
        (new_name, tag_id)
    )
    conn.commit()
    conn.close()


def delete_tag(tag_id: int, path: str = DB_PATH) -> None:
    """删除标签及其所有关联"""
    log.info("删除标签: %d", tag_id)
    conn = _connect(path)
    conn.execute(
        "DELETE FROM transaction_tags WHERE tag_id = ?",
        (tag_id,)
    )
    conn.execute(
        "DELETE FROM tags WHERE id = ?",
        (tag_id,)
    )
    conn.commit()
    conn.close()


def merge_tags(source_id: int, target_id: int, path: str = DB_PATH) -> None:
    """合并标签：将source_id的所有交易转移到target_id，然后删除source"""
    log.info("合并标签: %d -> %d", source_id, target_id)
    conn = _connect(path)
    conn.execute(
        "UPDATE OR IGNORE transaction_tags SET tag_id = ? WHERE tag_id = ?",
        (target_id, source_id)
    )
    conn.execute(
        "DELETE FROM transaction_tags WHERE tag_id = ?",
        (source_id,)
    )
    conn.execute(
        "DELETE FROM tags WHERE id = ?",
        (source_id,)
    )
    conn.commit()
    conn.close()


def set_transaction_tags(tx_id: int, tag_ids: List[int], path: str = DB_PATH) -> None:
    """设置单条交易的标签（先清空再批量设置）"""
    log.debug("设置交易标签: tx=%d, tags=%s", tx_id, tag_ids)
    conn = _connect(path)
    conn.execute(
        "DELETE FROM transaction_tags WHERE transaction_id = ?",
        (tx_id,)
    )
    for tag_id in tag_ids:
        conn.execute(
            "INSERT INTO transaction_tags(transaction_id, tag_id) VALUES (?, ?)",
            (tx_id, tag_id)
        )
    conn.commit()
    conn.close()


def batch_set_tags(tx_ids: List[int], tag_ids: List[int], path: str = DB_PATH) -> None:
    """批量设置多条交易的标签（在同一事务中）"""
    log.info("批量设置标签: %d 笔交易, %d 个标签", len(tx_ids), len(tag_ids))
    conn = _connect(path)
    for tx_id in tx_ids:
        conn.execute(
            "DELETE FROM transaction_tags WHERE transaction_id = ?",
            (tx_id,)
        )
        for tag_id in tag_ids:
            conn.execute(
                "INSERT INTO transaction_tags(transaction_id, tag_id) VALUES (?, ?)",
                (tx_id, tag_id)
            )
    conn.commit()
    conn.close()


def get_transaction_tags(tx_id: int, path: str = DB_PATH) -> List[Dict]:
    """获取单条交易的所有标签"""
    log.debug("查询交易标签: tx=%d", tx_id)
    conn = _connect(path)
    rows = conn.execute("""
        SELECT t.id, t.name
        FROM tags t
        JOIN transaction_tags tt ON t.id = tt.tag_id
        WHERE tt.transaction_id = ?
    """, (tx_id,)).fetchall()
    conn.close()

    return [
        {"id": r[0], "name": r[1]}
        for r in rows
    ]


def get_transaction_tags_batch(tx_ids: List[int], path: str = DB_PATH) -> Dict[int, Set[int]]:
    """批量查询多条交易的标签，返回 {tx_id: {tag_id, ...}}"""
    if not tx_ids:
        return {}
    conn = _connect(path)
    placeholders = ",".join("?" for _ in tx_ids)
    rows = conn.execute(
        f"SELECT transaction_id, tag_id FROM transaction_tags WHERE transaction_id IN ({placeholders})",
        tuple(tx_ids)
    ).fetchall()
    conn.close()
    result: Dict[int, Set[int]] = {tx_id: set() for tx_id in tx_ids}
    for tx_id, tag_id in rows:
        result[tx_id].add(tag_id)
    return result


def query_by_tag_ids(tag_ids: List[int], path: str = DB_PATH) -> List[int]:
    """查询包含任一指定标签的交易ID列表"""
    if not tag_ids:
        return []

    log.debug("按标签查询交易: %s", tag_ids)
    conn = _connect(path)
    placeholders = ",".join("?" for _ in tag_ids)
    rows = conn.execute(
        f"SELECT DISTINCT transaction_id FROM transaction_tags WHERE tag_id IN ({placeholders})",
        tuple(tag_ids)
    ).fetchall()
    conn.close()

    result = [r[0] for r in rows]
    log.debug("查询到 %d 条交易", len(result))
    return result


def get_transactions_by_ids(tx_ids: List[int], path: str = DB_PATH) -> List[Dict]:
    """根据ID列表获取交易详情"""
    if not tx_ids:
        return []

    log.debug("按ID查询交易: %d 个ID", len(tx_ids))
    conn = _connect(path)
    placeholders = ",".join("?" for _ in tx_ids)
    rows = conn.execute(
        f"SELECT {FIELD_ID}, {FIELD_PLATFORM}, {FIELD_TIME}, {FIELD_CATEGORY}, {FIELD_COUNTERPARTY}, {FIELD_AMOUNT}, {FIELD_TX_TYPE}, "
        f"{FIELD_PAYMENT_METHOD}, {FIELD_DESCRIPTION}, {FIELD_BALANCE}, {FIELD_CURRENCY}, {FIELD_BRANCH}, {FIELD_CP_ACCOUNT}, {FIELD_CP_BANK} "
        f"FROM transactions WHERE {FIELD_ID} IN ({placeholders}) ORDER BY {FIELD_TIME} DESC",
        tuple(tx_ids)
    ).fetchall()
    conn.close()

    log.debug("查询到 %d 条交易", len(rows))
    return [
        {
            FIELD_ID: r[0],
            FIELD_PLATFORM: r[1], FIELD_TIME: r[2], FIELD_CATEGORY: r[3],
            FIELD_COUNTERPARTY: r[4], FIELD_AMOUNT: r[5], FIELD_TX_TYPE: r[6],
            FIELD_PAYMENT_METHOD: r[7], FIELD_DESCRIPTION: r[8],
            FIELD_BALANCE: r[9], FIELD_CURRENCY: r[10], FIELD_BRANCH: r[11],
            FIELD_CP_ACCOUNT: r[12], FIELD_CP_BANK: r[13],
        }
        for r in rows
    ]


# ── 设置持久化 ──

def get_setting(key: str, default: str = "", path: str = DB_PATH) -> str:
    """读取设置值"""
    conn = _connect(path)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str, path: str = DB_PATH) -> None:
    """写入设置值"""
    conn = _connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()
