"""数据库模块集成测试 — CRUD 操作、标签管理、设置持久化。

使用临时数据库隔离测试，避免影响生产数据。
"""

import pytest
from paycheck.storage.database import (
    _connect, insert_transactions, get_all_transactions, get_summary,
    get_all_tags, get_tag_list, create_tag, rename_tag, delete_tag,
    merge_tags, set_transaction_tags, get_transaction_tags,
    get_transaction_tags_batch, batch_set_tags, query_by_tag_ids,
    get_transactions_by_ids, get_setting, set_setting,
)


# ═══════════════════════════════════════════════════════════
# 表创建测试
# ═══════════════════════════════════════════════════════════

class TestTableCreation:
    """验证数据库表结构自动创建"""

    def test_tables_exist(self, temp_db):
        conn = _connect(temp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r[0] for r in tables}
        assert "transactions" in table_names
        assert "tags" in table_names
        assert "transaction_tags" in table_names
        assert "settings" in table_names
        conn.close()

    def test_transactions_schema(self, temp_db):
        conn = _connect(temp_db)
        cols = conn.execute("PRAGMA table_info(transactions)").fetchall()
        col_names = {c[1] for c in cols}
        essential = {"id", "platform", "time", "amount", "counterparty",
                     "category", "tx_type", "payment_method", "description"}
        assert essential.issubset(col_names)
        conn.close()

    def test_unique_constraint(self, temp_db):
        """time + amount + counterparty 组合唯一"""
        conn = _connect(temp_db)
        conn.execute("""INSERT INTO transactions (platform, time, amount, counterparty)
                        VALUES ('wechat', '2025-01-01', 100, '测试')""")
        with pytest.raises(Exception):
            conn.execute("""INSERT INTO transactions (platform, time, amount, counterparty)
                            VALUES ('wechat', '2025-01-01', 100, '测试')""")
        conn.close()


# ═══════════════════════════════════════════════════════════
# 交易插入与查询测试
# ═══════════════════════════════════════════════════════════

class TestTransactionCRUD:
    """交易的插入、去重、查询"""

    def test_insert_empty(self, temp_db):
        added = insert_transactions([], temp_db)
        assert added == 0

    def test_insert_and_query(self, temp_db, sample_transactions):
        added = insert_transactions(sample_transactions, temp_db)
        assert added == len(sample_transactions)

        all_tx = get_all_transactions(temp_db)
        assert len(all_tx) == len(sample_transactions)
        # 验证按时间倒序
        assert all_tx[0]["time"] >= all_tx[-1]["time"]

    def test_dedup_duplicate(self, temp_db, sample_transactions):
        """重复插入同一交易应跳过"""
        first_added = insert_transactions(sample_transactions, temp_db)
        second_added = insert_transactions(sample_transactions, temp_db)
        assert second_added == 0
        all_tx = get_all_transactions(temp_db)
        assert len(all_tx) == first_added

    def test_partial_dedup(self, temp_db, sample_transactions):
        """部分重复：新交易插入，旧交易跳过"""
        insert_transactions(sample_transactions[:2], temp_db)
        added = insert_transactions(sample_transactions, temp_db)
        assert added == 1  # 只有第三条是新的
        all_tx = get_all_transactions(temp_db)
        assert len(all_tx) == 3

    def test_field_completeness(self, temp_db, sample_transactions):
        insert_transactions(sample_transactions, temp_db)
        all_tx = get_all_transactions(temp_db)
        tx = all_tx[0]
        # 所有字段应存在
        for field in ["platform", "time", "amount", "counterparty",
                       "category", "tx_type", "payment_method"]:
            assert field in tx, f"Missing field: {field}"

    def test_get_transactions_by_ids(self, temp_db, sample_transactions):
        insert_transactions(sample_transactions, temp_db)
        all_tx = get_all_transactions(temp_db)
        ids = [t["id"] for t in all_tx[:2]]
        result = get_transactions_by_ids(ids, temp_db)
        assert len(result) == 2

    def test_get_by_ids_empty(self, temp_db):
        result = get_transactions_by_ids([], temp_db)
        assert result == []


# ═══════════════════════════════════════════════════════════
# 汇总统计测试
# ═══════════════════════════════════════════════════════════

class TestSummary:
    """汇总统计查询"""

    def test_empty_db(self, temp_db):
        summary = get_summary(temp_db)
        assert summary["total_expense"] == 0
        assert summary["total_income"] == 0
        assert summary["total_count"] == 0

    def test_summary_with_data(self, temp_db, sample_transactions):
        insert_transactions(sample_transactions, temp_db)
        summary = get_summary(temp_db)
        # 2 条支出 + 1 条收入
        assert summary["total_expense"] == 35.50 + 199.00
        assert summary["total_income"] == 15000.00
        assert summary["total_count"] == 2
        assert summary["wechat_count"] >= 0
        assert summary["monthly_avg"] >= 0


# ═══════════════════════════════════════════════════════════
# 标签 CRUD 测试
# ═══════════════════════════════════════════════════════════

class TestTagCRUD:
    """标签的创建、重命名、删除、合并"""

    def test_create_tag(self, temp_db):
        tid = create_tag("新标签", temp_db)
        assert tid > 0

    def test_create_duplicate_tag_name(self, temp_db):
        create_tag("唯一标签", temp_db)
        with pytest.raises(Exception):
            create_tag("唯一标签", temp_db)

    def test_rename_tag(self, temp_db):
        tid = create_tag("旧名称", temp_db)
        rename_tag(tid, "新名称", temp_db)
        tags = get_tag_list(temp_db)
        names = {t["name"] for t in tags}
        assert "新名称" in names
        assert "旧名称" not in names

    def test_delete_tag(self, temp_db):
        tid = create_tag("待删除", temp_db)
        delete_tag(tid, temp_db)
        tags = get_tag_list(temp_db)
        assert len(tags) == 0

    def test_get_all_tags_with_count(self, temp_db, sample_transactions):
        """标签列表含引用计数"""
        insert_transactions(sample_transactions, temp_db)
        tid1 = create_tag("标签A", temp_db)
        tid2 = create_tag("标签B", temp_db)
        all_tx = get_all_transactions(temp_db)
        set_transaction_tags(all_tx[0]["id"], [tid1], temp_db)
        set_transaction_tags(all_tx[1]["id"], [tid1, tid2], temp_db)

        tags = get_all_tags(temp_db)
        tag_dict = {t["name"]: t["count"] for t in tags}
        assert tag_dict["标签A"] == 2
        assert tag_dict["标签B"] == 1

    def test_merge_tags(self, temp_db, sample_transactions):
        """合并标签：源标签删除，交易归入目标标签"""
        insert_transactions(sample_transactions, temp_db)
        tid_src = create_tag("源标签", temp_db)
        tid_tgt = create_tag("目标标签", temp_db)
        all_tx = get_all_transactions(temp_db)
        set_transaction_tags(all_tx[0]["id"], [tid_src], temp_db)

        merge_tags(tid_src, tid_tgt, temp_db)
        tags = get_tag_list(temp_db)
        names = {t["name"] for t in tags}
        assert "源标签" not in names
        assert "目标标签" in names
        # 原交易转到目标标签
        tx_tags = get_transaction_tags(all_tx[0]["id"], temp_db)
        assert len(tx_tags) == 1
        assert tx_tags[0]["id"] == tid_tgt

    def test_batch_set_tags(self, temp_db, sample_transactions):
        insert_transactions(sample_transactions, temp_db)
        tid = create_tag("批量标签", temp_db)
        all_tx = get_all_transactions(temp_db)
        tx_ids = [t["id"] for t in all_tx]
        batch_set_tags(tx_ids, [tid], temp_db)

        batch_result = get_transaction_tags_batch(tx_ids, temp_db)
        for tx_id in tx_ids:
            assert tid in batch_result[tx_id]

    def test_query_by_tag_ids(self, temp_db, sample_transactions):
        insert_transactions(sample_transactions, temp_db)
        tid = create_tag("查询标签", temp_db)
        all_tx = get_all_transactions(temp_db)
        set_transaction_tags(all_tx[0]["id"], [tid], temp_db)
        set_transaction_tags(all_tx[1]["id"], [tid], temp_db)

        tx_ids = query_by_tag_ids([tid], temp_db)
        assert len(tx_ids) == 2

    def test_query_by_tag_ids_empty(self, temp_db):
        result = query_by_tag_ids([], temp_db)
        assert result == []


# ═══════════════════════════════════════════════════════════
# 设置持久化测试
# ═══════════════════════════════════════════════════════════

class TestSettings:
    """键值设置持久化"""

    def test_set_and_get(self, temp_db):
        set_setting("test_key", "test_value", temp_db)
        assert get_setting("test_key", path=temp_db) == "test_value"

    def test_get_nonexistent_default(self, temp_db):
        assert get_setting("nonexistent", "fallback", temp_db) == "fallback"

    def test_overwrite_setting(self, temp_db):
        set_setting("key", "v1", temp_db)
        set_setting("key", "v2", temp_db)
        assert get_setting("key", path=temp_db) == "v2"

    def test_multiple_keys(self, temp_db):
        set_setting("k1", "a", temp_db)
        set_setting("k2", "b", temp_db)
        assert get_setting("k1", path=temp_db) == "a"
        assert get_setting("k2", path=temp_db) == "b"
