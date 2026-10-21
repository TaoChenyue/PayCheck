"""总账户视图与规则存储层测试：规则 CRUD、统一映射、三种显示模式、汇总三口径（TCY-15）"""

from __future__ import annotations

import pytest

from paycheck_workbench import db, total
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


def _rows(columns, specs):
    return [[spec.get(c, "") for c in columns] for spec in specs]


def _seed(conn):
    """构造三源样本（与真实数据无关）：含渠道重复行、余额宝、零钱通、花呗还款等场景。"""
    boc = _rows(BOC_COLUMNS, [
        {"date": "2026-10-01", "time": "10:00:00", "tx_type": "支出", "amount": "8.80",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "100.00",
         "tx_name": "网上快捷支付"},
        {"date": "2026-10-02", "time": "10:00:00", "tx_type": "支出", "amount": "20.00",
         "counterparty": "财付通", "channel": "银企对接", "balance": "80.00",
         "tx_name": "网上快捷支付"},
        {"date": "2026-10-03", "time": "09:00:00", "tx_type": "收入", "amount": "8000.00",
         "counterparty": "示例公司", "channel": "银企对接", "balance": "8080.00",
         "tx_name": "代发工资", "memo": "10月工资"},
        {"date": "2026-10-04", "time": "11:00:00", "tx_type": "收入", "amount": "8.80",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "8088.80",
         "tx_name": "网上快捷退款"},
        {"date": "2026-10-05", "time": "12:00:00", "tx_type": "支出", "amount": "3000.00",
         "counterparty": "支付宝-还款", "channel": "银企对接", "balance": "5088.80",
         "tx_name": "转账支出"},
    ])
    alipay = _rows(ALIPAY_COLUMNS, [
        {"交易时间": "2026-10-01 12:00:00", "交易分类": "餐饮美食", "交易对方": "示例面馆",
         "商品说明": "牛肉面", "收/支": "支出", "金额": "18.00", "交易订单号": "A1", "交易状态": "交易成功"},
        {"交易时间": "2026-10-02 08:00:00", "交易分类": "投资理财", "交易对方": "余额宝",
         "商品说明": "余额宝-收益发放", "收/支": "不计收支", "金额": "0.50", "交易订单号": "A2", "交易状态": "交易成功"},
        {"交易时间": "2026-10-03 09:00:00", "交易分类": "账户存取", "交易对方": "支付宝",
         "商品说明": "余额提现", "收/支": "不计收支", "金额": "500.00", "交易订单号": "A3", "交易状态": "交易成功"},
        {"交易时间": "2026-10-04 10:00:00", "交易分类": "信用借还", "交易对方": "花呗",
         "商品说明": "花呗主动还款", "收/支": "不计收支", "金额": "300.00", "交易订单号": "A4", "交易状态": "交易成功"},
        {"交易时间": "2026-10-05 11:00:00", "交易分类": "手机充值", "交易对方": "中国移动",
         "商品说明": "话费充值", "收/支": "支出", "金额": "50.00", "交易订单号": "A5", "交易状态": "交易成功"},
    ])
    wechat = _rows(WECHAT_COLUMNS, [
        {"交易时间": "2026-10-01 13:00:00", "交易类型": "零钱充值", "交易对方": "/", "商品": "/",
         "收/支": "中性交易", "金额(元)": "200.00", "支付方式": "/", "交易单号": "W1", "当前状态": "支付成功"},
        {"交易时间": "2026-10-02 14:00:00", "交易类型": "商户消费", "交易对方": "示例超市",
         "商品": "日常用品", "收/支": "支出", "金额(元)": "66.00", "支付方式": "零钱", "交易单号": "W2", "当前状态": "支付成功"},
        {"交易时间": "2026-10-03 15:00:00", "交易类型": "零钱提现", "交易对方": "/", "商品": "/",
         "收/支": "中性交易", "金额(元)": "100.00", "支付方式": "/", "交易单号": "W3", "当前状态": "提现成功"},
        {"交易时间": "2026-10-04 16:00:00", "交易类型": "转账", "交易对方": "示例朋友",
         "商品": "/", "收/支": "收入", "金额(元)": "30.00", "支付方式": "零钱", "交易单号": "W4", "当前状态": "已收钱"},
    ])
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, boc), "b.csv")
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, alipay), "a.csv")
    db.import_parse_result(conn, SOURCE_WECHAT, _parsed(SOURCE_WECHAT, WECHAT_COLUMNS, wechat), "w.csv")


def _rule(conn, name, source, conditions, action="fold", enabled=True):
    return db.save_rule(conn, {"name": name, "source": source, "conditions": conditions,
                               "action": action, "enabled": enabled})


def _seed_rules(conn):
    _rule(conn, "余额宝-转入转出", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}])
    _rule(conn, "账户存取", SOURCE_ALIPAY, [{"field": "交易分类", "op": "eq", "value": "账户存取"}])
    _rule(conn, "零钱充值提现", SOURCE_WECHAT, [{"field": "交易类型", "op": "in", "value": "零钱充值|零钱提现"}])
    _rule(conn, "快捷支付渠道行", SOURCE_BOC,
          [{"field": "tx_name", "op": "eq", "value": "网上快捷支付"},
           {"field": "counterparty", "op": "starts", "value": "支付宝"}], action="hide")
    _rule(conn, "花呗还款-银行侧", SOURCE_BOC, [{"field": "counterparty", "op": "eq", "value": "支付宝-还款"}])


# ---------------------------------------------------------------------------
# 规则 CRUD
# ---------------------------------------------------------------------------

class TestRuleCrud:
    def test_create_list_get_update_delete(self, conn):
        created = _rule(conn, "测试规则", SOURCE_BOC, [{"field": "memo", "op": "contains", "value": "工资"}])
        assert created["id"] == 1
        assert created["enabled"] is True
        assert created["action"] == "fold"
        assert created["created_at"]

        assert [r["name"] for r in db.list_rules(conn)] == ["测试规则"]
        assert db.get_rule(conn, created["id"])["conditions"] == [{"field": "memo", "op": "contains", "value": "工资"}]

        updated = db.save_rule(conn, {**created, "enabled": False, "action": "hide"}, rule_id=created["id"])
        assert updated["enabled"] is False
        assert updated["action"] == "hide"
        assert db.list_rules(conn)[0]["enabled"] is False

        db.delete_rule(conn, created["id"])
        assert db.list_rules(conn) == []
        assert db.get_rule(conn, created["id"]) is None

    def test_update_keeps_preset_id(self, conn):
        created = db.save_rule(conn, {"name": "p", "source": "boc", "preset_id": "preset-x",
                                      "conditions": [{"field": "memo", "op": "eq", "value": "a"}],
                                      "action": "fold", "enabled": True})
        updated = db.save_rule(conn, {"name": "p2", "source": "boc",
                                      "conditions": [{"field": "memo", "op": "eq", "value": "b"}],
                                      "action": "hide", "enabled": False}, rule_id=created["id"])
        assert updated["preset_id"] == "preset-x"

    def test_find_duplicate_rule(self, conn):
        conditions = [{"field": "交易分类", "op": "eq", "value": "信用借还"},
                      {"field": "交易对方", "op": "eq", "value": "花呗"}]
        _rule(conn, "花呗", SOURCE_ALIPAY, conditions)
        # 同名同条件（AND 顺序无关）视为重复
        dup = db.find_duplicate_rule(conn, "花呗", list(reversed(conditions)))
        assert dup is not None
        assert db.find_duplicate_rule(conn, "花呗", conditions[:1]) is None
        assert db.find_duplicate_rule(conn, "别的名字", conditions) is None


class TestRuleHits:
    def test_count_and_match_ids(self, conn):
        _seed(conn)
        rule = {"source": SOURCE_BOC, "conditions": [{"field": "tx_name", "op": "eq", "value": "网上快捷支付"}]}
        assert db.count_rule_hits(conn, rule) == 2
        assert len(db.rule_match_ids(conn, rule)) == 2

        _seed_rules(conn)
        rule_list = db.list_rules(conn)
        hits = {r["name"]: db.count_rule_hits(conn, r) for r in rule_list}
        assert hits["余额宝-转入转出"] == 1
        assert hits["账户存取"] == 1
        assert hits["零钱充值提现"] == 2
        assert hits["快捷支付渠道行"] == 1  # 支付宝渠道行 1 笔（财付通行不在该规则内）
        assert hits["花呗还款-银行侧"] == 1


# ---------------------------------------------------------------------------
# 总账户统一映射与筛选
# ---------------------------------------------------------------------------

class TestTotalMapping:
    def test_mapping_and_default_mode(self, conn):
        _seed(conn)
        result = total.query_rows(conn)
        assert result["total"] == 14  # 5 BOC + 5 支付宝 + 4 微信
        by_id = {r["id"]: r for r in result["rows"]}
        boc_pay = by_id["boc:1"]
        assert boc_pay["time"] == "2026-10-01 10:00:00"
        assert boc_pay["direction"] == "支出"
        assert boc_pay["counterparty"] == "支付宝"
        assert boc_pay["summary"] == "网上快捷支付"
        # BOC 摘要：memo 非空时拼接
        assert by_id["boc:3"]["summary"] == "代发工资（10月工资）"
        # 微信「中性交易」统一展示为「不计收支」
        assert by_id["wechat:1"]["direction"] == "不计收支"
        # 微信摘要：商品为空用交易类型
        assert by_id["wechat:1"]["summary"] == "零钱充值"
        assert by_id["wechat:2"]["summary"] == "日常用品"
        # 原始列保留于 raw，供行详情展开
        assert boc_pay["raw"]["tx_name"] == "网上快捷支付"
        assert by_id["alipay:2"]["raw"]["商品说明"] == "余额宝-收益发放"

    def test_filters(self, conn):
        _seed(conn)
        assert total.query_rows(conn, directions=["不计收支"])["total"] == 5  # 3 支付宝 + 2 微信
        assert total.query_rows(conn, directions=["支出", "收入"])["total"] == 9
        assert total.query_rows(conn, q="余额宝")["total"] == 1  # 对方 + 摘要
        assert total.query_rows(conn, q="工资")["total"] == 1
        assert total.query_rows(conn, date_from="2026-10-03")["total"] == 8
        assert total.query_rows(conn, date_to="2026-10-02")["total"] == 6
        assert total.query_rows(conn, amount_min=100, amount_max=500)["total"] == 4
        assert total.query_rows(conn, sources=["boc"])["total"] == 5
        assert total.query_rows(conn, sources=["alipay", "wechat"])["total"] == 9
        assert total.query_rows(conn, sources=[])["total"] == 0
        assert total.query_rows(conn, sources=["unknown"])["total"] == 0

    def test_sort_and_pagination(self, conn):
        _seed(conn)
        result = total.query_rows(conn, sort="datetime", order="desc")
        times = [r["time"] for r in result["rows"]]
        assert times == sorted(times, reverse=True)
        assert result["rows"][0]["time"] == "2026-10-05 12:00:00"

        by_amount = total.query_rows(conn, sort="amount", order="desc")["rows"]
        assert by_amount[0]["amount"] == "8000.00"
        assert by_amount[-1]["amount"] == "0.50"

        by_cp = total.query_rows(conn, sort="counterparty", order="asc")["rows"]
        cps = [r["counterparty"] for r in by_cp if r["counterparty"]]
        assert cps == sorted(cps)

        page2 = total.query_rows(conn, page=2, page_size=10)
        assert page2["total"] == 14
        assert len(page2["rows"]) == 4
        assert page2["rows"][0]["id"] != total.query_rows(conn, page=1, page_size=10)["rows"][0]["id"]


# ---------------------------------------------------------------------------
# 内部转账三种显示模式与汇总
# ---------------------------------------------------------------------------

class TestTransferModes:
    def test_fold_mode_marks_and_hides_hide_rules(self, conn):
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, transfer="fold")
        assert result["total"] == 14 - 1  # 快捷支付渠道行（hide）被隐藏
        assert result["hidden"] == {"count": 1, "rule_names": ["快捷支付渠道行"]}
        marked = [r for r in result["rows"] if r["transfer"]]
        assert {r["id"] for r in marked} == {"alipay:2", "alipay:3", "wechat:1", "wechat:3", "boc:5"}
        assert all(r["transfer"]["action"] == "fold" for r in marked)
        rule_names = {name for r in marked for name in r["transfer"]["rule_names"]}
        assert rule_names == {"余额宝-转入转出", "账户存取", "零钱充值提现", "花呗还款-银行侧"}

    def test_hide_mode_hides_all_hit_rows(self, conn):
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, transfer="hide")
        assert result["total"] == 14 - 6
        assert all(r["transfer"] is None for r in result["rows"])
        assert result["hidden"]["count"] == 6

    def test_show_mode_disables_rules(self, conn):
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, transfer="show")
        assert result["total"] == 14
        assert all(r["transfer"] is None for r in result["rows"])
        assert result["hidden"]["count"] == 0

    def test_disabled_rule_not_applied(self, conn):
        _seed(conn)
        _rule(conn, "停用规则", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}],
              enabled=False)
        result = total.query_rows(conn, transfer="fold")
        assert result["total"] == 14
        assert all(r["transfer"] is None for r in result["rows"])

    def test_invalid_mode_falls_back_to_fold(self, conn):
        _seed(conn)
        _seed_rules(conn)
        assert total.query_rows(conn, transfer="boom")["total"] == 13


class TestTotalSummary:
    def test_three_sets(self, conn):
        _seed(conn)
        _seed_rules(conn)
        summary = total.query_summary(conn)
        # counted：14 - 1(hide 渠道行) - 5(fold 命中) = 8 笔
        assert summary["counted"]["count"] == 8
        assert summary["transfer"]["count"] == 5
        assert summary["hidden"]["count"] == 1
        # fold/hide 命中金额不进入 counted
        assert summary["counted"]["expense_sum"] == 20.00 + 18.00 + 50.00 + 66.00
        assert summary["counted"]["income_sum"] == 8000.00 + 8.80 + 30.00
        # fold 命中行（花呗还款银行侧）金额进入 transfer 口径
        assert summary["transfer"]["expense_sum"] == 3000.00
        assert summary["transfer"]["income_sum"] == 0.0
        assert summary["hidden"]["expense_sum"] == 8.80

    def test_summary_follows_filters(self, conn):
        _seed(conn)
        _seed_rules(conn)
        summary = total.query_summary(conn, date_from="2026-10-04")
        assert summary["counted"]["count"] == 4
        assert summary["counted"]["income_sum"] == 8.80 + 30.00
        assert summary["counted"]["expense_sum"] == 50.00

    def test_summary_show_mode_composition(self, conn):
        """全部显示 = 三套口径合计。"""
        _seed(conn)
        _seed_rules(conn)
        s = total.query_summary(conn)
        total_count = s["counted"]["count"] + s["transfer"]["count"] + s["hidden"]["count"]
        assert total_count == 14
        total_expense = s["counted"]["expense_sum"] + s["transfer"]["expense_sum"] + s["hidden"]["expense_sum"]
        assert total_expense == 8.80 + 20.00 + 3000.00 + 18.00 + 50.00 + 66.00
