"""总账户三区结构与规则存储层测试：规则 CRUD、统一映射、三区划分、组键聚合与主记录选择（TCY-18）"""

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


def _seed_extra_boc_income(conn):
    """补一条与 boc:5 同日同规则命中的收入行（用于主记录收入优先测试）。"""
    rows = _rows(BOC_COLUMNS, [
        {"date": "2026-10-05", "time": "10:00:00", "tx_type": "收入", "amount": "3000.00",
         "counterparty": "支付宝-还款", "channel": "银企对接", "balance": "8088.80",
         "tx_name": "转账收入"},
    ])
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, rows), "b2.csv")


def _seed_many(conn, n):
    """补 n 条不同日期的收入行与 n 条花呗还款行（分区独立分页测试用）。"""
    income_rows = [
        {"date": f"2026-11-{i + 1:02d}", "time": "09:00:00", "tx_type": "收入", "amount": "100.00",
         "counterparty": "示例公司", "channel": "银企对接", "balance": "100.00", "tx_name": "代发工资"}
        for i in range(n)
    ]
    huabei_rows = [
        {"date": f"2026-11-{i + 1:02d}", "time": "10:00:00", "tx_type": "支出", "amount": "100.00",
         "counterparty": "支付宝-还款", "channel": "银企对接", "balance": "0.00", "tx_name": "转账支出"}
        for i in range(n)
    ]
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _rows(BOC_COLUMNS, income_rows)), "many1.csv")
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, _rows(BOC_COLUMNS, huabei_rows)), "many2.csv")


def _rule(conn, name, source, conditions, action="fold", enabled=True):
    return db.save_rule(conn, {"name": name, "source": source, "conditions": conditions,
                               "action": action, "enabled": enabled})


def _seed_rules(conn):
    """规则名与内置预设一致（通道对映射按预设规则名，设计 §3.1）。"""
    _rule(conn, "余额宝-转入转出", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}])
    _rule(conn, "支付宝余额-提现", SOURCE_ALIPAY, [{"field": "交易分类", "op": "eq", "value": "账户存取"}])
    _rule(conn, "微信零钱-充值提现", SOURCE_WECHAT, [{"field": "交易类型", "op": "in", "value": "零钱充值|零钱提现"}])
    _rule(conn, "银行卡快捷支付-渠道行（支付宝）", SOURCE_BOC,
          [{"field": "tx_name", "op": "eq", "value": "网上快捷支付"},
           {"field": "counterparty", "op": "starts", "value": "支付宝"}], action="hide")
    _rule(conn, "花呗还款-银行侧", SOURCE_BOC, [{"field": "counterparty", "op": "eq", "value": "支付宝-还款"}])


def _all_rows(result):
    """三区结构中的全部行（流动区含主记录与成员行）。"""
    rows = list(result["income"]["rows"]) + list(result["expense"]["rows"])
    for g in result["flow"]["groups"]:
        rows.append(g["main"])
        rows.extend(g["members"])
    return rows


def _flow_groups_by_key(result):
    return {g["key"]: g for g in result["flow"]["groups"]}


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
        assert hits["支付宝余额-提现"] == 1
        assert hits["微信零钱-充值提现"] == 2
        assert hits["银行卡快捷支付-渠道行（支付宝）"] == 1  # 支付宝渠道行 1 笔（财付通行不在该规则内）
        assert hits["花呗还款-银行侧"] == 1


# ---------------------------------------------------------------------------
# 总账户统一映射与筛选
# ---------------------------------------------------------------------------

class TestTotalMapping:
    def test_mapping_fields(self, conn):
        _seed(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = {r["id"]: r for r in _all_rows(result)}
        assert len(by_id) == 14  # 5 BOC + 5 支付宝 + 4 微信
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
        _seed_rules(conn)
        # 收/支只作用于真实区，内部流动区不受方向筛选影响
        neutral = total.query_rows(conn, directions=["不计收支"])
        assert neutral["income"]["total"] == 0
        assert neutral["expense"]["total"] == 0
        assert neutral["flow"]["row_total"] == 7
        real = total.query_rows(conn, directions=["支出", "收入"])
        assert real["income"]["total"] == 3
        assert real["expense"]["total"] == 4
        assert total.query_rows(conn, q="余额宝")["flow"]["row_total"] == 1
        assert total.query_rows(conn, q="余额宝")["income"]["total"] == 0
        assert total.query_rows(conn, q="工资")["income"]["total"] == 1
        assert total.query_rows(conn, date_from="2026-10-03")["income"]["total"] == 3
        assert total.query_rows(conn, date_from="2026-10-03")["expense"]["total"] == 1
        assert total.query_rows(conn, date_from="2026-10-03")["flow"]["row_total"] == 4
        assert total.query_rows(conn, date_to="2026-10-02")["income"]["total"] == 0
        assert total.query_rows(conn, date_to="2026-10-02")["expense"]["total"] == 3
        assert total.query_rows(conn, amount_min=100, amount_max=500)["flow"]["row_total"] == 4
        assert total.query_rows(conn, sources=["boc"])["income"]["total"] == 2
        assert total.query_rows(conn, sources=["boc"])["expense"]["total"] == 1
        assert total.query_rows(conn, sources=["boc"])["flow"]["row_total"] == 2
        assert total.query_rows(conn, sources=["alipay", "wechat"])["income"]["total"] == 1
        assert total.query_rows(conn, sources=[])["income"]["total"] == 0
        assert total.query_rows(conn, sources=["unknown"])["income"]["total"] == 0

    def test_sort_and_zone_pagination(self, conn):
        _seed(conn)
        _seed_rules(conn)
        by_time = total.query_rows(conn, sort="datetime", order="desc")
        times = [r["time"] for r in by_time["income"]["rows"]]
        assert times == sorted(times, reverse=True)
        assert by_time["income"]["rows"][0]["time"] == "2026-10-04 16:00:00"

        by_amount = total.query_rows(conn, sort="amount", order="desc")["income"]["rows"]
        assert by_amount[0]["amount"] == "8000.00"

        by_cp = total.query_rows(conn, sort="counterparty", order="asc")["income"]["rows"]
        cps = [r["counterparty"] for r in by_cp if r["counterparty"]]
        assert cps == sorted(cps)

        # 各区独立分页：真实区按行、流动区按组，页码互不影响
        _seed_many(conn, 12)
        income_page2 = total.query_rows(conn, income_page=2, page_size=10)
        assert income_page2["income"]["total"] == 15  # 原有 3 + 新增 12
        assert len(income_page2["income"]["rows"]) == 5
        assert income_page2["income"]["page"] == 2
        assert income_page2["expense"]["page"] == 1
        assert income_page2["flow"]["page"] == 1
        flow_page2 = total.query_rows(conn, flow_page=2, page_size=10)
        assert flow_page2["flow"]["total"] == 19  # 原有 7 组 + 新增 12 组
        assert len(flow_page2["flow"]["groups"]) == 9
        assert flow_page2["flow"]["page"] == 2
        assert flow_page2["flow"]["groups"][0]["key"] == "花呗|2026-11-02"
        assert flow_page2["income"]["page"] == 1


# ---------------------------------------------------------------------------
# 三区划分、内部流动分组与主记录选择
# ---------------------------------------------------------------------------

class TestTotalZones:
    def test_zone_partition(self, conn):
        """未命中按方向进真实区；命中或不计收支进流动区。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        assert {r["id"] for r in result["income"]["rows"]} == {"boc:3", "boc:4", "wechat:4"}
        assert {r["id"] for r in result["expense"]["rows"]} == {"boc:2", "alipay:1", "alipay:5", "wechat:2"}
        assert result["flow"]["row_total"] == 7
        flow_ids = set()
        for g in result["flow"]["groups"]:
            flow_ids.add(g["main"]["id"])
            flow_ids.update(m["id"] for m in g["members"])
        assert flow_ids == {"boc:1", "boc:5", "alipay:2", "alipay:3", "alipay:4", "wechat:1", "wechat:3"}

    def test_disabled_rule_not_applied(self, conn):
        _seed(conn)
        _rule(conn, "停用规则", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}],
              enabled=False)
        result = total.query_rows(conn, page_size=200)
        # 停用规则不生效：余额宝行未命中且方向=不计收支，仍进流动区
        assert result["flow"]["row_total"] == 5  # 不计收支 5 行（3 支付宝 + 2 微信）
        assert result["income"]["total"] == 3
        assert result["expense"]["total"] == 6

    def test_flow_groups_by_pair_and_date(self, conn):
        """组键 = 通道对 × 日期（预设规则名映射到通道对）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        groups = _flow_groups_by_key(result)
        assert set(groups) == {
            "支付宝 ↔ BOC|2026-10-01", "支付宝 ↔ BOC|2026-10-02", "支付宝 ↔ BOC|2026-10-03",
            "微信 ↔ BOC|2026-10-03", "支付宝|2026-10-04", "微信 ↔ BOC|2026-10-01",
            "花呗|2026-10-05",
        }
        # 组按主记录时间倒序
        assert [g["key"] for g in result["flow"]["groups"]] == [
            "花呗|2026-10-05", "支付宝|2026-10-04", "微信 ↔ BOC|2026-10-03", "支付宝 ↔ BOC|2026-10-03",
            "支付宝 ↔ BOC|2026-10-02", "微信 ↔ BOC|2026-10-01", "支付宝 ↔ BOC|2026-10-01",
        ]

    def test_custom_rule_forms_own_pair(self, conn):
        """自定义规则自成一个通道对（名 = 规则名，设计 §3.1）。"""
        _seed(conn)
        _rule(conn, "我的自定义互转", SOURCE_BOC, [{"field": "counterparty", "op": "eq", "value": "支付宝-还款"}])
        result = total.query_rows(conn, page_size=200)
        group = _flow_groups_by_key(result)["我的自定义互转|2026-10-05"]
        assert group["main"]["id"] == "boc:5"
        assert group["main"]["mark"] == "flow"

    def test_main_pick_income_first(self, conn):
        """主记录 = 组内收入最新行（无收入取支出最新；收入早于支出仍以收入为主）。"""
        _seed(conn)
        _seed_rules(conn)
        _seed_extra_boc_income(conn)  # boc:6 收入 10:00，与 boc:5 支出 12:00 同组
        result = total.query_rows(conn, page_size=200)
        group = _flow_groups_by_key(result)["花呗|2026-10-05"]
        assert group["main"]["id"] == "boc:6"
        assert group["main"]["direction"] == "收入"
        assert group["main"]["member_count"] == 1
        assert [m["id"] for m in group["members"]] == ["boc:5"]

    def test_main_pick_fallback(self, conn):
        """无收入行取支出最新；纯不计收支组取时间最新。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        groups = _flow_groups_by_key(result)
        assert groups["花呗|2026-10-05"]["main"]["id"] == "boc:5"  # 仅支出行
        assert groups["支付宝|2026-10-04"]["main"]["id"] == "alipay:4"  # 纯不计收支组

    def test_flow_labels_and_cross_ref(self, conn):
        """hide→重复记录、fold→内部流动；渠道重复组带跨区引用提示。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        groups = _flow_groups_by_key(result)
        # 命中 hide 的渠道行：重复记录 + 跨区引用（组内无平台侧行）
        alipay_pair = groups["支付宝 ↔ BOC|2026-10-01"]
        assert alipay_pair["main"]["mark"] == "duplicate"
        assert alipay_pair["main"]["rule_names"] == ["银行卡快捷支付-渠道行（支付宝）"]
        assert alipay_pair["cross_ref"] is True
        assert alipay_pair["platform"] == "支付宝"
        # 命中 fold：内部流动
        assert groups["花呗|2026-10-05"]["main"]["mark"] == "flow"
        # 未命中规则的不计收支行：内部流动且无命中规则名
        ungrouped = groups["支付宝|2026-10-04"]["main"]
        assert ungrouped["mark"] == "flow"
        assert ungrouped["rule_names"] == []
        # 无重复记录行的组不提示跨区引用
        assert groups["微信 ↔ BOC|2026-10-01"]["cross_ref"] is False

    def test_direction_filter_not_apply_to_flow(self, conn):
        """收/支筛选只作用于真实区，内部流动区不受影响。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, directions=["支出"])
        assert result["income"]["total"] == 0
        assert result["expense"]["total"] == 4
        assert result["flow"]["row_total"] == 7
        assert result["flow"]["total"] == 7

    def test_q_filter_regroups_and_refills_main(self, conn):
        """流动区先按行过滤再重新分组，主记录被筛掉时自动递补。"""
        _seed(conn)
        _seed_rules(conn)
        _seed_extra_boc_income(conn)
        # 只筛出支出行：主记录递补为 boc:5
        expense_only = total.query_rows(conn, q="转账支出", page_size=200)
        assert expense_only["flow"]["total"] == 1
        group = expense_only["flow"]["groups"][0]
        assert group["main"]["id"] == "boc:5"
        assert group["members"] == []
        # 关键词跨区：命中「支付宝」的行分布到三区，流动区重新分组
        by_cp = total.query_rows(conn, q="支付宝", page_size=200)
        assert {r["id"] for r in by_cp["income"]["rows"]} == {"boc:4"}
        assert by_cp["expense"]["total"] == 0
        assert by_cp["flow"]["total"] == 3
        assert {g["key"] for g in by_cp["flow"]["groups"]} == {
            "支付宝 ↔ BOC|2026-10-01", "花呗|2026-10-05", "支付宝 ↔ BOC|2026-10-03"}

    def test_empty_zones(self, conn):
        """空区返回空列表（前端显示「该区无记录」）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, directions=["收入"])
        assert result["expense"]["total"] == 0
        assert result["expense"]["rows"] == []
        assert result["income"]["total"] == 3
        none = total.query_rows(conn, sources=[])
        assert none["income"]["rows"] == [] and none["flow"]["groups"] == []


class TestTotalSummary:
    def test_three_zone_metrics(self, conn):
        """真实收入 / 真实支出 / 净收支 / 真实笔数 + 内部流动组数行数。"""
        _seed(conn)
        _seed_rules(conn)
        s = total.query_summary(conn)
        assert s["income"] == {"count": 3, "sum": 8038.80}  # 8000 + 8.80 + 30
        assert s["expense"] == {"count": 4, "sum": 154.00}  # 20 + 18 + 50 + 66
        assert s["net"] == 7884.80
        assert s["count"] == 7
        assert s["flow"] == {"groups": 7, "rows": 7}

    def test_summary_follows_filters(self, conn):
        _seed(conn)
        _seed_rules(conn)
        s = total.query_summary(conn, date_from="2026-10-04")
        assert s["income"] == {"count": 2, "sum": 38.80}
        assert s["expense"] == {"count": 1, "sum": 50.00}
        assert s["flow"] == {"groups": 2, "rows": 2}
        # 收/支筛选不作用于内部流动口径
        d = total.query_summary(conn, directions=["支出"])
        assert d["income"] == {"count": 0, "sum": 0.0}
        assert d["expense"] == {"count": 4, "sum": 154.00}
        assert d["flow"] == {"groups": 7, "rows": 7}

    def test_summary_without_rules(self, conn):
        """无规则时未命中的不计收支行仍进流动区，不进真实收支。"""
        _seed(conn)
        s = total.query_summary(conn)
        assert s["income"] == {"count": 3, "sum": 8038.80}
        assert s["expense"] == {"count": 6, "sum": 3162.80}
        assert s["flow"] == {"groups": 5, "rows": 5}
        assert s["count"] == 9
