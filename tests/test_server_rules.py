"""规则 API 与总账户 HTTP 端到端测试（TCY-15）"""

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
        target=serve, kwargs={"db_path": db_path, "port": 8898}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8898"
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


def _seed_boc(base_url):
    rows = "\r\n".join([
        "2026-10-01,10:00:00,支出,8.80,支付宝,银企对接,100.00,,网上快捷支付,人民币,,,",
        "2026-10-02,10:00:00,收入,3000.00,示例公司,银企对接,3100.00,,代发工资,人民币,,,",
    ])
    body = ("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank\r\n"
            + rows + "\r\n").encode("utf-8-sig")
    req = urllib.request.Request(base_url + "/api/import/confirm", data=body, headers={
        "Content-Type": "application/octet-stream", "X-Source": "boc", "X-Filename": "b.csv",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


RULE_PAYLOAD = {
    "name": "快捷支付渠道行",
    "source": "boc",
    "conditions": [
        {"field": "tx_name", "op": "eq", "value": "网上快捷支付"},
        {"field": "counterparty", "op": "starts", "value": "支付宝"},
    ],
    "action": "hide",
}


class TestRulesApi:
    def test_create_list_update_delete(self, base_url):
        created = _send("POST", base_url + "/api/rules", RULE_PAYLOAD)
        assert created["ok"]
        assert created["rule"]["name"] == "快捷支付渠道行"
        assert created["rule"]["enabled"] is True

        listed = _get(base_url + "/api/rules")
        assert listed["ok"]
        assert len(listed["rules"]) == 1
        assert listed["rules"][0]["hit_count"] == 0  # 空库命中 0 笔
        assert listed["rules"][0]["conditions"] == RULE_PAYLOAD["conditions"]

        updated = _send("PUT", base_url + f"/api/rules/{created['rule']['id']}",
                        {**RULE_PAYLOAD, "enabled": False, "action": "fold"})
        assert updated["rule"]["enabled"] is False
        assert updated["rule"]["action"] == "fold"

        deleted = _send("DELETE", base_url + f"/api/rules/{created['rule']['id']}", {})
        assert deleted["ok"]
        assert _get(base_url + "/api/rules")["rules"] == []

    def test_auto_name_when_blank(self, base_url):
        payload = {**RULE_PAYLOAD, "name": ""}
        created = _send("POST", base_url + "/api/rules", payload)
        assert created["rule"]["name"] == "交易名称 等于「网上快捷支付」 且 对方账户名 开头是「支付宝」"

    def test_invalid_rule_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("POST", base_url + "/api/rules", {
                "name": "x", "source": "boc",
                "conditions": [{"field": "商品说明", "op": "eq", "value": "a"}], "action": "fold",
            })
        assert excinfo.value.code == 400

    def test_update_missing_rule_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/rules/999", RULE_PAYLOAD)
        assert excinfo.value.code == 400

    def test_hit_count_follows_data(self, base_url):
        _send("POST", base_url + "/api/rules", RULE_PAYLOAD)
        assert _get(base_url + "/api/rules")["rules"][0]["hit_count"] == 0
        _seed_boc(base_url)
        assert _get(base_url + "/api/rules")["rules"][0]["hit_count"] == 1

    def test_preview_endpoint(self, base_url):
        _seed_boc(base_url)
        res = _send("POST", base_url + "/api/rules/preview",
                    {"source": "boc", "conditions": RULE_PAYLOAD["conditions"]})
        assert res["ok"]
        assert res["hit_count"] == 1


class TestPresetsApi:
    def test_presets_listing(self, base_url):
        res = _get(base_url + "/api/presets")
        assert res["ok"]
        assert len(res["presets"]) == 10
        by_id = {p["id"]: p for p in res["presets"]}
        p10 = by_id["preset-same-name"]
        assert p10["has_placeholder"] is True
        assert p10["hit_count"] is None  # 占位符预设不统计
        p1 = by_id["preset-yuebao"]
        assert p1["hit_count"] == 0  # 空库
        assert p1["rule_count"] == 1
        p7 = by_id["preset-channel-pay"]
        assert p7["rule_count"] == 2
        assert all(r["action"] == "hide" for r in p7["rules"])

    def test_import_creates_rules_and_skips_duplicates(self, base_url):
        _seed_boc(base_url)
        res = _send("POST", base_url + "/api/rules/import", {
            "preset_ids": ["preset-channel-pay"], "replacements": {},
        })
        assert res["ok"]
        assert len(res["created"]) == 2
        assert res["skipped"] == []
        assert {r["preset_id"] for r in res["created"]} == {"preset-channel-pay"}

        again = _send("POST", base_url + "/api/rules/import", {
            "preset_ids": ["preset-channel-pay"], "replacements": {},
        })
        assert again["created"] == []
        assert len(again["skipped"]) == 2

        listed = _get(base_url + "/api/rules")
        assert len(listed["rules"]) == 2
        assert listed["rules"][0]["hit_count"] == 1

    def test_import_requires_placeholder_value(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("POST", base_url + "/api/rules/import", {
                "preset_ids": ["preset-same-name"], "replacements": {},
            })
        assert excinfo.value.code == 400

    def test_import_with_placeholder_replacement(self, base_url):
        _seed_boc(base_url)
        res = _send("POST", base_url + "/api/rules/import", {
            "preset_ids": ["preset-same-name"], "replacements": {"本人姓名": "示例公司"},
        })
        assert res["ok"]
        assert len(res["created"]) == 1
        assert res["created"][0]["enabled"] is False  # P10 默认不启用
        assert res["created"][0]["conditions"][0]["value"] == "示例公司"
        assert _get(base_url + "/api/rules")["rules"][0]["hit_count"] == 1


class TestTotalApi:
    def test_options_total(self, base_url):
        res = _get(base_url + "/api/options?source=total")
        assert res["ok"]
        assert res["label"] == "总账户"
        assert res["directions"] == ["支出", "收入", "不计收支"]
        assert res["categories"] == ["boc", "alipay", "wechat"]
        assert [c["key"] for c in res["columns"]] == [
            "time", "direction", "amount", "source", "counterparty", "summary", "transfer"]

    def test_rows_total_with_transfer_modes(self, base_url):
        _seed_boc(base_url)
        _send("POST", base_url + "/api/rules", RULE_PAYLOAD)

        fold = _get(base_url + "/api/rows?source=total&transfer=fold")
        assert fold["ok"]
        assert fold["total"] == 1  # 渠道行被 hide 规则隐藏，剩工资行
        assert fold["hidden"] == {"count": 1, "rule_names": ["快捷支付渠道行"]}

        hide = _get(base_url + "/api/rows?source=total&transfer=hide")
        assert hide["total"] == 1

        show = _get(base_url + "/api/rows?source=total&transfer=show")
        assert show["total"] == 2
        assert all(r["transfer"] is None for r in show["rows"])

    def test_rows_total_mapping_fields(self, base_url):
        _seed_boc(base_url)
        show = _get(base_url + "/api/rows?source=total&transfer=show")
        wage = next(r for r in show["rows"] if r["summary"] == "代发工资")
        assert wage["source"] == "boc"
        assert wage["time"] == "2026-10-02 10:00:00"
        assert wage["direction"] == "收入"
        assert wage["raw"]["counterparty"] == "示例公司"

    def test_summary_total_three_sets(self, base_url):
        _seed_boc(base_url)
        _send("POST", base_url + "/api/rules", RULE_PAYLOAD)
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["ok"]
        assert summary["counted"]["count"] == 1
        assert summary["counted"]["income_sum"] == 3000.00
        assert summary["hidden"]["count"] == 1
        assert summary["hidden"]["expense_sum"] == 8.80
        assert summary["transfer"]["count"] == 0

    def test_rows_total_sources_filter(self, base_url):
        _seed_boc(base_url)
        assert _get(base_url + "/api/rows?source=total&sources=alipay")["total"] == 0
        assert _get(base_url + "/api/rows?source=total&sources=boc")["total"] == 2

    def test_unknown_source_still_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(base_url + "/api/rows?source=xx")
        assert excinfo.value.code == 400
