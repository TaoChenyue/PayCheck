"""BOC 重复账单自动不计（TCY-52 方案 A）测试：匹配核心单测 + API 端到端

覆盖：主规则命中/不命中、贪心一对一、歧义跳过、中性行/非人民币/无 time 跳过、
已有覆盖尊重与幂等、金额符号与千分位、导入自动标记、检测/应用接口、可逆性。
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from paycheck_workbench import auto_exclude, db
from paycheck_workbench.parsing import parse_file
from paycheck_workbench.server import serve

BOC_HEADER = "date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank"
ALIPAY_HEADER = "交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注"
WECHAT_HEADER = "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注"

HEADERS = {"boc": BOC_HEADER, "alipay": ALIPAY_HEADER, "wechat": WECHAT_HEADER}


def import_rows(conn, source, rows, name="t.csv"):
    """CSV 文本 → 解析 → 入库（与真实导入路径一致）。"""
    data = (HEADERS[source] + "\r\n" + "\r\n".join(rows) + "\r\n").encode(
        "utf-8-sig" if source == "boc" else "utf-8"
    )
    parsed = parse_file(source, name, data)
    return db.import_parse_result(conn, source, parsed, name)


def boc_row(day, time, amount, counterparty="示例店", direction="支出", currency="人民币"):
    return f"{day},{time},{direction},{amount},{counterparty},银企对接,100.00,,快捷支付,{currency},,,"


def alipay_row(day_time, amount, direction="支出", order="A1", counterparty="示例店"):
    return f"{day_time},餐饮美食,{counterparty},,商品,{direction},{amount},,交易成功,{order},,"


def wechat_row(day_time, amount, direction="支出", order="W1", counterparty="示例店"):
    return f"{day_time},商户消费,{counterparty},商品,{direction},{amount},零钱,支付成功,{order},,"


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "core.db"
    db.init_db(db_path)
    connection = db.connect(db_path)
    yield connection
    connection.close()


class TestMatchCore:
    def test_unique_hit_exact_minute_amount_direction(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        result = auto_exclude.scan(conn)
        assert len(result["matches"]) == 1
        match = result["matches"][0]
        assert match["boc"]["id"] == "boc:1"
        assert match["other"] == {
            "id": "alipay:1", "source": "alipay", "time": "2026-10-01 10:00:00",
            "amount": "8.80", "direction": "支出", "counterparty": "示例店", "summary": "商品",
        }
        assert result["ambiguous"] == []

    def test_minute_mismatch_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:01:00", "8.80")])
        result = auto_exclude.run_auto_exclude(conn)
        assert result["auto_excluded"] == 0
        assert result["matches"] == []

    def test_amount_mismatch_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.81")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_direction_mismatch_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80", direction="支出")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80", direction="收入")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_greedy_one_candidate_consumed_once(self, conn):
        """多对一：同一分钟+金额+方向的两个 BOC 行，只消费唯一的对方候选一行。"""
        import_rows(conn, "boc", [
            boc_row("2026-10-01", "10:00:00", "7.77", counterparty="A店"),
            boc_row("2026-10-01", "10:00:00", "7.77", counterparty="B店"),
        ])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "7.77", counterparty="A店")])
        result = auto_exclude.run_auto_exclude(conn)
        assert result["auto_excluded"] == 1
        assert [m["boc"]["id"] for m in result["matches"]] == ["boc:1"]
        assert db.fetch_overrides(conn)["boc:1"] == 0
        assert "boc:2" not in db.fetch_overrides(conn)

    def test_ambiguous_multiple_candidates_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "6.00")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "6.00")])
        import_rows(conn, "wechat", [wechat_row("2026-10-01 10:00:00", "6.00")])
        result = auto_exclude.scan(conn)
        assert result["matches"] == []
        assert len(result["ambiguous"]) == 1
        amb = result["ambiguous"][0]
        assert amb["boc"]["id"] == "boc:1"
        assert {c["source"] for c in amb["candidates"]} == {"alipay", "wechat"}
        # 歧义不自动标记
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_neutral_rows_excluded(self, conn):
        """银行侧真实动账（余额宝转入）不与支付宝中性行匹配。"""
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "10.00", counterparty="余额宝")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "10.00", direction="不计收支", counterparty="余额宝")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_wechat_neutral_excluded(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "5.00")])
        import_rows(conn, "wechat", [wechat_row("2026-10-01 10:00:00", "5.00", direction="中性交易")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_non_rmb_currency_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80", currency="美元")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_boc_without_time_skip(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0

    def test_existing_override_never_overwritten(self, conn):
        """用户手动标记（counted=0/1）的行跳过；改回计入后不再被自动覆盖。"""
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        db.set_overrides(conn, [("boc", 1)], 1)  # 用户改回计入
        result = auto_exclude.run_auto_exclude(conn)
        assert result["auto_excluded"] == 0
        assert db.fetch_overrides(conn)["boc:1"] == 1  # 用户设置不被覆盖

    def test_idempotent_rescan(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 1
        assert auto_exclude.run_auto_exclude(conn)["auto_excluded"] == 0  # 已有覆盖跳过

    def test_amount_symbols_and_thousands(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", '"1,234.56"')])
        import_rows(conn, "alipay", [alipay_row("2026-10-01 10:00:00", '"￥1,234.56"')])
        result = auto_exclude.run_auto_exclude(conn)
        assert result["auto_excluded"] == 1
        assert db.fetch_overrides(conn)["boc:1"] == 0

    def test_wechat_source_matches(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        import_rows(conn, "wechat", [wechat_row("2026-10-01 10:00:00", "8.80")])
        result = auto_exclude.run_auto_exclude(conn)
        assert result["auto_excluded"] == 1
        assert result["matches"][0]["other"]["source"] == "wechat"

    def test_apply_matches_rejects_non_boc(self, conn):
        with pytest.raises(db.DataError, match="仅支持 BOC 行"):
            auto_exclude.apply_matches(conn, ["alipay:1"])
        with pytest.raises(db.DataError, match="行标识无效"):
            auto_exclude.apply_matches(conn, ["boc:abc"])

    def test_apply_matches_writes_counted_zero(self, conn):
        import_rows(conn, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        assert auto_exclude.apply_matches(conn, ["boc:1"]) == 1
        assert db.fetch_overrides(conn)["boc:1"] == 0


@pytest.fixture()
def base_url(tmp_path):
    db_path = tmp_path / "srv.db"
    thread = threading.Thread(
        target=serve, kwargs={"db_path": db_path, "port": 8898}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8898"
    # 守护线程随进程退出，无需关闭


def _get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _send_json(method, url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _confirm(base_url, source, rows):
    data = (HEADERS[source] + "\r\n" + "\r\n".join(rows) + "\r\n").encode(
        "utf-8-sig" if source == "boc" else "utf-8"
    )
    return _post(base_url + "/api/import/confirm", data, {
        "Content-Type": "application/octet-stream", "X-Source": source, "X-Filename": "t.csv",
    })


class TestAutoExcludeApi:
    def test_import_alipay_then_boc_backfills(self, base_url):
        """先导支付宝后导 BOC：BOC 导入确认时补标（与导入顺序无关）。"""
        res = _confirm(base_url, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert res["ok"] and res["auto_excluded"] == 0  # 无 BOC 行可标
        res = _confirm(base_url, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        assert res["ok"] and res["auto_excluded"] == 1

    def test_import_boc_then_alipay_marks_total(self, base_url):
        """先导 BOC 后导支付宝：导入即自动标记，总账户行计入属性与汇总同步变化。"""
        res = _confirm(base_url, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        assert res["auto_excluded"] == 0
        res = _confirm(base_url, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert res["auto_excluded"] == 1

        rows = _get(base_url + "/api/rows?source=total")
        by_id = {r["id"]: r for r in rows["rows"]}
        assert by_id["boc:1"]["counted"] is False
        assert by_id["alipay:1"]["counted"] is True  # 只作用于 BOC 行，支付宝行照常计入
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["expense"] == {"count": 1, "sum": 8.80}
        assert summary["count"] == 1
        assert summary["not_counted"] == 1

    def test_detect_and_apply_endpoints(self, base_url, monkeypatch):
        """工具栏「检测重复」：dry-run 扫描 → 按 ids 应用 → 总账户生效。

        关闭自动开关后导入（模拟历史数据/开关关闭场景），手动扫描应能发现
        并应用标记。
        """
        monkeypatch.setattr(auto_exclude, "AUTO_EXCLUDE_ENABLED", False)
        res = _confirm(base_url, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        assert res["auto_excluded"] == 0
        res = _confirm(base_url, "alipay", [alipay_row("2026-10-01 10:00:00", "8.80")])
        assert res["auto_excluded"] == 0  # 开关关闭：导入不自动标记

        scan = _send_json("POST", base_url + "/api/total/detect-duplicates", {})
        assert scan["ok"]
        assert [m["boc"]["id"] for m in scan["matches"]] == ["boc:1"]

        res = _send_json("POST", base_url + "/api/total/apply-auto-exclude", {"ids": ["boc:1"]})
        assert res["ok"] and res["updated"] == 1
        rows = _get(base_url + "/api/rows?source=total")
        assert next(r for r in rows["rows"] if r["id"] == "boc:1")["counted"] is False

    def test_apply_endpoint_rejects_non_boc(self, base_url):
        _confirm(base_url, "boc", [boc_row("2026-10-01", "10:00:00", "8.80")])
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send_json("POST", base_url + "/api/total/apply-auto-exclude", {"ids": ["alipay:1"]})
        assert excinfo.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send_json("POST", base_url + "/api/total/apply-auto-exclude", {"ids": []})
        assert excinfo.value.code == 400

    def test_detect_reports_ambiguous(self, base_url):
        """先导支付宝与微信后导 BOC：BOC 导入时同距双候选为歧义，不自动标记、进预览。"""
        _confirm(base_url, "alipay", [alipay_row("2026-10-01 10:00:00", "6.00")])
        _confirm(base_url, "wechat", [wechat_row("2026-10-01 10:00:00", "6.00")])
        res = _confirm(base_url, "boc", [boc_row("2026-10-01", "10:00:00", "6.00")])
        assert res["auto_excluded"] == 0  # 歧义不自动标记

        scan = _send_json("POST", base_url + "/api/total/detect-duplicates", {})
        assert scan["matches"] == []
        assert len(scan["ambiguous"]) == 1
        assert scan["ambiguous"][0]["boc"]["id"] == "boc:1"
        assert {c["source"] for c in scan["ambiguous"][0]["candidates"]} == {"alipay", "wechat"}
