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


def _fake_transactions(pdf_path, scale, timeout_minutes, verbose, device, progress_cb=None, should_cancel=None):
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
    def _boom(pdf_path, scale, timeout_minutes, verbose, device, progress_cb=None, should_cancel=None):
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


# ---------------------------------------------------------------------------
# 协作取消（should_cancel）
# ---------------------------------------------------------------------------

def test_pdf_to_transactions_cancel_at_page_boundary(monkeypatch, tmp_path):
    """页边界检查取消：首轮检查即取消时，模型加载后中止，不产出交易、不发 pdf_done。"""
    monkeypatch.setattr(pipeline, "pdf_to_images", _fake_render)
    monkeypatch.setattr(pipeline, "warmup_engine", lambda device: None)
    monkeypatch.setattr(pipeline, "process_image", lambda img_path, device: [{"date": "2026-10-01", "amount": "1.00", "counterparty": "甲"}])

    pdf_path = str(tmp_path / "样例.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

    events = []
    with pytest.raises(pipeline.ConvertCancelled):
        pipeline._pdf_to_transactions(
            pdf_path, device="cpu",
            progress_cb=lambda e, info: events.append((e, dict(info))),
            should_cancel=lambda: True,
        )

    # 模型加载事件已发，但没有任何页被处理、也没有完成事件
    assert [e for e, _ in events] == ["engine_loading"]
    assert "pdf_done" not in [e for e, _ in events]


def test_pdf_to_transactions_cancel_midway_discards_partial(monkeypatch, tmp_path):
    """处理完第 1 页后取消：第 2 页边界抛出 ConvertCancelled，部分结果不返回。"""
    monkeypatch.setattr(pipeline, "pdf_to_images", _fake_render)
    monkeypatch.setattr(pipeline, "warmup_engine", lambda device: None)
    monkeypatch.setattr(pipeline, "process_image", lambda img_path, device: [])

    pdf_path = str(tmp_path / "样例.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

    calls = {"n": 0}

    def cancel_after_first_page():
        calls["n"] += 1
        # 检查点：模型加载后(1) → 第 1 页前(2) → 第 2 页前(3，取消)
        return calls["n"] > 2

    events = []
    with pytest.raises(pipeline.ConvertCancelled):
        pipeline._pdf_to_transactions(
            pdf_path, device="cpu",
            progress_cb=lambda e, info: events.append((e, dict(info))),
            should_cancel=cancel_after_first_page,
        )

    kinds = [e for e, _ in events]
    assert kinds == ["engine_loading", "pdf_start", "page_done"]
    assert events[-1][1]["page"] == 1  # 只处理完第 1 页


def test_process_folder_cancel_between_files(monkeypatch, tmp_path):
    """文件边界取消：不处理任何文件，整批抛出 ConvertCancelled，不写 CSV。"""
    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _fake_transactions)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")

    with pytest.raises(pipeline.ConvertCancelled):
        pipeline.process_folder(str(tmp_path), device="cpu", should_cancel=lambda: True)

    assert not (tmp_path / "a.csv").exists()
    assert not (tmp_path / "b.csv").exists()


def test_process_folder_cancel_after_first_file_keeps_first_csv(monkeypatch, tmp_path):
    """第 2 个文件前取消：第 1 个文件的 CSV 保留，第 2 个文件不处理。"""
    monkeypatch.setattr(pipeline, "_pdf_to_transactions", _fake_transactions)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")

    calls = {"n": 0}

    def cancel_before_second():
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(pipeline.ConvertCancelled):
        pipeline.process_folder(str(tmp_path), device="cpu", should_cancel=cancel_before_second)

    assert (tmp_path / "a.csv").exists()  # 已完成文件产物保留
    assert not (tmp_path / "b.csv").exists()
