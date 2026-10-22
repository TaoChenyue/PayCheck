"""标签组 CRUD 与批量打/移除标签 API 端到端测试（TCY-27）"""

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
        target=serve, kwargs={"db_path": db_path, "port": 8896}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8896"
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
    req = urllib.request.Request(base_url + "/api/import/confirm", data=boc, headers={
        "Content-Type": "application/octet-stream", "X-Source": "boc", "X-Filename": "b.csv",
    })
    with urllib.request.urlopen(req) as resp:
        json.loads(resp.read().decode("utf-8"))


class TestTagsApi:
    def test_create_list_update_delete(self, base_url):
        created = _send("POST", base_url + "/api/tags", {"name": "差旅"})
        assert created["ok"]
        assert created["tag"]["name"] == "差旅"
        assert created["tag"]["color"]
        assert created["tag"]["row_count"] == 0

        second = _send("POST", base_url + "/api/tags", {"name": "餐饮"})
        assert second["tag"]["color"] != created["tag"]["color"]  # 8 色循环自动分配

        listed = _get(base_url + "/api/tags")
        assert [t["name"] for t in listed["tags"]] == ["差旅", "餐饮"]

        updated = _send("PUT", base_url + f"/api/tags/{created['tag']['id']}", {"name": "出差"})
        assert updated["tag"]["name"] == "出差"

        deleted = _send("DELETE", base_url + f"/api/tags/{created['tag']['id']}", {})
        assert deleted["ok"]
        assert [t["name"] for t in _get(base_url + "/api/tags")["tags"]] == ["餐饮"]

    def test_blank_name_rejected(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("POST", base_url + "/api/tags", {"name": "  "})
        assert excinfo.value.code == 400

    def test_duplicate_name_rejected(self, base_url):
        _send("POST", base_url + "/api/tags", {"name": "差旅"})
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("POST", base_url + "/api/tags", {"name": "差旅"})
        assert excinfo.value.code == 400

    def test_update_missing_tag_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/tags/999", {"name": "x"})
        assert excinfo.value.code == 400

    def test_delete_missing_tag_400(self, base_url):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("DELETE", base_url + "/api/tags/999", {})
        assert excinfo.value.code == 400


class TestTagsApplyApi:
    def test_apply_add_idempotent_and_reflect(self, base_url):
        _seed(base_url)
        travel = _send("POST", base_url + "/api/tags", {"name": "差旅"})["tag"]
        dining = _send("POST", base_url + "/api/tags", {"name": "餐饮"})["tag"]

        res = _send("PUT", base_url + "/api/tags/apply", {
            "scope": "ids", "action": "add",
            "group_ids": [travel["id"], dining["id"]], "ids": ["boc:1"],
        })
        assert res["ok"]
        assert res["updated"] == 1

        rows = _get(base_url + "/api/rows?source=total")
        boc1 = next(r for r in rows["rows"] if r["id"] == "boc:1")
        assert [t["name"] for t in boc1["tags"]] == ["差旅", "餐饮"]
        assert boc1["counted"] is True  # 打标签不改属性

        # 重复打幂等
        again = _send("PUT", base_url + "/api/tags/apply", {
            "scope": "ids", "action": "add", "group_ids": [travel["id"]], "ids": ["boc:1"],
        })
        assert again["updated"] == 1
        rows = _get(base_url + "/api/rows?source=total")
        boc1 = next(r for r in rows["rows"] if r["id"] == "boc:1")
        assert [t["name"] for t in boc1["tags"]] == ["差旅", "餐饮"]

        # 行数统计
        assert _get(base_url + "/api/tags")["tags"][0]["row_count"] == 1

    def test_apply_remove(self, base_url):
        _seed(base_url)
        tag = _send("POST", base_url + "/api/tags", {"name": "差旅"})["tag"]
        _send("PUT", base_url + "/api/tags/apply", {
            "scope": "ids", "action": "add", "group_ids": [tag["id"]], "ids": ["boc:1", "boc:2"],
        })
        res = _send("PUT", base_url + "/api/tags/apply", {
            "scope": "ids", "action": "remove", "group_ids": [tag["id"]], "ids": ["boc:1"],
        })
        assert res["updated"] == 1
        rows = _get(base_url + "/api/rows?source=total")
        assert next(r for r in rows["rows"] if r["id"] == "boc:1")["tags"] == []
        assert len(next(r for r in rows["rows"] if r["id"] == "boc:2")["tags"]) == 1

    def test_apply_filter_scope(self, base_url):
        _seed(base_url)
        tag = _send("POST", base_url + "/api/tags", {"name": "划转"})["tag"]
        res = _send("PUT", base_url + "/api/tags/apply", {
            "scope": "filter", "action": "add", "group_ids": [tag["id"]],
            "filters": {"directions": ["收入"]},
        })
        assert res["updated"] == 1
        # 按标签筛选：命中任一勾选标签即显示
        filtered = _get(base_url + f"/api/rows?source=total&tags={tag['id']}")
        assert {r["id"] for r in filtered["rows"]} == {"boc:2"}

    def test_apply_unknown_tag_400(self, base_url):
        _seed(base_url)
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/tags/apply", {
                "scope": "ids", "action": "add", "group_ids": [999], "ids": ["boc:1"],
            })
        assert excinfo.value.code == 400

    def test_apply_invalid_action_400(self, base_url):
        _seed(base_url)
        tag = _send("POST", base_url + "/api/tags", {"name": "x"})["tag"]
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _send("PUT", base_url + "/api/tags/apply", {
                "scope": "ids", "action": "xx", "group_ids": [tag["id"]], "ids": ["boc:1"],
            })
        assert excinfo.value.code == 400

    def test_delete_tag_group_cascades(self, base_url):
        """删除标签组连带解除全部关联，账单行不动。"""
        _seed(base_url)
        tag = _send("POST", base_url + "/api/tags", {"name": "差旅"})["tag"]
        _send("PUT", base_url + "/api/tags/apply", {
            "scope": "ids", "action": "add", "group_ids": [tag["id"]], "ids": ["boc:1"],
        })
        _send("DELETE", base_url + f"/api/tags/{tag['id']}", {})
        rows = _get(base_url + "/api/rows?source=total")
        assert {r["id"] for r in rows["rows"]} == {"boc:1", "boc:2"}
        assert all(r["tags"] == [] for r in rows["rows"])
