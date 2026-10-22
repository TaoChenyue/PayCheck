"""规则 API 与总账户两区结构 HTTP 端到端测试（TCY-15/TCY-24）"""

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


def _seed_alipay(base_url):
    """与 BOC 快捷支付同日同金额的支付宝消费行（配对测试用）。"""
    rows = "\r\n".join([
        "2026-10-01 12:00:00,餐饮美食,示例面馆,,牛肉面,支出,8.80,,交易成功,A1,,",
    ])
    body = ("交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注\r\n"
            + rows + "\r\n").encode("utf-8")
    req = urllib.request.Request(base_url + "/api/import/confirm", data=body, headers={
        "Content-Type": "application/octet-stream", "X-Source": "alipay", "X-Filename": "a.csv",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


RULE_PAYLOAD = {
    "name": "银行卡快捷支付-渠道行（支付宝）",
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
        assert created["rule"]["name"] == "银行卡快捷支付-渠道行（支付宝）"
        assert created["rule"]["enabled"] is True
        assert created["rule"]["action"] == "fold"  # 动作统一「忽略」：提交 hide 也归一化为 fold

        listed = _get(base_url + "/api/rules")
        assert listed["ok"]
        assert len(listed["rules"]) == 1
        assert listed["rules"][0]["hit_count"] == 0  # 空库命中 0 笔
        assert listed["rules"][0]["conditions"] == RULE_PAYLOAD["conditions"]

        updated = _send("PUT", base_url + f"/api/rules/{created['rule']['id']}",
                        {**RULE_PAYLOAD, "enabled": False})
        assert updated["rule"]["enabled"] is False
        assert updated["rule"]["action"] == "fold"

        deleted = _send("DELETE", base_url + f"/api/rules/{created['rule']['id']}", {})
        assert deleted["ok"]
        assert _get(base_url + "/api/rules")["rules"] == []

    def test_auto_name_when_blank(self, base_url):
        payload = {**RULE_PAYLOAD, "name": ""}
        created = _send("POST", base_url + "/api/rules", payload)
        assert created["rule"]["name"] == "交易名称 等于「网上快捷支付」 且 对方账户名 开头是「支付宝」"
        assert created["rule"]["action"] == "fold"

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
        assert len(res["presets"]) == 8  # P7/P8 已移除
        ids = {p["id"] for p in res["presets"]}
        assert "preset-channel-pay" not in ids
        assert "preset-channel-refund" not in ids
        by_id = {p["id"]: p for p in res["presets"]}
        p10 = by_id["preset-same-name"]
        assert p10["has_placeholder"] is True
        assert p10["hit_count"] is None  # 占位符预设不统计
        p1 = by_id["preset-yuebao"]
        assert p1["hit_count"] == 0  # 空库
        assert p1["rule_count"] == 1
        for preset in res["presets"]:
            assert all(r["action"] == "fold" for r in preset["rules"])

    def test_import_removed_preset_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("POST", base_url + "/api/rules/import", {
                "preset_ids": ["preset-channel-pay"], "replacements": {},
            })
        assert excinfo.value.code == 400

    def test_import_creates_rules_and_skips_duplicates(self, base_url):
        _seed_boc(base_url)
        res = _send("POST", base_url + "/api/rules/import", {
            "preset_ids": ["preset-platform-income"], "replacements": {},
        })
        assert res["ok"]
        assert len(res["created"]) == 4
        assert res["skipped"] == []
        assert {r["preset_id"] for r in res["created"]} == {"preset-platform-income"}
        assert all(r["action"] == "fold" for r in res["created"])

        again = _send("POST", base_url + "/api/rules/import", {
            "preset_ids": ["preset-platform-income"], "replacements": {},
        })
        assert again["created"] == []
        assert len(again["skipped"]) == 4

        listed = _get(base_url + "/api/rules")
        assert len(listed["rules"]) == 4
        # 样本中无快捷提现/银联入账行，四条规则均 0 命中
        assert all(r["hit_count"] == 0 for r in listed["rules"])

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
            "time", "direction", "amount", "source", "counterparty", "summary", "mark"]
        assert [c for c in res["columns"] if c["key"] == "mark"][0]["label"] == "标注"

    def test_rows_total_two_zones(self, base_url):
        """rows 返回两区结构：命中规则的渠道行进忽略区标「忽略（规则名）」。"""
        _seed_boc(base_url)
        _send("POST", base_url + "/api/rules", RULE_PAYLOAD)

        res = _get(base_url + "/api/rows?source=total")
        assert res["ok"]
        assert res["real"]["total"] == 1  # 工资行
        assert res["real"]["rows"][0]["summary"] == "代发工资"
        assert res["ignore"]["total"] == 1
        row = res["ignore"]["rows"][0]
        assert row["summary"] == "网上快捷支付"
        assert row["mark"] == "path"
        assert row["mark_label"] == "忽略（银行卡快捷支付-渠道行（支付宝））"
        assert row["rule_names"] == ["银行卡快捷支付-渠道行（支付宝）"]

    def test_rows_total_mirror_pairing(self, base_url):
        """同日同金额配对端到端：银行侧进忽略区标镜像，平台侧主记录留真实区。"""
        _seed_boc(base_url)
        _seed_alipay(base_url)
        res = _get(base_url + "/api/rows?source=total")
        assert res["ok"]
        assert res["real"]["total"] == 2  # 工资 + 支付宝消费（主记录）
        assert {r["source"] for r in res["real"]["rows"]} == {"boc", "alipay"}
        assert res["ignore"]["total"] == 1
        mirror = res["ignore"]["rows"][0]
        assert mirror["mark"] == "mirror"
        assert mirror["mark_label"] == "镜像·支付宝"
        assert mirror["source"] == "boc"

    def test_rows_total_zone_pagination(self, base_url):
        _seed_boc(base_url)
        res = _get(base_url + "/api/rows?source=total&real_page=2&page_size=1")
        assert res["real"]["page"] == 2
        assert res["real"]["total"] == 2  # 工资 + 快捷支付（未建规则，真实支出）
        assert res["real"]["rows"] == []
        assert res["ignore"]["total"] == 0
        assert res["ignore"]["page"] == 1

    def test_rows_total_mapping_fields(self, base_url):
        _seed_boc(base_url)
        res = _get(base_url + "/api/rows?source=total")
        wage = next(r for r in res["real"]["rows"] if r["summary"] == "代发工资")
        assert wage["source"] == "boc"
        assert wage["time"] == "2026-10-02 10:00:00"
        assert wage["direction"] == "收入"
        assert wage["raw"]["counterparty"] == "示例公司"

    def test_summary_total_two_zones(self, base_url):
        _seed_boc(base_url)
        _seed_alipay(base_url)
        summary = _get(base_url + "/api/summary?source=total")
        assert summary["ok"]
        assert summary["income"] == {"count": 1, "sum": 3000.00}
        assert summary["expense"] == {"count": 1, "sum": 8.80}  # 平台侧主记录
        assert summary["net"] == 2991.20
        assert summary["count"] == 2
        assert summary["ignore"] == {"count": 1, "mirror": 1, "transfer": 0, "neutral": 0}

    def test_rows_total_sources_filter(self, base_url):
        _seed_boc(base_url)
        _seed_alipay(base_url)
        assert _get(base_url + "/api/rows?source=total&sources=alipay")["real"]["total"] == 1
        # 来源只留 BOC：身份仍按全量数据计算，镜像行保持镜像
        boc = _get(base_url + "/api/rows?source=total&sources=boc")
        assert boc["real"]["total"] == 1  # 工资行
        assert boc["ignore"]["total"] == 1
        assert boc["ignore"]["rows"][0]["mark"] == "mirror"

    def test_unknown_source_still_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(base_url + "/api/rows?source=xx")
        assert excinfo.value.code == 400
