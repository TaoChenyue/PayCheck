"""存储层测试：建表、去重导入（幂等）、筛选查询、汇总"""

from __future__ import annotations

import sqlite3

import pytest

from paycheck_workbench import db
from paycheck_workbench.parsing import ParseResult, ParsedRow
from paycheck_workbench.sources import (
    ALIPAY_COLUMNS,
    BOC_COLUMNS,
    SOURCE_ALIPAY,
    SOURCE_BOC,
    SOURCE_WECHAT,
    WECHAT_COLUMNS,
)


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    connection = db.connect(db_path)
    yield connection
    connection.close()


def _parsed(source, columns, value_rows):
    return ParseResult(
        source=source,
        file_name="t.csv",
        columns=list(columns),
        rows=[ParsedRow(row_number=i + 1, values=list(v)) for i, v in enumerate(value_rows)],
    )


def _boc_rows():
    cols = BOC_COLUMNS
    base = {c: "" for c in cols}
    rows = []
    for i, (date, time_, tx_type, amount, balance) in enumerate([
        ("2024-08-01", "12:00:00", "支出", "8.43", "100.00"),
        ("2024-08-02", "09:30:00", "支出", "31.00", "69.00"),
        ("2024-08-03", "10:00:00", "收入", "1559.27", "1628.27"),
    ]):
        row = dict(base)
        row.update({"date": date, "time": time_, "tx_type": tx_type, "amount": amount,
                    "counterparty": f"对方{i}", "channel": "银企对接", "balance": balance,
                    "tx_name": "网上快捷支付", "memo": f"附言{i}"})
        rows.append([row[c] for c in cols])
    return rows


def _alipay_rows():
    cols = ALIPAY_COLUMNS
    base = {c: "" for c in cols}
    rows = []
    for i, (time_, kind, amount, category, order) in enumerate([
        ("2025-07-31 18:05:17", "支出", "27.00", "餐饮美食", "ORDER001"),
        ("2025-07-30 06:02:38", "不计收支", "5.22", "投资理财", "ORDER002"),
        ("2025-07-29 12:00:00", "收入", "100.00", "其他", "ORDER003"),
    ]):
        row = dict(base)
        row.update({"交易时间": time_, "收/支": kind, "金额": amount, "交易分类": category,
                    "交易对方": "对方", "交易订单号": order, "交易状态": "交易成功"})
        rows.append([row[c] for c in cols])
    return rows


def test_init_creates_three_tables(conn):
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"boc_transactions", "alipay_transactions", "wechat_transactions"} <= tables


def test_init_creates_override_and_tag_tables_without_rules(conn):
    """三张旁表建齐；transfer_rules 随规则体系废弃被迁移删除（TCY-27）。"""
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"total_overrides", "tag_groups", "row_tags"} <= tables
    assert "transfer_rules" not in tables


def test_init_drops_legacy_transfer_rules(conn):
    """旧库升级：既有 transfer_rules 表（含数据）在 init_db 时删除。"""
    conn.execute("CREATE TABLE transfer_rules (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO transfer_rules (name) VALUES ('旧规则')")
    conn.commit()
    db.init_db(conn.execute("PRAGMA database_list").fetchone()["file"])  # 同一库文件重跑 init_db
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "transfer_rules" not in tables
    assert {"total_overrides", "tag_groups", "row_tags"} <= tables


class TestOverridesTable:
    def test_set_fetch_upsert(self, conn):
        db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _boc_rows()), "b.csv")
        assert db.fetch_overrides(conn) == {}
        assert db.set_overrides(conn, [("boc", 1), ("boc", 2)], 0) == 2
        assert db.fetch_overrides(conn) == {"boc:1": 0, "boc:2": 0}
        # upsert：同键改写不新增行
        assert db.set_overrides(conn, [("boc", 1)], 1) == 1
        assert db.fetch_overrides(conn) == {"boc:1": 1, "boc:2": 0}
        assert conn.execute("SELECT COUNT(*) AS n FROM total_overrides").fetchone()["n"] == 2


class TestTagGroupsTable:
    def test_create_color_cycle(self, conn):
        first = db.create_tag_group(conn, "差旅")
        assert first["name"] == "差旅"
        assert first["color"] == db.TAG_COLORS[0]
        assert first["row_count"] == 0
        for name in ["餐饮", "购物"]:
            db.create_tag_group(conn, name)
        colors = [g["color"] for g in db.list_tag_groups(conn)]
        assert colors == db.TAG_COLORS[:3]

    def test_duplicate_name_rejected(self, conn):
        db.create_tag_group(conn, "差旅")
        with pytest.raises(db.DataError):
            db.create_tag_group(conn, "差旅")

    def test_rename(self, conn):
        group = db.create_tag_group(conn, "差旅")
        updated = db.update_tag_group(conn, group["id"], "出差")
        assert updated["name"] == "出差"
        assert db.update_tag_group(conn, 999, "x") is None
        db.create_tag_group(conn, "餐饮")
        with pytest.raises(db.DataError):
            db.update_tag_group(conn, group["id"], "餐饮")

    def test_delete_cascades_row_tags(self, conn):
        db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _boc_rows()), "b.csv")
        group = db.create_tag_group(conn, "差旅")
        db.apply_tags(conn, [("boc", 1), ("boc", 2)], [group["id"]], "add")
        assert db.list_tag_groups(conn)[0]["row_count"] == 2
        db.delete_tag_group(conn, group["id"])
        assert db.list_tag_groups(conn) == []
        assert db.fetch_row_tags(conn) == {}

    def test_apply_tags_add_idempotent_and_remove(self, conn):
        db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _boc_rows()), "b.csv")
        a = db.create_tag_group(conn, "A")
        b = db.create_tag_group(conn, "B")
        assert db.apply_tags(conn, [("boc", 1), ("boc", 2)], [a["id"], b["id"]], "add") == 2
        # 重复打幂等
        db.apply_tags(conn, [("boc", 1)], [a["id"]], "add")
        assert {k: len(v) for k, v in db.fetch_row_tags(conn).items()} == {"boc:1": 2, "boc:2": 2}
        assert db.apply_tags(conn, [("boc", 1)], [b["id"]], "remove") == 1
        assert {k: [t["name"] for t in v] for k, v in db.fetch_row_tags(conn).items()} == {
            "boc:1": ["A"], "boc:2": ["A", "B"]}


def test_boc_import_and_idempotent_reimport(conn):
    parsed = _parsed(SOURCE_BOC, BOC_COLUMNS, _boc_rows())
    first = db.import_parse_result(conn, SOURCE_BOC, parsed, "b.csv")
    assert first == {"inserted": 3, "skipped": 0, "failed": 0, "failures": []}
    second = db.import_parse_result(conn, SOURCE_BOC, parsed, "b.csv")
    assert second == {"inserted": 0, "skipped": 3, "failed": 0, "failures": []}
    assert db.source_counts(conn) == {SOURCE_BOC: 3, SOURCE_ALIPAY: 0, SOURCE_WECHAT: 0}
    # 元数据列
    row = conn.execute("SELECT source_file, imported_at, dedup_key FROM boc_transactions LIMIT 1").fetchone()
    assert row["source_file"] == "b.csv"
    assert row["imported_at"]
    assert row["dedup_key"] == "2024-08-01|12:00:00|8.43|对方0"


def test_in_file_duplicate_rows_skipped(conn):
    rows = _boc_rows()
    parsed = _parsed(SOURCE_BOC, BOC_COLUMNS, rows + [rows[0]])
    result = db.import_parse_result(conn, SOURCE_BOC, parsed, "b.csv")
    assert result["inserted"] == 3
    assert result["skipped"] == 1


def test_empty_dedup_key_row_failed(conn):
    # 全空值的行（主键与回退键都为空）按失败行记录，不写入
    parsed = ParseResult(
        source=SOURCE_ALIPAY, file_name="t.csv", columns=ALIPAY_COLUMNS,
        rows=[ParsedRow(row_number=5, values=[""] * len(ALIPAY_COLUMNS))],
    )
    result = db.import_parse_result(conn, SOURCE_ALIPAY, parsed, "a.csv")
    assert result["inserted"] == 0
    assert result["failed"] == 1
    assert result["failures"][0]["row"] == 5


def test_query_filters_and_sort(conn):
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, _alipay_rows()), "a.csv")

    all_rows = db.query_rows(conn, SOURCE_ALIPAY)
    assert all_rows["total"] == 3
    # 默认时间倒序
    assert all_rows["rows"][0]["交易时间"] == "2025-07-31 18:05:17"

    assert db.query_rows(conn, SOURCE_ALIPAY, directions=["不计收支"])["total"] == 1
    assert db.query_rows(conn, SOURCE_ALIPAY, categories=["餐饮美食"])["total"] == 1
    assert db.query_rows(conn, SOURCE_ALIPAY, q="对方")["total"] == 3
    assert db.query_rows(conn, SOURCE_ALIPAY, date_from="2025-07-30", date_to="2025-07-31")["total"] == 2
    assert db.query_rows(conn, SOURCE_ALIPAY, amount_min=10, amount_max=50)["total"] == 1
    # 金额排序（文本列按数值）
    top = db.query_rows(conn, SOURCE_ALIPAY, sort="amount", order="desc")
    assert top["rows"][0]["金额"] == "100.00"
    # 分页（page_size 为白名单档位）
    page = db.query_rows(conn, SOURCE_ALIPAY, page=1, page_size=10)
    assert page["total"] == 3
    assert len(page["rows"]) == 3
    beyond = db.query_rows(conn, SOURCE_ALIPAY, page=2, page_size=10)
    assert beyond["rows"] == []


def test_summary(conn):
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, _alipay_rows()), "a.csv")
    summary = db.query_summary(conn, SOURCE_ALIPAY)
    assert summary == {"count": 3, "income_sum": 100.0, "expense_sum": 27.0, "neutral_sum": 5.22}

    filtered = db.query_summary(conn, SOURCE_ALIPAY, directions=["支出"])
    assert filtered == {"count": 1, "income_sum": 0.0, "expense_sum": 27.0, "neutral_sum": 0.0}

    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _boc_rows()), "b.csv")
    boc_summary = db.query_summary(conn, SOURCE_BOC)
    assert boc_summary["count"] == 3
    assert boc_summary["income_sum"] == 1559.27
    assert boc_summary["expense_sum"] == 39.43
    assert boc_summary["last_balance"] == "1628.27"  # 筛选范围内最后一笔的余额


def test_distinct_categories(conn):
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, _alipay_rows()), "a.csv")
    assert db.distinct_categories(conn, SOURCE_ALIPAY) == ["其他", "投资理财", "餐饮美食"]


def test_query_unknown_source_rejected(conn):
    with pytest.raises(KeyError):
        db.query_rows(conn, "unknown")


def test_sql_injection_via_sort_rejected(conn):
    # 非白名单排序维度回退默认，不注入
    result = db.query_rows(conn, SOURCE_BOC, sort="amount; DROP TABLE boc_transactions")
    assert result["total"] == 0
    assert {"boc_transactions"} <= {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
