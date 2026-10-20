"""批量导入（一次多个文件）HTTP 端到端测试：multipart 预览合并统计、逐文件确认幂等

批量确认由前端编排为逐文件调用单文件 /api/import/confirm，本文件模拟该编排验证
批内去重（库内已有 ∪ 批内已见）与「同批重复导入第二次全部跳过」的不变式。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from paycheck_workbench.server import serve

BOUNDARY = "----PayCheckTestBoundary123"

_REAL_DIR = os.environ.get("PAYCHECK_SAMPLE_DIR", "")
REAL = Path(_REAL_DIR)
HAS_REAL = bool(_REAL_DIR) and REAL.is_dir()
BOC_FILE = REAL / "BOC" / "20240801-20260731.csv"

_BOC_HEADER = "date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank"


@pytest.fixture()
def base_url(tmp_path):
    db_path = tmp_path / "batch.db"
    thread = threading.Thread(
        target=serve, kwargs={"db_path": db_path, "port": 8901}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8901"


def _boc_row(date, time_, amount, counterparty):
    return f"{date},{time_},支出,{amount},{counterparty},银企对接,100.00,,快捷支付,人民币,,,"


def _boc_csv(rows):
    return ("\r\n".join([_BOC_HEADER, *rows]) + "\r\n").encode("utf-8-sig")


def _multipart(files):
    """构造 multipart/form-data 请求体（files: [(文件名, bytes)]）。"""
    parts = []
    for name, data in files:
        parts.append(
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
            + data
            + b"\r\n"
        )
    parts.append(f"--{BOUNDARY}--\r\n".encode("utf-8"))
    return b"".join(parts)


def _headers():
    return {
        "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
        "X-Source": "boc",
    }


def _get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_file(url, body, name="t.csv", source="boc"):
    return _post(url, body, {
        "Content-Type": "application/octet-stream",
        "X-Source": source,
        "X-Filename": name,
    })


def test_batch_preview_merged_stats(base_url):
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A"),
                   _boc_row("2024-08-02", "12:00:00", "2.00", "超市B")])
    f2 = _boc_csv([_boc_row("2024-08-02", "12:00:00", "2.00", "超市B"),  # 与 f1 批内重复
                   _boc_row("2024-08-03", "12:00:00", "3.00", "超市C")])
    res = _post(base_url + "/api/import/preview-batch", _multipart([("a.csv", f1), ("b.csv", f2)]), _headers())

    assert res["ok"]
    assert res["file_count"] == 2
    assert res["files"][0]["file_name"] == "a.csv"
    assert res["files"][0]["new_count"] == 2
    assert res["files"][0]["dup_count"] == 0
    assert res["files"][0]["date_min"] == "2024-08-01"
    assert res["files"][1]["new_count"] == 1
    assert res["files"][1]["dup_count"] == 1
    assert res["total_rows"] == 4
    assert res["total_new"] == 3
    assert res["total_dup"] == 1
    assert res["total_failed"] == 0
    assert res["error_file_count"] == 0


def test_batch_preview_bad_extension_flagged(base_url):
    """混入类型不匹配的文件：明确提示（error 字段）且不计入统计（前端据此不写入）。"""
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A")])
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("a.csv", f1), ("b.pdf", b"%PDF-1.4")]), _headers())

    assert res["ok"]
    assert res["files"][0]["new_count"] == 1
    assert "只支持" in res["files"][1]["error"]
    assert res["error_file_count"] == 1
    assert res["total_new"] == 1


def test_batch_preview_parse_error_file(base_url):
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A")])
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("a.csv", f1), ("bad.csv", "不是账单".encode("utf-8"))]), _headers())

    assert res["ok"]
    assert res["files"][0]["new_count"] == 1
    assert "表头" in res["files"][1]["error"]
    assert res["error_file_count"] == 1
    assert res["total_new"] == 1


def test_batch_preview_same_file_twice(base_url):
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A"),
                   _boc_row("2024-08-02", "12:00:00", "2.00", "超市B")])
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("a.csv", f1), ("a.csv", f1)]), _headers())

    assert res["files"][0]["new_count"] == 2
    assert res["files"][1]["new_count"] == 0
    assert res["files"][1]["dup_count"] == 2
    assert res["total_new"] == 2
    assert res["total_dup"] == 2


def test_batch_preview_without_files_400(base_url):
    body = f"--{BOUNDARY}--\r\n".encode("utf-8")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base_url + "/api/import/preview-batch", body, _headers())
    assert excinfo.value.code == 400


def test_batch_confirm_sequential_and_idempotent(base_url):
    """前端编排：预览后逐文件调用单文件 confirm，第二次整批导入全部「重复跳过」。"""
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A")])
    f2 = _boc_csv([_boc_row("2024-08-02", "12:00:00", "2.00", "超市B")])
    files = [("a.csv", f1), ("b.csv", f2)]

    preview = _post(base_url + "/api/import/preview-batch", _multipart(files), _headers())
    assert preview["total_new"] == 2
    assert preview["total_dup"] == 0

    first = [_post_file(base_url + "/api/import/confirm", data, name) for name, data in files]
    assert [r["inserted"] for r in first] == [1, 1]
    assert sum(r["skipped"] for r in first) == 0
    assert sum(r["failed"] for r in first) == 0

    meta = _get(base_url + "/api/meta")
    assert meta["counts"]["boc"] == 2

    again = [_post_file(base_url + "/api/import/confirm", data, name) for name, data in files]
    assert [r["inserted"] for r in again] == [0, 0]
    assert sum(r["skipped"] for r in again) == 2


@pytest.mark.skipif(not (HAS_REAL and BOC_FILE.exists()), reason="无真实样本")
def test_batch_real_sample_twice_idempotent(base_url):
    """真实样本：同一文件同批出现两次 → 第二个全部重复；确认后再导入全部跳过（幂等不变式）。"""
    data = BOC_FILE.read_bytes()
    files = [("real1.csv", data), ("real2.csv", data)]

    preview = _post(base_url + "/api/import/preview-batch", _multipart(files), _headers())
    first, second = preview["files"]
    assert first["new_count"] > 0
    assert second["new_count"] == 0
    assert second["dup_count"] == first["new_count"]
    assert preview["total_new"] == first["new_count"]

    r1 = _post_file(base_url + "/api/import/confirm", data, "real1.csv")
    assert r1["inserted"] == first["new_count"]
    r2 = _post_file(base_url + "/api/import/confirm", data, "real2.csv")
    assert r2["inserted"] == 0
    assert r2["skipped"] == first["new_count"]

    r3 = _post_file(base_url + "/api/import/confirm", data, "real3.csv")
    assert r3["inserted"] == 0
    assert r3["skipped"] == first["new_count"]
