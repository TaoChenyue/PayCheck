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
from paycheck_workbench.sources import ALIPAY_COLUMNS, BOC_COLUMNS

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


def _boc_row(date, time_, amount, counterparty, tx_type="支出"):
    return f"{date},{time_},{tx_type},{amount},{counterparty},银企对接,100.00,,快捷支付,人民币,,,"


def _boc_csv(rows):
    return ("\r\n".join([_BOC_HEADER, *rows]) + "\r\n").encode("utf-8-sig")


def _alipay_csv(row_texts):
    info = ["支付宝交易明细", "共2笔记录"]
    header = ",".join(ALIPAY_COLUMNS) + ","
    return "\n".join([*info, header, *row_texts]).encode("gbk")


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


def _headers(source="boc"):
    return {
        "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
        "X-Source": source,
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
                   _boc_row("2024-08-03", "12:00:00", "3.00", "超市C"),
                   _boc_row("2024-08-04", "12:00:00", "100.00", "工资", "收入")])
    res = _post(base_url + "/api/import/preview-batch", _multipart([("a.csv", f1), ("b.csv", f2)]), _headers())

    assert res["ok"]
    assert res["file_count"] == 2
    assert res["columns"] == BOC_COLUMNS
    assert res["files"][0]["file_name"] == "a.csv"
    assert res["files"][0]["new_count"] == 2
    assert res["files"][0]["dup_count"] == 0
    assert res["files"][0]["date_min"] == "2024-08-01"
    assert res["files"][1]["new_count"] == 2
    assert res["files"][1]["dup_count"] == 1
    assert res["total_rows"] == 5
    assert res["total_new"] == 4
    assert res["total_dup"] == 1
    assert res["total_failed"] == 0
    assert res["error_file_count"] == 0
    # 合并覆盖日期与收支分布（设计 4.2 合并统计次行）
    assert res["date_min"] == "2024-08-01"
    assert res["date_max"] == "2024-08-04"
    assert res["distribution"] == [
        {"label": "收入", "count": 1, "sum": 100.0},
        {"label": "支出", "count": 4, "sum": 8.0},
    ]
    # 逐文件分布与首 5 行样例（卡片展开区）
    assert res["files"][0]["distribution"] == [
        {"label": "收入", "count": 0, "sum": 0.0},
        {"label": "支出", "count": 2, "sum": 3.0},
    ]
    assert res["files"][0]["sample"] == [
        ["2024-08-01", "12:00:00", "支出", "1.00", "超市A", "银企对接", "100.00", "", "快捷支付", "人民币", "", "", ""],
        ["2024-08-02", "12:00:00", "支出", "2.00", "超市B", "银企对接", "100.00", "", "快捷支付", "人民币", "", "", ""],
    ]
    assert len(res["files"][1]["sample"]) == 3


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


def test_batch_preview_sample_limited_to_5(base_url):
    f = _boc_csv([_boc_row(f"2024-08-0{i}", "12:00:00", "1.00", "超市") for i in range(1, 7)])
    res = _post(base_url + "/api/import/preview-batch", _multipart([("a.csv", f)]), _headers())
    assert res["files"][0]["row_count"] == 6
    assert len(res["files"][0]["sample"]) == 5


def test_batch_preview_alipay_merged_distribution(base_url):
    """支付宝批内合并分布：收入/支出/不计收支三类合并顺序与数值正确。"""
    f1 = _alipay_csv([
        "2025-07-31 18:05:17,餐饮美食,上海亚惠,/,商品A,支出,27.00,中国银行储蓄卡(3569),交易成功,ORDER001,M001,备注1,",
        "2025-07-30 06:02:38,投资理财,余额宝,/,收益发放,不计收支,5.22,余额宝,交易成功,ORDER002\t,\t,,",
    ])
    f2 = _alipay_csv([
        "2025-07-29 12:00:00,其他,转账,/,转入,收入,100.00,余额,交易成功,ORDER003,M003,备注3,",
    ])
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("a.csv", f1), ("b.csv", f2)]), _headers("alipay"))

    assert res["columns"] == ALIPAY_COLUMNS
    assert res["distribution"] == [
        {"label": "收入", "count": 1, "sum": 100.0},
        {"label": "支出", "count": 1, "sum": 27.0},
        {"label": "不计收支", "count": 1, "sum": 5.22},
    ]
    assert res["total_new"] == 3


def test_batch_preview_oversize_file_flagged(base_url):
    """>64MB 文件：批量预览即拦截并标记 error（与单文件口径一致），不解析不写入。"""
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A")])
    big = b"x" * (64 * 1024 * 1024 + 1)
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("big.csv", big), ("a.csv", f1)]), _headers())

    assert res["ok"]
    assert "超过 64MB" in res["files"][0]["error"]
    assert res["files"][1]["new_count"] == 1
    assert res["error_file_count"] == 1
    assert res["total_new"] == 1


def test_batch_preview_oversized_field_file_flagged(base_url):
    """含 >128KB 单字段的文件：标记解析失败，同批其余文件正常返回（整批不断开）。"""
    f1 = _boc_csv([_boc_row("2024-08-01", "12:00:00", "1.00", "超市A")])
    big = "x" * (200 * 1024)
    f2 = (
        _BOC_HEADER + "\r\n"
        f"2024-08-02,12:00:00,支出,2.00,超市B,银企对接,100.00,{big},快捷支付,人民币,,,\r\n"
    ).encode("utf-8-sig")
    res = _post(base_url + "/api/import/preview-batch",
                _multipart([("a.csv", f1), ("big.csv", f2)]), _headers())

    assert res["ok"]
    assert res["files"][0]["new_count"] == 1
    assert "CSV 解析失败" in res["files"][1]["error"]
    assert res["error_file_count"] == 1
    assert res["total_new"] == 1


def test_single_preview_oversized_field_graceful(base_url):
    """>128KB 单字段：单文件预览优雅返回解析失败（ok=False JSON），不断开连接（既有缺陷）。"""
    big = "x" * (200 * 1024)
    body = (
        _BOC_HEADER + "\r\n"
        f"2024-08-01,12:00:00,支出,1.00,超市,银企对接,100.00,{big},快捷支付,人民币,,,\r\n"
    ).encode("utf-8-sig")
    res = _post_file(base_url + "/api/import/preview", body, "big.csv")
    assert res["ok"] is False
    assert "CSV 解析失败" in res["error"]


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
    # 合并覆盖日期/收支分布与逐文件分布、样例均返回
    assert preview["date_min"] == first["date_min"]
    assert preview["date_max"] == first["date_max"]
    assert sum(d["count"] for d in preview["distribution"]) == first["row_count"] * 2
    assert len(first["sample"]) == 5
    assert first["distribution"]

    r1 = _post_file(base_url + "/api/import/confirm", data, "real1.csv")
    assert r1["inserted"] == first["new_count"]
    r2 = _post_file(base_url + "/api/import/confirm", data, "real2.csv")
    assert r2["inserted"] == 0
    assert r2["skipped"] == first["new_count"]

    r3 = _post_file(base_url + "/api/import/confirm", data, "real3.csv")
    assert r3["inserted"] == 0
    assert r3["skipped"] == first["new_count"]
