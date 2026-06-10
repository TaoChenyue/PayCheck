"""SQLite 本地存储 — 交易去重 + 汇总查询"""

import logging
import sqlite3
import os
from typing import List, Dict

log = logging.getLogger("paycheck.database")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "log", "paycheck.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    time TEXT NOT NULL,
    category TEXT DEFAULT '',
    counterparty TEXT DEFAULT '',
    amount REAL NOT NULL,
    tx_type TEXT DEFAULT '',
    payment_method TEXT DEFAULT '',
    description TEXT DEFAULT '',
    balance REAL DEFAULT 0,
    currency TEXT DEFAULT '',
    branch TEXT DEFAULT '',
    cp_account TEXT DEFAULT '',
    cp_bank TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(time, amount, counterparty)
);
"""


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(CREATE_TABLE)
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
            conn.execute("""
                INSERT OR IGNORE INTO transactions
                (platform, time, category, counterparty, amount, tx_type,
                 payment_method, description, balance, currency, branch,
                 cp_account, cp_bank)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("platform", ""),
                t.get("time", ""),
                t.get("category", ""),
                t.get("counterparty", ""),
                t.get("amount", 0),
                t.get("tx_type", ""),
                t.get("payment_method", ""),
                t.get("description", ""),
                t.get("balance", 0),
                t.get("currency", ""),
                t.get("branch", ""),
                t.get("cp_account", ""),
                t.get("cp_bank", ""),
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
    rows = conn.execute("""
        SELECT platform, time, category, counterparty, amount, tx_type,
               payment_method, description, balance, currency,
               branch, cp_account, cp_bank
        FROM transactions ORDER BY time DESC
    """).fetchall()
    conn.close()

    log.debug("查询到 %d 条交易", len(rows))

    return [
        {
            "platform": r[0], "time": r[1], "category": r[2],
            "counterparty": r[3], "amount": r[4], "tx_type": r[5],
            "payment_method": r[6], "description": r[7],
            "balance": r[8], "currency": r[9], "branch": r[10],
            "cp_account": r[11], "cp_bank": r[12],
        }
        for r in rows
    ]


def get_summary(path: str = DB_PATH) -> Dict:
    """直接从 SQLite 计算汇总统计"""
    log.debug("查询汇总统计")
    conn = _connect(path)

    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN tx_type = '支出' THEN amount ELSE 0 END), 0) AS total_expense,
            COALESCE(SUM(CASE WHEN tx_type = '收入' THEN amount ELSE 0 END), 0) AS total_income,
            COUNT(CASE WHEN tx_type = '支出' THEN 1 END) AS total_count,
            COALESCE(SUM(CASE WHEN tx_type = '支出' AND platform = 'wechat' THEN amount ELSE 0 END), 0) AS wechat_total,
            COALESCE(SUM(CASE WHEN tx_type = '支出' AND platform = 'alipay' THEN amount ELSE 0 END), 0) AS alipay_total,
            COALESCE(SUM(CASE WHEN tx_type = '支出' AND platform = 'bank' THEN amount ELSE 0 END), 0) AS bank_total,
            COUNT(CASE WHEN tx_type = '支出' AND platform = 'wechat' THEN 1 END) AS wechat_count,
            COUNT(CASE WHEN tx_type = '支出' AND platform = 'alipay' THEN 1 END) AS alipay_count,
            COUNT(CASE WHEN tx_type = '支出' AND platform = 'bank' THEN 1 END) AS bank_count
        FROM transactions
    """).fetchone()

    month_row = conn.execute(
        "SELECT COUNT(DISTINCT substr(time, 1, 7)) FROM transactions WHERE tx_type = '支出'"
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
