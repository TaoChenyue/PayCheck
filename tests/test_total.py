"""总账户单表口径测试：统一映射、有效属性（覆盖 > 原始方向）、方向约束、
单表分页、计入口径汇总与 counted/tags 筛选维度（TCY-27）"""

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
    """构造三源样本（与真实数据无关）：真实收支、不计收支/中性、划转类场景。"""
    boc = _rows(BOC_COLUMNS, [
        # 真实支出
        {"date": "2026-10-01", "time": "10:00:00", "tx_type": "支出", "amount": "8.80",
         "counterparty": "示例面馆", "channel": "银企对接", "balance": "100.00", "tx_name": "网上快捷支付"},
        # 金额对不上的渠道行 → 仍为计入支出（无任何自动识别）
        {"date": "2026-10-02", "time": "10:00:00", "tx_type": "支出", "amount": "20.00",
         "counterparty": "财付通", "channel": "银企对接", "balance": "80.00", "tx_name": "网上快捷支付"},
        # 真实收入
        {"date": "2026-10-03", "time": "09:00:00", "tx_type": "收入", "amount": "8000.00",
         "counterparty": "示例公司", "channel": "银企对接", "balance": "8080.00", "tx_name": "代发工资", "memo": "10月工资"},
        # 划转类支出（余额宝转入的银行侧）→ 计入，用户手动设为不计
        {"date": "2026-10-04", "time": "11:00:00", "tx_type": "支出", "amount": "500.00",
         "counterparty": "蚂蚁基金", "channel": "银企对接", "balance": "7580.00", "tx_name": "快捷支付"},
        # 划转类收入（基金入账）→ 计入，用户手动设为不计
        {"date": "2026-10-05", "time": "12:00:00", "tx_type": "收入", "amount": "300.00",
         "counterparty": "财付通", "channel": "银企对接", "balance": "7880.00", "tx_name": "银联入账"},
    ])
    alipay = _rows(ALIPAY_COLUMNS, [
        # 余额宝收益 → 不计收支，默认不计
        {"交易时间": "2026-10-02 08:00:00", "交易分类": "投资理财", "交易对方": "余额宝",
         "商品说明": "余额宝-收益发放", "收/支": "不计收支", "金额": "0.50", "交易订单号": "A1", "交易状态": "交易成功"},
        # 余额提现 → 不计收支，默认不计
        {"交易时间": "2026-10-03 09:00:00", "交易分类": "账户存取", "交易对方": "支付宝",
         "商品说明": "余额提现", "收/支": "不计收支", "金额": "500.00", "交易订单号": "A2", "交易状态": "交易成功"},
        # 真实支出
        {"交易时间": "2026-10-04 10:00:00", "交易分类": "手机充值", "交易对方": "中国移动",
         "商品说明": "话费充值", "收/支": "支出", "金额": "50.00", "交易订单号": "A3", "交易状态": "交易成功"},
        # 退款收入
        {"交易时间": "2026-10-05 10:05:00", "交易分类": "退款", "交易对方": "示例网店",
         "商品说明": "订单退款", "收/支": "收入", "金额": "8.80", "交易订单号": "A4", "交易状态": "交易成功"},
        # 中性收入（金额为正）→ 默认不计，可改为计入按符号进收入
        {"交易时间": "2026-10-06 09:00:00", "交易分类": "其他", "交易对方": "示例平台",
         "商品说明": "资金托管", "收/支": "不计收支", "金额": "88.00", "交易订单号": "A5", "交易状态": "交易成功"},
    ])
    wechat = _rows(WECHAT_COLUMNS, [
        # 零钱充值 → 中性交易，默认不计
        {"交易时间": "2026-10-01 13:00:00", "交易类型": "零钱充值", "交易对方": "/", "商品": "/",
         "收/支": "中性交易", "金额(元)": "200.00", "支付方式": "/", "交易单号": "W1", "当前状态": "支付成功"},
        # 真实支出
        {"交易时间": "2026-10-02 14:00:00", "交易类型": "商户消费", "交易对方": "示例超市",
         "商品": "日常用品", "收/支": "支出", "金额(元)": "66.00", "支付方式": "零钱", "交易单号": "W2", "当前状态": "支付成功"},
        # 真实收入
        {"交易时间": "2026-10-03 15:00:00", "交易类型": "转账", "交易对方": "示例朋友",
         "商品": "/", "收/支": "收入", "金额(元)": "30.00", "支付方式": "零钱", "交易单号": "W3", "当前状态": "已收钱"},
    ])
    db.import_parse_result(conn, SOURCE_BOC, _parsed(SOURCE_BOC, BOC_COLUMNS, boc), "b.csv")
    db.import_parse_result(conn, SOURCE_ALIPAY, _parsed(SOURCE_ALIPAY, ALIPAY_COLUMNS, alipay), "a.csv")
    db.import_parse_result(conn, SOURCE_WECHAT, _parsed(SOURCE_WECHAT, WECHAT_COLUMNS, wechat), "w.csv")


def _all_ids(result):
    return {r["id"] for r in result["rows"]}


def _by_id(result):
    return {r["id"]: r for r in result["rows"]}


# ---------------------------------------------------------------------------
# 总账户统一映射与筛选
# ---------------------------------------------------------------------------

class TestTotalMapping:
    def test_mapping_fields(self, conn):
        _seed(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = _by_id(result)
        assert len(by_id) == 13  # 5 BOC + 5 支付宝 + 3 微信
        boc_pay = by_id["boc:1"]
        assert boc_pay["time"] == "2026-10-01 10:00:00"
        assert boc_pay["direction"] == "支出"
        assert boc_pay["counterparty"] == "示例面馆"
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
        assert by_id["alipay:1"]["raw"]["商品说明"] == "余额宝-收益发放"

    def test_filters(self, conn):
        _seed(conn)
        assert total.query_rows(conn, directions=["不计收支"])["total"] == 4
        assert total.query_rows(conn, directions=["支出", "收入"])["total"] == 9
        assert total.query_rows(conn, q="余额宝")["total"] == 1
        assert total.query_rows(conn, q="工资")["total"] == 1
        assert total.query_rows(conn, date_from="2026-10-03")["total"] == 8
        assert total.query_rows(conn, date_to="2026-10-02")["total"] == 5
        assert total.query_rows(conn, amount_min=100, amount_max=500)["total"] == 4
        assert total.query_rows(conn, sources=["boc"])["total"] == 5
        assert total.query_rows(conn, sources=["alipay", "wechat"])["total"] == 8
        assert total.query_rows(conn, sources=[])["total"] == 0
        assert total.query_rows(conn, sources=["unknown"])["total"] == 0

    def test_sort_and_single_table_pagination(self, conn):
        _seed(conn)
        by_time = total.query_rows(conn, sort="datetime", order="desc", page_size=200)
        times = [r["time"] for r in by_time["rows"]]
        assert times == sorted(times, reverse=True)
        assert by_time["rows"][0]["time"] == "2026-10-06 09:00:00"

        by_amount = total.query_rows(conn, sort="amount", order="desc", page_size=200)
        assert by_amount["rows"][0]["amount"] == "8000.00"

        by_cp = total.query_rows(conn, sort="counterparty", order="asc", page_size=200)
        cps = [r["counterparty"] for r in by_cp["rows"] if r["counterparty"]]
        assert cps == sorted(cps)

        # 标准 page 分页（与渠道页签同一套，page_size 为白名单档位）
        page1 = total.query_rows(conn, page=1, page_size=10)
        assert page1["total"] == 13
        assert len(page1["rows"]) == 10
        assert page1["page"] == 1
        page2 = total.query_rows(conn, page=2, page_size=10)
        assert len(page2["rows"]) == 3
        assert page2["page"] == 2
        assert page1["rows"][0]["id"] != page2["rows"][0]["id"]


# ---------------------------------------------------------------------------
# 有效属性（覆盖 > 原始方向）与方向约束
# ---------------------------------------------------------------------------

class TestEffectiveCounted:
    def test_default_counted(self, conn):
        """无覆盖时：收入/支出 → 计入；不计收支/中性 → 不计。无任何自动逻辑。"""
        _seed(conn)
        result = total.query_rows(conn, page_size=200)
        by_id = _by_id(result)
        assert by_id["boc:1"]["counted"] is True
        assert by_id["boc:3"]["counted"] is True
        assert by_id["alipay:3"]["counted"] is True
        assert by_id["wechat:2"]["counted"] is True
        assert by_id["alipay:1"]["counted"] is False
        assert by_id["alipay:2"]["counted"] is False
        assert by_id["wechat:1"]["counted"] is False

    def test_override_priority(self, conn):
        """覆盖存在 → 以覆盖为准（覆盖 > 原始方向）。"""
        _seed(conn)
        db.set_overrides(conn, [("boc", 3)], 0)  # 收入 → 不计
        db.set_overrides(conn, [("alipay", 1)], 1)  # 不计收支 → 计入
        result = total.query_rows(conn, page_size=200)
        by_id = _by_id(result)
        assert by_id["boc:3"]["counted"] is False
        assert by_id["alipay:1"]["counted"] is True
        # 未覆盖行不受影响
        assert by_id["boc:1"]["counted"] is True
        assert by_id["alipay:2"]["counted"] is False

    def test_override_upsert_and_revert(self, conn):
        """覆盖可反复改写（改回原状态即再写一次），稀疏旁表不丢。"""
        _seed(conn)
        db.set_overrides(conn, [("boc", 1)], 0)
        assert db.fetch_overrides(conn) == {"boc:1": 0}
        db.set_overrides(conn, [("boc", 1)], 1)  # 改回计入
        result = total.query_rows(conn, page_size=200)
        assert _by_id(result)["boc:1"]["counted"] is True

    def test_direction_never_reverses(self, conn):
        """方向约束铁律：属性只改计入/不计，行的方向永远不变。"""
        _seed(conn)
        db.set_overrides(conn, [("boc", 3)], 0)  # 收入行设为不计
        db.set_overrides(conn, [("alipay", 1)], 1)  # 中性行设为计入
        result = total.query_rows(conn, page_size=200)
        by_id = _by_id(result)
        assert by_id["boc:3"]["direction"] == "收入"  # 不反向
        assert by_id["alipay:1"]["direction"] == "不计收支"
        # 中性行计入方向按金额符号定（正=收入）
        s = total.query_summary(conn)
        assert s["income"] == {"count": 4, "sum": 339.30}  # 300 + 8.80 + 0.50 + 30（工资 8000 已设为不计）
        assert s["expense"]["count"] == 5

    def test_neutral_counted_direction_by_sign(self, conn):
        """中性行计入后：金额为正进收入、为负进支出（汇总口径，方向列不变）。"""
        _seed(conn)
        db.set_overrides(conn, [("alipay", 5)], 1)  # +88.00 中性 → 收入
        db.set_overrides(conn, [("wechat", 1)], 1)  # 中性充值（金额为正）→ 收入
        s = total.query_summary(conn)
        income_ids = {"boc:3", "boc:5", "alipay:4", "alipay:5", "wechat:1", "wechat:3"}
        assert s["income"]["count"] == 6  # 8000 + 300 + 8.80 + 88 + 200 + 30
        assert s["income"]["sum"] == 8626.80
        assert s["count"] == 11  # 计入 11 笔


# ---------------------------------------------------------------------------
# counted / tags 筛选维度
# ---------------------------------------------------------------------------

class TestCountedTagFilters:
    def test_counted_filter(self, conn):
        _seed(conn)
        assert total.query_rows(conn, counted={"0"}, page_size=200)["total"] == 4
        assert total.query_rows(conn, counted={"1"}, page_size=200)["total"] == 9
        # 空集合（属性两档全不勾选）→ 匹配 0 行
        assert total.query_rows(conn, counted=set(), page_size=200)["total"] == 0
        # None → 不过滤
        assert total.query_rows(conn, page_size=200)["total"] == 13

    def test_counted_filter_follows_overrides(self, conn):
        _seed(conn)
        db.set_overrides(conn, [("boc", 3)], 0)
        assert total.query_rows(conn, counted={"0"}, page_size=200)["total"] == 5
        assert total.query_rows(conn, counted={"1"}, page_size=200)["total"] == 8

    def test_tag_filter_or_semantics(self, conn):
        """标签多选 OR 语义：命中任一勾选标签即显示；无标签行仅全部未勾选时显示。"""
        _seed(conn)
        travel = db.create_tag_group(conn, "差旅")
        dining = db.create_tag_group(conn, "餐饮")
        db.apply_tags(conn, [("boc", 3)], [travel["id"]], "add")
        db.apply_tags(conn, [("boc", 1)], [dining["id"]], "add")
        db.apply_tags(conn, [("alipay", 4)], [travel["id"], dining["id"]], "add")

        assert total.query_rows(conn, tags=[str(travel["id"])], page_size=200)["total"] == 2
        assert total.query_rows(conn, tags=[str(dining["id"])], page_size=200)["total"] == 2
        # OR：任一命中（alipay:4 两标签都打仍计 1 行）
        assert total.query_rows(conn, tags=[str(travel["id"]), str(dining["id"])], page_size=200)["total"] == 3
        # 无标签行仅在全部未勾选时显示
        assert total.query_rows(conn, tags=[], page_size=200)["total"] == 13
        assert total.query_rows(conn, tags=None, page_size=200)["total"] == 13


# ---------------------------------------------------------------------------
# 计入口径汇总
# ---------------------------------------------------------------------------

class TestTotalSummary:
    def test_counted_scope_metrics(self, conn):
        """收入合计 / 支出合计 / 净收支 / 计入笔数 + 不计入笔数。"""
        _seed(conn)
        s = total.query_summary(conn)
        assert s["income"] == {"count": 4, "sum": 8338.80}  # 8000 + 300 + 8.80 + 30
        assert s["expense"] == {"count": 5, "sum": 644.80}  # 8.80 + 20 + 500 + 50 + 66
        assert s["net"] == 7694.00
        assert s["count"] == 9
        assert s["not_counted"] == 4

    def test_summary_follows_overrides_and_filters(self, conn):
        _seed(conn)
        db.set_overrides(conn, [("boc", 4)], 0)  # 划转支出 500 不计
        db.set_overrides(conn, [("boc", 5)], 0)  # 划转收入 300 不计
        s = total.query_summary(conn)
        assert s["income"] == {"count": 3, "sum": 8038.80}  # 8000 + 8.80 + 30
        assert s["expense"] == {"count": 4, "sum": 144.80}  # 8.80 + 20 + 50 + 66
        assert s["net"] == 7894.00
        assert s["count"] == 7
        assert s["not_counted"] == 6

        d = total.query_summary(conn, directions=["支出"])
        assert d["income"] == {"count": 0, "sum": 0.0}
        assert d["expense"] == {"count": 4, "sum": 144.80}
        assert d["not_counted"] == 1

        c = total.query_summary(conn, counted={"0"})
        assert c["income"] == {"count": 0, "sum": 0.0}
        assert c["expense"] == {"count": 0, "sum": 0.0}
        assert c["count"] == 0
        assert c["not_counted"] == 6

    def test_neutral_counted_summary(self, conn):
        """不计收支行默认不计；手动计入后按金额符号进收入/支出。"""
        _seed(conn)
        db.set_overrides(conn, [("alipay", 5)], 1)  # +88.00 → 收入
        db.set_overrides(conn, [("alipay", 2)], 1)  # 余额提现 500（金额为正）→ 收入
        s = total.query_summary(conn)
        assert s["income"] == {"count": 6, "sum": 8926.80}  # 8338.80 + 88 + 500
        assert s["net"] == 8282.00
        assert s["not_counted"] == 2


# ---------------------------------------------------------------------------
# 批量 scope 解析（overrides / tags apply 共用）
# ---------------------------------------------------------------------------

class TestResolveScope:
    def test_ids_scope(self, conn):
        _seed(conn)
        keys = total.resolve_scope_rows(conn, {"scope": "ids", "ids": ["boc:1", "alipay:3"]})
        assert keys == [("boc", 1), ("alipay", 3)]
        # 不存在的行自动跳过
        keys = total.resolve_scope_rows(conn, {"scope": "ids", "ids": ["boc:999"]})
        assert keys == []

    def test_ids_scope_invalid_format(self, conn):
        _seed(conn)
        for bad in ["boc", "boc:x", "xx:1", ":1"]:
            with pytest.raises(db.DataError):
                total.resolve_scope_rows(conn, {"scope": "ids", "ids": [bad]})

    def test_filter_scope(self, conn):
        """filter scope 作用于整个筛选结果（含 counted/tags 维度），不只当前页。"""
        _seed(conn)
        keys = total.resolve_scope_rows(conn, {
            "scope": "filter",
            "filters": {"directions": ["不计收支"]},
        })
        assert keys == [("alipay", 1), ("alipay", 2), ("alipay", 5), ("wechat", 1)]
        # counted 维度按当前有效属性求值
        db.set_overrides(conn, [("boc", 3)], 0)
        keys = total.resolve_scope_rows(conn, {
            "scope": "filter",
            "filters": {"counted": ["0"]},
        })
        assert ("boc", 3) in keys
        assert ("boc", 1) not in keys
        # 空 counted（属性两档全不勾选）→ 0 行
        keys = total.resolve_scope_rows(conn, {"scope": "filter", "filters": {"counted": []}})
        assert keys == []

    def test_invalid_scope(self, conn):
        _seed(conn)
        with pytest.raises(db.DataError):
            total.resolve_scope_rows(conn, {"scope": "xx"})
