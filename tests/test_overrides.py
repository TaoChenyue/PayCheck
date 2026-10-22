"""收支属性批量 API 端到端测试：ids / filter 两种 scope、方向约束铁律（TCY-27）"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from paycheck_workbench.server import serve


@pytest.fixture()
def base_url(tmp_path):
    db_path = tmp_path / "srv.db"
    thread = threading.Thread(
        target=serve, kwargs={"db_path": db_path, "port": 8897}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8897"
    # 守护线程随进程退出，无需关闭


def _get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _send(method, url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _seed(base_url):
    boc = ("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank\r\n"
           + "\r\n".join([
               "2026-10-01,10:00:00,支出,8.80,示例面馆,银企对接,100.00,,网上快捷支付,人民币,,,",
               "2026-10-02,10:00:00,收入,3000.00,示例公司,银企对接,3100.00,,代发工资,人民币,,,",
           ]) + "\r\n").encode("utf-8-sig")
    alipay = ("交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注\r\n"
              + "\r\n".join([
                  "2026-10-01 12:00:00,餐饮美食,示例面馆,,牛肉面,支出,8.80,,交易成功,A1,,",
                  "2026-10-02 08:00:00,投资理财,余额宝,,余额宝-收益发放,不计收支,0.50,,交易成功,A2,,",
              ]) + "\r\n").encode("utf-8")
    for source, body in (("boc", boc), ("alipay", alipay)):
        req = urllib.request.Request(base_url + "/api/import/confirm", data=body, headers={
            "Content-Type": "application/octet-stream", "X-Source": source, "X-Filename": "t.csv",
        })
        with urllib.request.urlopen(req) as resp:
            json.loads(resp.read().decode("utf-8"))


class TestOverridesApi:
    def test_ids_scope_set_and_reflect(self, base_url):
        _seed(base_url)
        res = _send("PUT", base_url + "/api/total/overrides",
                    {"scope": "ids", "counted": 0, "ids": ["boc:1", "alipay:1"]})
        assert res["ok"]
        assert res["updated"] == 2
        rows = _get(base_url + "/api/rows?source=total")
        by_id = {r["id"]: r for r in rows["rows"]}
        assert by_id["boc:1"]["counted"] is False
        assert by_id["alipay:1"]["counted"] is False
        assert by_id["boc:2"]["counted"] is True  # 未覆盖行不受影响
        # 汇总随属性修改即时变化：两条支出不再计入
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["expense"] == {"count": 0, "sum": 0.0}
        assert summary["count"] == 1
        assert summary["not_counted"] == 3

    def test_ids_scope_unknown_rows_skipped(self, base_url):
        _seed(base_url)
        res = _send("PUT", base_url + "/api/total/overrides",
                    {"scope": "ids", "counted": 0, "ids": ["boc:999"]})
        assert res["updated"] == 0

    def test_filter_scope_acts_on_whole_filter_result(self, base_url):
        """filter scope 作用于整个筛选结果，不只当前页。"""
        _seed(base_url)
        res = _send("PUT", base_url + "/api/total/overrides",
                    {"scope": "filter", "counted": 0, "filters": {"directions": ["支出"]}})
        assert res["ok"]
        assert res["updated"] == 2  # 两条支出行全部设为不计
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["expense"] == {"count": 0, "sum": 0.0}
        assert summary["income"] == {"count": 1, "sum": 3000.00}

    def test_direction_constraint_never_reverses(self, base_url):
        """方向约束铁律：设为不计不反向，设为计入不改方向，方向永远是原始方向。"""
        _seed(base_url)
        _send("PUT", base_url + "/api/total/overrides",
              {"scope": "ids", "counted": 0, "ids": ["boc:2"]})  # 收入行 → 不计
        _send("PUT", base_url + "/api/total/overrides",
              {"scope": "ids", "counted": 1, "ids": ["alipay:2"]})  # 中性行 → 计入
        rows = _get(base_url + "/api/rows?source=total")
        by_id = {r["id"]: r for r in rows["rows"]}
        assert by_id["boc:2"]["direction"] == "收入"
        assert by_id["boc:2"]["counted"] is False
        assert by_id["alipay:2"]["direction"] == "不计收支"
        assert by_id["alipay:2"]["counted"] is True
        # 中性行计入方向按金额符号定：+0.50 进收入
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["income"] == {"count": 1, "sum": 0.50}

    def test_neutral_row_counted_by_sign(self, base_url):
        """中性行可改为计入，方向按金额符号（正=收入、负=支出）。"""
        _seed(base_url)
        _send("PUT", base_url + "/api/total/overrides",
              {"scope": "ids", "counted": 1, "ids": ["alipay:2"]})
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["income"] == {"count": 2, "sum": 3000.50}

    def test_invalid_counted_rejected(self, base_url):
        _seed(base_url)
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/total/overrides",
                  {"scope": "ids", "counted": 2, "ids": ["boc:1"]})
        assert excinfo.value.code == 400

    def test_invalid_row_id_rejected(self, base_url):
        _seed(base_url)
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/total/overrides",
                  {"scope": "ids", "counted": 0, "ids": ["boc:x"]})
        assert excinfo.value.code == 400

    def test_invalid_scope_rejected(self, base_url):
        _seed(base_url)
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/total/overrides",
                  {"scope": "xx", "counted": 0, "ids": []})
        assert excinfo.value.code == 400
