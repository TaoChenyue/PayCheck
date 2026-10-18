"""HTTP 服务端到端测试：静态页 + API + 导入幂等"""

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
        target=serve, kwargs={"db_path": db_path, "port": 8899}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8899"
    # 守护线程随进程退出，无需关闭


def _get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _upload_headers(source, name="t.csv"):
    return {
        "Content-Type": "application/octet-stream",
        "X-Source": source,
        "X-Filename": name,
    }


def test_index_served(base_url):
    with urllib.request.urlopen(base_url + "/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
    assert "账单工作台" in html


def test_meta_and_options(base_url):
    meta = _get(base_url + "/api/meta")
    assert meta["ok"]
    assert set(meta["counts"]) == {"boc", "alipay", "wechat"}

    options = _get(base_url + "/api/options?source=boc")
    assert options["ok"]
    assert options["directions"] == ["支出", "收入"]
    assert options["balance_col"] == "balance"
    assert any(c["key"] == "datetime" for c in options["columns"])

    alipay = _get(base_url + "/api/options?source=alipay")
    assert alipay["neutral"] == "不计收支"
    assert alipay["category_label"] == "交易分类"


def test_unknown_source_400(base_url):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(base_url + "/api/rows?source=xx")
    assert excinfo.value.code == 400


def test_import_preview_confirm_idempotent(base_url):
    body = (
        "date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank\r\n"
        "2024-08-01,12:00:00,支出,8.43,超市,银企对接,100.00,,快捷支付,人民币,,,\r\n"
    ).encode("utf-8-sig")
    preview = _post(base_url + "/api/import/preview", body, _upload_headers("boc"))
    assert preview["ok"]
    assert preview["row_count"] == 1
    assert preview["new_count"] == 1
    assert preview["dup_count"] == 0
    assert preview["date_min"] == preview["date_max"] == "2024-08-01"

    confirm = _post(base_url + "/api/import/confirm", body, _upload_headers("boc"))
    assert confirm["inserted"] == 1
    assert confirm["skipped"] == 0
    assert confirm["failed"] == 0

    again = _post(base_url + "/api/import/confirm", body, _upload_headers("boc"))
    assert again["inserted"] == 0
    assert again["skipped"] == 1

    meta = _get(base_url + "/api/meta")
    assert meta["counts"]["boc"] == 1
    rows = _get(base_url + "/api/rows?source=boc")
    assert rows["total"] == 1
    summary = _get(base_url + "/api/summary?source=boc")
    assert summary["expense_sum"] == 8.43
    assert summary["last_balance"] == "100.00"


def test_import_bad_file_returns_ok_false(base_url):
    preview = _post(
        base_url + "/api/import/preview",
        "not a csv".encode("utf-8"),
        _upload_headers("boc"),
    )
    assert preview["ok"] is False
    assert "表头" in preview["error"]


def test_import_wrong_extension_rejected(base_url):
    preview = _post(
        base_url + "/api/import/preview",
        b"x",
        _upload_headers("boc", "t.xlsx"),
    )
    assert preview["ok"] is False
    assert "只支持" in preview["error"]


def test_summary_with_date_filter(base_url):
    """带日期筛选的汇总应正常返回且只统计筛选范围内记录（回归：余额查询双重 WHERE）。"""
    rows = [
        "2026-10-05,12:00:00,支出,10.00,超市A,银企对接,100.00,,快捷支付,人民币,,,",
        "2026-09-15,12:00:00,支出,30.00,超市C,银企对接,100.00,,快捷支付,人民币,,,",
    ]
    body = ("date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank\r\n"
            + "\r\n".join(rows) + "\r\n").encode("utf-8-sig")
    confirm = _post(base_url + "/api/import/confirm", body, _upload_headers("boc"))
    assert confirm["inserted"] == 2

    summary = _get(base_url + "/api/summary?source=boc&date_from=2026-10-01&date_to=2026-10-19")
    assert summary["ok"]
    assert summary["count"] == 1
    assert summary["expense_sum"] == 10.0
    assert summary["last_balance"] == "100.00"

    summary = _get(base_url + "/api/summary?source=boc&date_from=2026-09-01&date_to=2026-09-30")
    assert summary["ok"]
    assert summary["count"] == 1
    assert summary["expense_sum"] == 30.0
