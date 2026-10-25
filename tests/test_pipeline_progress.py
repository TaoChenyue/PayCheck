"""boc_pdf2csv 管线进度回调与文件名过滤测试（不触发真实 OCR）

- progress_cb 可选：不传时行为与命令行一致（现有回归测试覆盖）
- 事件粒度：engine_loading / pdf_start / page_done / pdf_done / pdf_skipped / pdf_failed
- pdf_names 过滤：仅处理指定文件名，默认处理全部（命令行语义不变）
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import boc_pdf2csv.pipeline as pipeline


def _fake_render(pdf_path, scale=3.0, output_dir=None):
    # 两个假页面（内容无关，process_image 被替换为空实现）
    return [os.path.join(output_dir, "p1.png"), os.path.join(output_dir, "p2.png")]


def test_pdf_to_transactions_emits_progress_events(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "pdf_to_images", _fake_render)
    monkeypatch.setattr(pipeline, "warmup_engine", lambda device: None)
    monkeypatch.setattr(pipeline, "process_image", lambda img_path, device: [])

    pdf_path = str(tmp_path / "样例.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

    events = []
    transactions = pipeline._pdf_to_transactions(
        pdf_path, device="cpu", progress_cb=lambda e, info: events.append((e, dict(info)))
    )

    assert transactions == []
    assert [e for e, _ in events] == [
        "engine_loading", "pdf_start", "page_done", "page_done", "pdf_done",
    ]
    assert events[0][1] == {"device": "cpu"}
    assert events[1][1] == {"name": "样例.pdf", "pages_total": 2}
    assert events[2][1]["page"] == 1
    assert events[2][1]["pages_total"] == 2
    assert events[2][1]["transactions_so_far"] == 0
    assert events[3][1]["page"] == 2
    done = events[4][1]
    assert done["name"] == "样例.pdf"
    assert done["transactions"] == 0
    assert done["duration_s"] >= 0


def test_pdf_to_transactions_no_cb_unchanged(monkeypatch, tmp_path):
    """不传 progress_cb 时行为与命令行一致（不抛错、无事件依赖）。"""
    monkeypatch.setattr(pipeline, "pdf_to_images", _fake_render)
    monkeypatch.setattr(pipeline, "warmup_engine", lambda device: None)
    monkeypatch.setattr(pipeline, "process_image", lambda img_path, device: [])

    pdf_path = str(tmp_path / "样例.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
    assert pipeline._pdf_to_transactions(pdf_path, device="cpu") == []


def test_pdf_to_transactions_render_empty_emits_pdf_done(monkeypatch, tmp_path):
    """渲染 0 图时收尾事件照发（服务端任务按 CLI 语义计为「成功、0 条交易」）。"""
    monkeypatch.setattr(pipeline, "pdf_to_images", lambda *a, **k: [])

    pdf_path = str(tmp_path / "样例.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
    events = []
    result = pipeline._pdf_to_transactions(
        pdf_path, device="cpu", progress_cb=lambda e, info: events.append((e, info))
    )
    assert result == []
    assert events[-1] == ("pdf_done", {"name": "样例.pdf", "transactions": 0, "duration_s": events[-1][1]["duration_s"]})


def _fake_transactions(pdf_path, scale, timeout_minutes, verbose, device, progress_cb=None):
    # 模拟真实 _pdf_to_transactions 的 pdf_done 事件（其余事件由其内部发出，这里从简）
    if progress_cb:
        progress_cb("pdf_done", {
            "name": os.path.basename(pdf_path),
            "transactions": 1,
            "duration_s": 0.0,
        })
    return [{"date": "2026-10-01", "amount": "1.00", "counterparty": "甲"}]


def test_process_folder_progress_events(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _fake_transactions)

    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "a.csv").write_text("已有同名 CSV", encoding="utf-8")

    events = []
    result = pipeline.process_folder(
        str(tmp_path), device="cpu", progress_cb=lambda e, info: events.append((e, info))
    )

    assert list(result.processed) == [str(tmp_path / "b.pdf")]
    assert list(result.skipped) == [str(tmp_path / "a.pdf")]
    assert result.failed == []
    assert result.total_transactions == 1
    assert ("pdf_skipped", {"name": "a.pdf", "error": "同名 CSV 已存在"}) in events
    assert ("pdf_done", {"name": "b.pdf", "transactions": 1, "duration_s": 0.0}) in events
    # 成功文件写出同名 CSV
    assert (tmp_path / "b.csv").exists()


def test_process_folder_failed_emits_pdf_failed(monkeypatch, tmp_path):
    def _boom(pdf_path, scale, timeout_minutes, verbose, device, progress_cb=None):
        raise RuntimeError("渲染失败")

    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _boom)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")

    events = []
    with pytest.raises(RuntimeError):  # 全部失败时与命令行一致仍抛出
        pipeline.process_folder(str(tmp_path), device="cpu", progress_cb=lambda e, i: events.append((e, i)))

    assert ("pdf_failed", {"name": "a.pdf", "error": "渲染失败"}) in events


def test_process_folder_pdf_names_filter(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _fake_transactions)

    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")

    result = pipeline.process_folder(str(tmp_path), device="cpu", pdf_names=["a.pdf"])

    assert list(result.processed) == [str(tmp_path / "a.pdf")]
    assert result.skipped == [] and result.failed == []
    assert (tmp_path / "a.csv").exists()
    assert not (tmp_path / "b.csv").exists()  # 未在清单内的 PDF 不处理


def test_process_folder_without_filter_processes_all(monkeypatch, tmp_path):
    """默认不过滤：命令行语义不变（文件夹内全部 PDF 参与）。"""
    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _fake_transactions)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")

    result = pipeline.process_folder(str(tmp_path), device="cpu")

    assert len(result.processed) == 2
    assert (tmp_path / "a.csv").exists() and (tmp_path / "b.csv").exists()
