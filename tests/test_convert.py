"""BOC PDF 转换 HTTP 端到端测试：上传启动后台任务、轮询进度、产物预览/确认导入

真实 OCR 管线由假 process_folder 替换（monkeypatch boc_pdf2csv.pipeline.process_folder），
验证任务模型、接口契约与导入衔接（解析/去重/写入复用现有实现）。
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

import boc_pdf2csv.pipeline as pipeline_module
from paycheck_workbench import convert as convert_module
from paycheck_workbench.server import serve

BOUNDARY = "----PayCheckConvertBoundary123"

_BOC_HEADER = "date,time,tx_type,amount,counterparty,channel,balance,memo,tx_name,currency,branch,cp_account,cp_bank"


def _boc_row(date, amount, counterparty):
    return f"{date},10:00:00,支出,{amount},{counterparty},银企对接,100.00,,快捷支付,人民币,,,"


def _boc_csv(rows):
    return ("\r\n".join([_BOC_HEADER, *rows]) + "\r\n").encode("utf-8-sig")


@pytest.fixture()
def base_url(tmp_path, monkeypatch):
    monkeypatch.setattr(convert_module, "_detect_gpu", lambda: False)  # 无 GPU 环境
    monkeypatch.setattr(convert_module, "_gpu_cache", None)  # 每个测试从「未探测」开始
    monkeypatch.setattr(convert_module, "_jobs", {})  # 任务注册表按测试隔离
    monkeypatch.setattr(convert_module, "_current", None)
    db_path = tmp_path / "conv.db"
    thread = threading.Thread(
        target=serve, kwargs={"db_path": db_path, "port": 8903}, daemon=True
    )
    thread.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:8903", db_path


def _fake_pipeline(results, blocker=None):
    """返回假 process_folder：results {pdf 名: ("done"|"skip"|"fail", 交易数/错误)}。"""
    def fake(folder_path, scale=3.0, timeout_minutes=60, verbose=False, device="gpu",
             force=False, progress_cb=None, pdf_names=None):
        names = pdf_names if pdf_names is not None else sorted(
            f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")
        )
        for name in names:
            if blocker is not None:
                blocker.wait(timeout=10)
            action = results.get(name, ("fail", "处理出错"))
            if action[0] == "skip":
                if progress_cb:
                    progress_cb("pdf_skipped", {"name": name, "error": "同名 CSV 已存在"})
            elif action[0] == "fail":
                if progress_cb:
                    progress_cb("pdf_failed", {"name": name, "error": action[1]})
            else:
                n = action[1]
                if progress_cb:
                    progress_cb("engine_loading", {"device": device})
                    progress_cb("pdf_start", {"name": name, "pages_total": 1})
                    progress_cb("page_done", {"name": name, "page": 1, "pages_total": 1, "transactions_so_far": n})
                rows = [_boc_row(f"2026-10-{i + 1:02d}", f"{8.8 + i:.2f}", "示例面馆") for i in range(n)]
                (Path(folder_path) / (Path(name).stem + ".csv")).write_bytes(_boc_csv(rows))
                if progress_cb:
                    progress_cb("pdf_done", {"name": name, "transactions": n, "duration_s": 1.5})
    return fake


def _convert_multipart(files, fields=None):
    parts = []
    for name, data in files:
        parts.append(
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n".encode("utf-8")
            + data
            + b"\r\n"
        )
    for key, value in (fields or {}).items():
        parts.append(
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(f"--{BOUNDARY}--\r\n".encode("utf-8"))
    return b"".join(parts)


def _headers():
    return {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


def _get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, data=b"", headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_job(base_url, job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = _get(f"{base_url}/api/boc/convert/{job_id}")
        if res["status"] != "running":
            return res
        time.sleep(0.1)
    raise AssertionError("任务未在限时内结束")


def test_meta_includes_convert_info(base_url):
    base, _ = base_url
    meta = _get(base + "/api/meta")
    assert meta["ok"]
    assert meta["convert_dir"].endswith("boc_csv")
    assert meta["gpu_available"] is None  # 首次转换任务前未探测
    assert meta["convert_existing_csvs"] == []


def test_convert_end_to_end_done_and_skipped(base_url, monkeypatch):
    base, db_path = base_url
    monkeypatch.setattr(pipeline_module, "process_folder", _fake_pipeline({
        "a.pdf": ("done", 2), "b.pdf": ("skip", 0),
    }))

    res = _post(base + "/api/boc/convert", _convert_multipart([
        ("a.pdf", b"%PDF-1.4"), ("b.pdf", b"%PDF-1.4"),
    ]), _headers())
    assert res["ok"] and res["job_id"]

    job = _wait_job(base, res["job_id"])
    assert job["status"] == "done"
    assert job["totals"] == {"done": 1, "skipped": 1, "failed": 0, "transactions": 2}
    by_name = {f["name"]: f for f in job["files"]}
    assert by_name["a.pdf"]["state"] == "done"
    assert by_name["a.pdf"]["transactions"] == 2
    assert by_name["b.pdf"]["state"] == "skipped"
    assert job["finished_at"]

    # 产物 CSV 落盘转换目录（PDF 同名）
    assert (db_path.parent / "boc_csv" / "a.csv").exists()
    assert (db_path.parent / "boc_csv" / "a.pdf").exists()

    # 预览：结构与 preview-batch 一致，仅含成功产出的 CSV
    preview = _post(base + f"/api/boc/convert/{res['job_id']}/preview")
    assert preview["ok"]
    assert preview["file_count"] == 1
    assert preview["files"][0]["file_name"] == "a.csv"
    assert preview["total_rows"] == 2
    assert preview["total_new"] == 2
    assert preview["total_dup"] == 0

    # 确认导入：写入 SQLite；重复确认幂等（全跳过）
    confirm = _post(base + f"/api/boc/convert/{res['job_id']}/confirm")
    assert confirm["ok"]
    assert confirm["inserted"] == 2 and confirm["skipped"] == 0 and confirm["failed"] == 0
    again = _post(base + f"/api/boc/convert/{res['job_id']}/confirm")
    assert again["inserted"] == 0 and again["skipped"] == 2

    meta = _get(base + "/api/meta")
    assert meta["counts"]["boc"] == 2
    assert meta["gpu_available"] is False  # 首次任务已触发探测
    assert "a.csv" in meta["convert_existing_csvs"]


def test_convert_confirm_respects_file_filter(base_url, monkeypatch):
    base, _ = base_url
    monkeypatch.setattr(pipeline_module, "process_folder", _fake_pipeline({
        "a.pdf": ("done", 1), "b.pdf": ("done", 1),
    }))
    res = _post(base + "/api/boc/convert", _convert_multipart([
        ("a.pdf", b"%PDF-1.4"), ("b.pdf", b"%PDF-1.4"),
    ]), _headers())
    _wait_job(base, res["job_id"])

    confirm = _post_json(base + f"/api/boc/convert/{res['job_id']}/confirm", {"files": ["a.csv"]})
    assert confirm["inserted"] == 1
    assert [f["file_name"] for f in confirm["files"]] == ["a.csv"]

    meta = _get(base + "/api/meta")
    assert meta["counts"]["boc"] == 1  # b.csv 未导入


def test_convert_partial_failure(base_url, monkeypatch):
    base, _ = base_url
    monkeypatch.setattr(pipeline_module, "process_folder", _fake_pipeline({
        "ok.pdf": ("done", 1), "bad.pdf": ("fail", "渲染失败"),
    }))
    res = _post(base + "/api/boc/convert", _convert_multipart([
        ("ok.pdf", b"%PDF-1.4"), ("bad.pdf", b"%PDF-1.4"),
    ]), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "partial"
    assert job["totals"] == {"done": 1, "skipped": 0, "failed": 1, "transactions": 1}
    by_name = {f["name"]: f for f in job["files"]}
    assert by_name["bad.pdf"]["state"] == "failed"
    assert by_name["bad.pdf"]["error"] == "渲染失败"

    # 部分失败仍可导入成功的 CSV
    preview = _post(base + f"/api/boc/convert/{res['job_id']}/preview")
    assert preview["ok"] and preview["total_new"] == 1


def test_convert_all_failed_blocks_preview(base_url, monkeypatch):
    base, _ = base_url
    monkeypatch.setattr(pipeline_module, "process_folder", _fake_pipeline({
        "a.pdf": ("fail", "处理出错"), "b.pdf": ("fail", "处理出错"),
    }))
    res = _post(base + "/api/boc/convert", _convert_multipart([
        ("a.pdf", b"%PDF-1.4"), ("b.pdf", b"%PDF-1.4"),
    ]), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "failed"
    assert job["totals"]["failed"] == 2

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + f"/api/boc/convert/{res['job_id']}/preview")
    assert excinfo.value.code == 400


def test_convert_conflict_409_returns_job_id(base_url, monkeypatch):
    base, _ = base_url
    blocker = threading.Event()
    monkeypatch.setattr(pipeline_module, "process_folder",
                        _fake_pipeline({"a.pdf": ("done", 1)}, blocker=blocker))
    res = _post(base + "/api/boc/convert", _convert_multipart([("a.pdf", b"%PDF-1.4")]), _headers())
    assert res["ok"]

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert", _convert_multipart([("b.pdf", b"%PDF-1.4")]), _headers())
    assert excinfo.value.code == 409
    body = json.loads(excinfo.value.read().decode("utf-8"))
    assert body["ok"] is False and body["job_id"] == res["job_id"]

    blocker.set()
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "done"


def test_convert_status_interrupted_for_unknown_job(base_url):
    base, _ = base_url
    res = _get(base + "/api/boc/convert/" + "0" * 32)
    assert res["ok"] and res["status"] == "interrupted"
    assert res["files"] == []


def test_convert_silent_files_settled_done(base_url, monkeypatch):
    """管线正常返回但不发事件（渲染 0 图提前返回路径）且已写出 CSV：
    服务端按 CLI 语义补记为 done（0 条），不误标失败。"""
    base, _ = base_url

    def fake(folder_path, scale=3.0, timeout_minutes=60, verbose=False, device="gpu",
             force=False, progress_cb=None, pdf_names=None):
        for name in pdf_names or []:
            (Path(folder_path) / (Path(name).stem + ".csv")).write_bytes(_boc_csv([]))

    monkeypatch.setattr(pipeline_module, "process_folder", fake)
    res = _post(base + "/api/boc/convert", _convert_multipart([("a.pdf", b"%PDF-1.4")]), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "done"
    assert job["files"][0]["state"] == "done"
    assert job["files"][0]["transactions"] == 0


def test_convert_silent_files_settled_failed(base_url, monkeypatch):
    """管线正常返回但不发事件且无 CSV 产物：补记为失败。"""
    base, _ = base_url

    def fake(folder_path, scale=3.0, timeout_minutes=60, verbose=False, device="gpu",
             force=False, progress_cb=None, pdf_names=None):
        pass  # 不发事件、不写产物

    monkeypatch.setattr(pipeline_module, "process_folder", fake)
    res = _post(base + "/api/boc/convert", _convert_multipart([("a.pdf", b"%PDF-1.4")]), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "failed"
    assert job["files"][0]["state"] == "failed"


def test_convert_upload_validation(base_url, monkeypatch):
    base, _ = base_url
    monkeypatch.setattr(pipeline_module, "process_folder", _fake_pipeline({"a.pdf": ("done", 0)}))

    # 非 PDF
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert", _convert_multipart([("a.csv", b"x")]), _headers())
    assert excinfo.value.code == 400
    assert "仅支持 PDF" in json.loads(excinfo.value.read().decode("utf-8"))["error"]

    # 单文件超 64MB
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert",
              _convert_multipart([("big.pdf", b"x" * (64 * 1024 * 1024 + 1))]), _headers())
    assert excinfo.value.code == 400
    assert "64MB" in json.loads(excinfo.value.read().decode("utf-8"))["error"]

    # 超过 50 个文件
    many = [("f{:02d}.pdf".format(i), b"%PDF-1.4") for i in range(51)]
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert", _convert_multipart(many), _headers())
    assert excinfo.value.code == 400
    assert "50" in json.loads(excinfo.value.read().decode("utf-8"))["error"]

    # 非法 device
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert", _convert_multipart(
            [("a.pdf", b"%PDF-1.4")], {"device": "xpu"}), _headers())
    assert excinfo.value.code == 400


def test_convert_gpu_unavailable_error_mapped(base_url, monkeypatch):
    """device=gpu 且无 GPU：失败原因映射为页面文案（设计 §5.2）。"""
    base, _ = base_url

    def fake(folder_path, scale=3.0, timeout_minutes=60, verbose=False, device="gpu",
             force=False, progress_cb=None, pdf_names=None):
        assert device == "gpu"  # auto 在服务端解析，假管线收到 gpu/cpu 原语义
        for name in pdf_names or []:
            if progress_cb:
                progress_cb("pdf_failed", {
                    "name": name,
                    "error": "强制使用 GPU，但未检测到可用 GPU：请确认安装的是 GPU 版 paddlepaddle",
                })

    monkeypatch.setattr(pipeline_module, "process_folder", fake)
    res = _post(base + "/api/boc/convert", _convert_multipart(
        [("a.pdf", b"%PDF-1.4")], {"device": "gpu"}), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "failed"
    assert job["files"][0]["error"] == "未检测到可用 GPU，且推理设备为 GPU。请改用「自动」或「CPU」后重试"


def test_convert_auto_resolves_to_cpu_without_gpu(base_url, monkeypatch):
    base, _ = base_url
    seen = {}

    def fake(folder_path, scale=3.0, timeout_minutes=60, verbose=False, device="gpu",
             force=False, progress_cb=None, pdf_names=None):
        seen["device"] = device
        for name in pdf_names or []:
            if progress_cb:
                progress_cb("pdf_done", {"name": name, "transactions": 0, "duration_s": 0.1})
                (Path(folder_path) / (Path(name).stem + ".csv")).write_bytes(_boc_csv([]))

    monkeypatch.setattr(pipeline_module, "process_folder", fake)
    res = _post(base + "/api/boc/convert", _convert_multipart(
        [("a.pdf", b"%PDF-1.4")], {"device": "auto"}), _headers())
    job = _wait_job(base, res["job_id"])
    assert job["status"] == "done"
    assert seen["device"] == "cpu"  # auto + 无 GPU → 服务端解析为 cpu


def test_convert_open_dir(base_url, monkeypatch):
    base, db_path = base_url
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path))
    res = _post(base + "/api/boc/convert/open-dir")
    assert res["ok"]
    assert opened == [str(db_path.parent / "boc_csv")]


def test_convert_preview_unknown_job_400(base_url):
    base, _ = base_url
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(base + "/api/boc/convert/" + "0" * 32 + "/preview")
    assert excinfo.value.code == 400
