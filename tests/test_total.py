"""总账户两区结构与配对算法测试：规则 CRUD、统一映射、两区划分、同日同金额配对、
划转路径标注与汇总（TCY-24）"""

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
    SOURCES,
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
    """构造三源样本（与真实数据无关）：渠道重复行（可配对/金额不符/前缀不符）、
    划转规则命中、未命中不计收支、真实收支等场景。"""
    boc = _rows(BOC_COLUMNS, [
        # 配对成功：与支付宝同金额支出（镜像·支付宝）
        {"date": "2026-10-01", "time": "10:00:00", "tx_type": "支出", "amount": "8.80",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "100.00", "tx_name": "网上快捷支付"},
        # 金额对不上（微信当日无 20.00）→ 未配对 → 真实支出（DP2）
        {"date": "2026-10-02", "time": "10:00:00", "tx_type": "支出", "amount": "20.00",
         "counterparty": "财付通", "channel": "银企对接", "balance": "80.00", "tx_name": "网上快捷支付"},
        # 真实收入
        {"date": "2026-10-03", "time": "09:00:00", "tx_type": "收入", "amount": "8000.00",
         "counterparty": "示例公司", "channel": "银企对接", "balance": "8080.00", "tx_name": "代发工资", "memo": "10月工资"},
        # 配对成功：退款（双方收入，镜像·支付宝）
        {"date": "2026-10-04", "time": "11:00:00", "tx_type": "收入", "amount": "8.80",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "8088.80", "tx_name": "网上快捷退款"},
        # 命中花呗还款-银行侧规则 → 忽略区标路径
        {"date": "2026-10-05", "time": "12:00:00", "tx_type": "支出", "amount": "3000.00",
         "counterparty": "支付宝-还款", "channel": "银企对接", "balance": "5088.80", "tx_name": "转账支出"},
        # 对方前缀不匹配支付宝/财付通 → 无渠道分组、不配对 → 真实支出（补充边界）
        {"date": "2026-10-06", "time": "10:00:00", "tx_type": "支出", "amount": "66.00",
         "counterparty": "其他通道", "channel": "银企对接", "balance": "5022.80", "tx_name": "网上快捷支付"},
        # 命中平台提现入账规则 → 忽略区标路径（支出：本端 → 对端）
        {"date": "2026-10-07", "time": "10:00:00", "tx_type": "支出", "amount": "100.00",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "4922.80", "tx_name": "网上快捷提现"},
        # 命中基金/平台入账（蚂蚁）规则 → 忽略区标路径（收入：对端 → 本端）
        {"date": "2026-10-08", "time": "10:00:00", "tx_type": "收入", "amount": "500.00",
         "counterparty": "蚂蚁基金", "channel": "银企对接", "balance": "5422.80", "tx_name": "银联入账"},
        # 配对成功：与微信零钱充值同金额（方向无关，镜像·微信）
        {"date": "2026-10-01", "time": "09:00:00", "tx_type": "支出", "amount": "200.00",
         "counterparty": "财付通", "channel": "银企对接", "balance": "300.00", "tx_name": "网上快捷支付"},
    ])
    alipay = _rows(ALIPAY_COLUMNS, [
        # 与 boc:1 同日同金额 → 平台侧主记录（真实支出）
        {"交易时间": "2026-10-01 12:00:00", "交易分类": "餐饮美食", "交易对方": "示例面馆",
         "商品说明": "牛肉面", "收/支": "支出", "金额": "8.80", "交易订单号": "A1", "交易状态": "交易成功"},
        # 余额宝 → 忽略区标路径
        {"交易时间": "2026-10-02 08:00:00", "交易分类": "投资理财", "交易对方": "余额宝",
         "商品说明": "余额宝-收益发放", "收/支": "不计收支", "金额": "0.50", "交易订单号": "A2", "交易状态": "交易成功"},
        # 余额提现 → 忽略区标路径
        {"交易时间": "2026-10-03 09:00:00", "交易分类": "账户存取", "交易对方": "支付宝",
         "商品说明": "余额提现", "收/支": "不计收支", "金额": "500.00", "交易订单号": "A3", "交易状态": "交易成功"},
        # 花呗还款-支付宝侧 → 忽略区标路径
        {"交易时间": "2026-10-04 10:00:00", "交易分类": "信用借还", "交易对方": "花呗",
         "商品说明": "花呗主动还款", "收/支": "不计收支", "金额": "300.00", "交易订单号": "A4", "交易状态": "交易成功"},
        # 真实支出
        {"交易时间": "2026-10-05 11:00:00", "交易分类": "手机充值", "交易对方": "中国移动",
         "商品说明": "话费充值", "收/支": "支出", "金额": "50.00", "交易订单号": "A5", "交易状态": "交易成功"},
        # 与 boc:4 退款配对（双方收入），平台侧主记录
        {"交易时间": "2026-10-04 10:05:00", "交易分类": "退款", "交易对方": "示例网店",
         "商品说明": "订单退款", "收/支": "收入", "金额": "8.80", "交易订单号": "A6", "交易状态": "交易成功"},
        # 未命中规则的不计收支 → 忽略区标「不计收支」
        {"交易时间": "2026-10-09 09:00:00", "交易分类": "其他", "交易对方": "示例平台",
         "商品说明": "资金托管", "收/支": "不计收支", "金额": "88.00", "交易订单号": "A7", "交易状态": "交易成功"},
    ])
    wechat = _rows(WECHAT_COLUMNS, [
        # 零钱充值 → 忽略区标路径；同时与 boc:9 配对（平台侧不动）
        {"交易时间": "2026-10-01 13:00:00", "交易类型": "零钱充值", "交易对方": "/", "商品": "/",
         "收/支": "中性交易", "金额(元)": "200.00", "支付方式": "/", "交易单号": "W1", "当前状态": "支付成功"},
        # 真实支出
        {"交易时间": "2026-10-02 14:00:00", "交易类型": "商户消费", "交易对方": "示例超市",
         "商品": "日常用品", "收/支": "支出", "金额(元)": "66.00", "支付方式": "零钱", "交易单号": "W2", "当前状态": "支付成功"},
        # 零钱提现 → 忽略区标路径
        {"交易时间": "2026-10-03 15:00:00", "交易类型": "零钱提现", "交易对方": "/", "商品": "/",
         "收/支": "中性交易", "金额(元)": "100.00", "支付方式": "/", "交易单号": "W3", "当前状态": "提现成功"},
        # 真实收入
        {"交易时间": "2026-10-04 16:00:00", "交易类型": "转账", "交易对方": "示例朋友",
         "商品": "/", "收/支": "收入", "金额(元)": "30.00", "支付方式": "零钱", "交易单号": "W4", "当前状态": "已收钱"},
    ])
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, boc), "b.csv")
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, alipay), "a.csv")
    db.import_parse_result(conn, SOURCE_WECHAT, _parsed(SOURCE_WECHAT, WECHAT_COLUMNS, wechat), "w.csv")


def _seed_pair_stress(conn):
    """同渠道同日多笔同金额（时间序一对一）与跨日同金额（不配对）的边界样本。"""
    boc = _rows(BOC_COLUMNS, [
        {"date": "2026-10-10", "time": "09:00:00", "tx_type": "支出", "amount": "15.00",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "100.00", "tx_name": "网上快捷支付"},
        {"date": "2026-10-10", "time": "10:30:00", "tx_type": "支出", "amount": "15.00",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "85.00", "tx_name": "网上快捷支付"},
        {"date": "2026-10-11", "time": "09:00:00", "tx_type": "支出", "amount": "7.00",
         "counterparty": "支付宝", "channel": "银企对接", "balance": "78.00", "tx_name": "网上快捷支付"},
    ])
    alipay = _rows(ALIPAY_COLUMNS, [
        {"交易时间": "2026-10-10 09:30:00", "交易分类": "餐饮美食", "交易对方": "示例快餐",
         "商品说明": "午餐", "收/支": "支出", "金额": "15.00", "交易订单号": "B1", "交易状态": "交易成功"},
        {"交易时间": "2026-10-12 09:00:00", "交易分类": "餐饮美食", "交易对方": "示例快餐",
         "商品说明": "晚餐", "收/支": "支出", "金额": "7.00", "交易订单号": "B2", "交易状态": "交易成功"},
    ])
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, boc), "pair-b.csv")
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, alipay), "pair-a.csv")


def _seed_many(conn, n):
    """补 n 条不同日期的收入行与 n 条花呗还款行（两区独立分页测试用）。"""
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
    """规则名与内置预设一致（划转路径按预设规则名映射，设计 §4.1）。"""
    _rule(conn, "余额宝-转入转出", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}])
    _rule(conn, "支付宝余额-提现", SOURCE_ALIPAY, [{"field": "交易分类", "op": "eq", "value": "账户存取"}])
    _rule(conn, "微信零钱-充值提现", SOURCE_WECHAT, [{"field": "交易类型", "op": "in", "value": "零钱充值|零钱提现"}])
    _rule(conn, "花呗还款-支付宝侧", SOURCE_ALIPAY,
          [{"field": "交易分类", "op": "eq", "value": "信用借还"}, {"field": "交易对方", "op": "eq", "value": "花呗"}])
    _rule(conn, "花呗还款-银行侧", SOURCE_BOC, [{"field": "counterparty", "op": "eq", "value": "支付宝-还款"}])
    _rule(conn, "平台提现入账", SOURCE_BOC, [{"field": "tx_name", "op": "eq", "value": "网上快捷提现"}])
    _rule(conn, "基金/平台入账（蚂蚁）", SOURCE_BOC,
          [{"field": "tx_name", "op": "eq", "value": "银联入账"}, {"field": "counterparty", "op": "contains", "value": "蚂蚁"}])


def _all_rows(result):
    """两区结构中的全部行（需 page_size 覆盖全量）。"""
    return list(result["real"]["rows"]) + list(result["ignore"]["rows"])


def _ignore_by_id(result):
    return {r["id"]: r for r in result["ignore"]["rows"]}


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
        assert db.count_rule_hits(conn, rule) == 4
        assert len(db.rule_match_ids(conn, rule)) == 4

        _seed_rules(conn)
        rule_list = db.list_rules(conn)
        hits = {r["name"]: db.count_rule_hits(conn, r) for r in rule_list}
        assert hits["余额宝-转入转出"] == 1
        assert hits["支付宝余额-提现"] == 1
        assert hits["微信零钱-充值提现"] == 2
        assert hits["花呗还款-支付宝侧"] == 1
        assert hits["花呗还款-银行侧"] == 1
        assert hits["平台提现入账"] == 1
        assert hits["基金/平台入账（蚂蚁）"] == 1


# ---------------------------------------------------------------------------
# 总账户统一映射与筛选
# ---------------------------------------------------------------------------

class TestTotalMapping:
    def test_mapping_fields(self, conn):
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = {r["id"]: r for r in _all_rows(result)}
        assert len(by_id) == 20  # 9 BOC + 7 支付宝 + 4 微信
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
        # 收/支筛选统一作用于两区（忽略区按行方向过滤）
        neutral = total.query_rows(conn, directions=["不计收支"])
        assert neutral["real"]["total"] == 0
        assert {r["id"] for r in neutral["ignore"]["rows"]} == {
            "alipay:2", "alipay:3", "alipay:4", "alipay:7", "wechat:1", "wechat:3"}
        real = total.query_rows(conn, directions=["支出", "收入"])
        assert real["real"]["total"] == 8
        assert real["ignore"]["total"] == 6  # 忽略区内方向为收/支的行（镜像 3 + 路径 3）
        assert total.query_rows(conn, q="余额宝")["ignore"]["total"] == 1
        assert total.query_rows(conn, q="余额宝")["real"]["total"] == 0
        assert total.query_rows(conn, q="工资")["real"]["total"] == 1
        assert total.query_rows(conn, date_from="2026-10-03")["real"]["total"] == 5
        assert total.query_rows(conn, date_from="2026-10-03")["ignore"]["total"] == 8
        assert total.query_rows(conn, date_to="2026-10-02")["real"]["total"] == 3
        assert total.query_rows(conn, date_to="2026-10-02")["ignore"]["total"] == 4
        assert total.query_rows(conn, amount_min=100, amount_max=500)["ignore"]["total"] == 7
        assert total.query_rows(conn, sources=["boc"])["real"]["total"] == 3
        assert total.query_rows(conn, sources=["boc"])["ignore"]["total"] == 6
        assert total.query_rows(conn, sources=["alipay", "wechat"])["real"]["total"] == 5
        assert total.query_rows(conn, sources=[])["real"]["total"] == 0
        assert total.query_rows(conn, sources=["unknown"])["real"]["total"] == 0

    def test_sort_and_zone_pagination(self, conn):
        _seed(conn)
        _seed_rules(conn)
        by_time = total.query_rows(conn, sort="datetime", order="desc")
        times = [r["time"] for r in by_time["real"]["rows"]]
        assert times == sorted(times, reverse=True)
        assert by_time["real"]["rows"][0]["time"] == "2026-10-06 10:00:00"

        by_amount = total.query_rows(conn, sort="amount", order="desc")["real"]["rows"]
        assert by_amount[0]["amount"] == "8000.00"

        by_cp = total.query_rows(conn, sort="counterparty", order="asc")["real"]["rows"]
        cps = [r["counterparty"] for r in by_cp if r["counterparty"]]
        assert cps == sorted(cps)

        # 两区独立按行分页，页码互不影响
        _seed_many(conn, 12)
        real_page2 = total.query_rows(conn, real_page=2, page_size=10)
        assert real_page2["real"]["total"] == 20  # 原有 8 + 新增 12（收入）
        assert len(real_page2["real"]["rows"]) == 10
        assert real_page2["real"]["page"] == 2
        assert real_page2["ignore"]["page"] == 1
        ignore_page2 = total.query_rows(conn, ignore_page=2, page_size=10)
        assert ignore_page2["ignore"]["total"] == 24  # 原有 12 + 新增 12（花呗还款）
        assert len(ignore_page2["ignore"]["rows"]) == 10
        assert ignore_page2["ignore"]["page"] == 2
        assert ignore_page2["ignore"]["rows"][0]["time"] == "2026-11-02 10:00:00"
        assert ignore_page2["real"]["page"] == 1


# ---------------------------------------------------------------------------
# 同日同金额配对（独立算法，设计 §3.2）
# ---------------------------------------------------------------------------

class TestPairMirrors:
    def test_pair_algorithm_result(self, conn):
        """配对映射：消费（双方支出）、退款（双方收入）、充值（平台不计收支）同口径。"""
        _seed(conn)
        rows = total.fetch_rows(conn, SOURCES)
        mirrored = total.pair_mirrors(rows)
        assert mirrored == {"boc:1": SOURCE_ALIPAY, "boc:4": SOURCE_ALIPAY, "boc:9": SOURCE_WECHAT}

    def test_mirror_labels(self, conn):
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = _ignore_by_id(result)
        assert by_id["boc:1"]["mark"] == "mirror"
        assert by_id["boc:1"]["mark_label"] == "镜像·支付宝"
        assert by_id["boc:4"]["mark_label"] == "镜像·支付宝"  # 退款同口径
        assert by_id["boc:9"]["mark_label"] == "镜像·微信"  # 与不计收支的充值行配对，方向无关

    def test_pair_one_to_one_by_time_order(self, conn):
        """同日同渠道多笔同金额：时间升序一对一，多出的银行行未配对。"""
        _seed_pair_stress(conn)
        result = total.query_rows(conn, page_size=200)
        ignore_ids = {r["id"]: r for r in result["ignore"]["rows"]}
        real_ids = {r["id"] for r in result["real"]["rows"]}
        assert set(ignore_ids) == {"boc:1"}  # 09:00 银行行配到 09:30 平台行
        assert ignore_ids["boc:1"]["mark_label"] == "镜像·支付宝"
        # 第二笔银行行（10:30）与平台行均留真实区
        assert "boc:2" in real_ids and "alipay:1" in real_ids and "alipay:2" in real_ids

    def test_pair_cross_date_not_paired(self, conn):
        """同渠道日期不同的同金额行不配对（不同组）。"""
        _seed_pair_stress(conn)
        result = total.query_rows(conn, page_size=200)
        real_ids = {r["id"] for r in result["real"]["rows"]}
        assert "boc:3" in real_ids  # 10-11 银行行 vs 10-12 平台行：不配对，留真实区
        assert "alipay:2" in real_ids

    def test_pair_amount_mismatch_and_unknown_counterparty(self, conn):
        """金额不符、对方前缀不匹配支付宝/财付通 → 未配对留真实区（DP2）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        real_ids = {r["id"] for r in result["real"]["rows"]}
        assert "boc:2" in real_ids  # 金额对不上
        assert "boc:6" in real_ids  # 对方前缀不匹配 → 无渠道分组

    def test_pair_platform_row_untouched(self, conn):
        """配对成功的平台行不动：是主记录，留在真实收支区（或按规则进忽略区）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        real_ids = {r["id"] for r in result["real"]["rows"]}
        assert "alipay:1" in real_ids  # 消费主记录
        assert "alipay:6" in real_ids  # 退款主记录
        # 平台侧主记录同时命中忽略规则（零钱充值）→ 进忽略区标路径（§3.2 第 5 条）
        by_id = _ignore_by_id(result)
        assert by_id["wechat:1"]["mark"] == "path"
        assert by_id["wechat:1"]["mark_label"] == "微信 ↔ 银行卡（零钱）"


# ---------------------------------------------------------------------------
# 两区划分与标注优先级
# ---------------------------------------------------------------------------

class TestTotalZones:
    def test_zone_partition(self, conn):
        """未配对且未命中、方向=收/支 → 真实区；镜像 / 命中规则 / 不计收支 → 忽略区。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        assert {r["id"] for r in result["real"]["rows"]} == {
            "boc:2", "boc:3", "boc:6", "alipay:1", "alipay:5", "alipay:6", "wechat:2", "wechat:4"}
        assert {r["id"] for r in result["ignore"]["rows"]} == {
            "boc:1", "boc:4", "boc:5", "boc:7", "boc:8", "boc:9",
            "alipay:2", "alipay:3", "alipay:4", "alipay:7", "wechat:1", "wechat:3"}

    def test_annotation_priority(self, conn):
        """标注优先级：镜像 > 划转路径 > 不计收支（一行同时命中多种时取高者）。"""
        _seed(conn)
        _seed_rules(conn)
        # 自定义规则也命中 boc:1（网上快捷支付）→ 已配对，仍标镜像
        _rule(conn, "渠道行兜底", SOURCE_BOC, [{"field": "tx_name", "op": "eq", "value": "网上快捷支付"}])
        result = total.query_rows(conn, page_size=200)
        by_id = _ignore_by_id(result)
        assert by_id["boc:1"]["mark"] == "mirror"
        assert by_id["boc:1"]["mark_label"] == "镜像·支付宝"
        # 命中规则的不计收支行标路径（路径 > 不计收支）
        assert by_id["alipay:2"]["mark"] == "path"
        assert by_id["alipay:2"]["mark_label"] == "支付宝 ↔ 银行卡（余额宝）"
        # 未命中规则的不计收支行标「不计收支」
        assert by_id["alipay:7"]["mark"] == "neutral"
        assert by_id["alipay:7"]["mark_label"] == "不计收支"

    def test_transfer_path_labels(self, conn):
        """路径标注按「对端 + 行方向 + 行来源」组合（设计 §4.1）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = _ignore_by_id(result)
        # 收入 = 对端 → 本端
        assert by_id["boc:8"]["mark_label"] == "支付宝 → 银行卡"
        # 支出 = 本端 → 对端
        assert by_id["boc:5"]["mark_label"] == "银行卡 → 支付宝（花呗还款）"
        assert by_id["boc:7"]["mark_label"] == "银行卡 → 支付宝"  # 对端按对方前缀推断
        # 不计收支 = 本端 ↔ 对端
        assert by_id["alipay:2"]["mark_label"] == "支付宝 ↔ 银行卡（余额宝）"
        assert by_id["alipay:3"]["mark_label"] == "支付宝 ↔ 银行卡（余额）"
        assert by_id["alipay:4"]["mark_label"] == "支付宝 ↔ 花呗（还款）"
        assert by_id["wechat:1"]["mark_label"] == "微信 ↔ 银行卡（零钱）"
        assert by_id["wechat:3"]["mark_label"] == "微信 ↔ 银行卡（零钱）"
        # 路径行携带命中规则名（tooltip 用）
        assert by_id["alipay:2"]["rule_names"] == ["余额宝-转入转出"]

    def test_custom_rule_ignored_label(self, conn):
        """自定义规则无法确定对端 → 标注「忽略（规则名）」。"""
        _seed(conn)
        _rule(conn, "我的自定义规则", SOURCE_WECHAT, [{"field": "交易类型", "op": "eq", "value": "商户消费"}])
        result = total.query_rows(conn, page_size=200)
        by_id = _ignore_by_id(result)
        assert by_id["wechat:2"]["mark"] == "path"
        assert by_id["wechat:2"]["mark_label"] == "忽略（我的自定义规则）"
        assert by_id["wechat:2"]["rule_names"] == ["我的自定义规则"]
        assert "wechat:2" not in {r["id"] for r in result["real"]["rows"]}

    def test_disabled_rule_not_applied(self, conn):
        _seed(conn)
        _rule(conn, "停用规则", SOURCE_ALIPAY, [{"field": "商品说明", "op": "starts", "value": "余额宝-"}],
              enabled=False)
        result = total.query_rows(conn, page_size=200)
        # 停用规则不生效：余额宝行未命中且方向=不计收支，标「不计收支」进忽略区
        by_id = _ignore_by_id(result)
        assert by_id["alipay:2"]["mark"] == "neutral"
        assert result["real"]["total"] == 11  # 无启用规则时的真实区（收入 4 + 支出 7）

    def test_zone_identity_stable_across_filters(self, conn):
        """分区与标注身份在全量数据上计算：筛选只决定显示（设计 §3.1）。"""
        _seed(conn)
        _seed_rules(conn)
        # 关键词只命中银行行，平台行被筛掉：银行行身份仍为镜像
        only_bank = total.query_rows(conn, q="网上快捷退款", page_size=200)
        assert {r["id"] for r in only_bank["ignore"]["rows"]} == {"boc:4"}
        assert only_bank["ignore"]["rows"][0]["mark"] == "mirror"
        # 来源多选只留 BOC：身份仍按全量数据计算
        boc_only = total.query_rows(conn, sources=["boc"], page_size=200)
        by_id = _ignore_by_id(boc_only)
        assert by_id["boc:1"]["mark"] == "mirror"
        assert by_id["boc:9"]["mark"] == "mirror"
        assert "boc:2" in {r["id"] for r in boc_only["real"]["rows"]}  # 未配对留真实区

    def test_empty_zones(self, conn):
        """空区返回空列表（前端显示「该区无记录」）。"""
        _seed(conn)
        _seed_rules(conn)
        result = total.query_rows(conn, directions=["收入"], page_size=200)
        assert result["real"]["total"] == 3
        assert {r["id"] for r in result["real"]["rows"]} == {"boc:3", "alipay:6", "wechat:4"}
        assert result["ignore"]["total"] == 2  # 忽略区内方向=收入的行（退款镜像）
        none = total.query_rows(conn, sources=[])
        assert none["real"]["rows"] == [] and none["ignore"]["rows"] == []


class TestTotalSummary:
    def test_two_zone_metrics(self, conn):
        """真实收入 / 真实支出 / 净收支 / 真实笔数 + 忽略区细分。"""
        _seed(conn)
        _seed_rules(conn)
        s = total.query_summary(conn)
        assert s["income"] == {"count": 3, "sum": 8038.80}  # 8000 + 8.80 + 30
        assert s["expense"] == {"count": 5, "sum": 210.80}  # 20 + 66 + 8.80 + 50 + 66
        assert s["net"] == 7828.00
        assert s["count"] == 8
        assert s["ignore"] == {"count": 12, "mirror": 3, "transfer": 8, "neutral": 1}

    def test_summary_follows_filters(self, conn):
        _seed(conn)
        _seed_rules(conn)
        s = total.query_summary(conn, date_from="2026-10-04")
        assert s["income"] == {"count": 2, "sum": 38.80}  # 8.80 + 30
        assert s["expense"] == {"count": 2, "sum": 116.00}  # 66 + 50
        assert s["ignore"] == {"count": 6, "mirror": 1, "transfer": 4, "neutral": 1}
        # 收/支筛选统一作用于两区口径
        d = total.query_summary(conn, directions=["支出"])
        assert d["income"] == {"count": 0, "sum": 0.0}
        assert d["expense"] == {"count": 5, "sum": 210.80}
        assert d["ignore"] == {"count": 4, "mirror": 2, "transfer": 2, "neutral": 0}

    def test_summary_without_rules(self, conn):
        """无规则时：配对独立生效，未命中的不计收支行标「不计收支」，收/支未命中进真实区。"""
        _seed(conn)
        s = total.query_summary(conn)
        assert s["income"] == {"count": 4, "sum": 8538.80}  # 8000 + 500 + 8.80 + 30
        assert s["expense"] == {"count": 7, "sum": 3310.80}  # 20 + 3000 + 66 + 100 + 8.80 + 50 + 66
        assert s["count"] == 11
        assert s["ignore"] == {"count": 9, "mirror": 3, "transfer": 0, "neutral": 6}
