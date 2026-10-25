"""BOC PDF 转换真实推理路径冒烟测试（不 mock 管线）

现有接口契约测试全部 mock 了管线，真实推理路径没有自动化覆盖（测试侧反馈），
本文件补齐两条：

- 导入顺序回归（缺陷 1）：GPU 探测必须先导 torch 再导 paddle——Windows 上
  顺序颠倒时 paddle 的 DLL 搜索路径干扰 torch 加载 shm.dll（WinError 127），
  且一旦发生本进程 torch 永远无法加载。子进程内验证。
- 真实 OCR 管线冒烟：需设置环境变量 PAYCHECK_SAMPLE_DIR 指向真实样本目录
  （与 test_batch_import.py 同一约定），用真实 PDF 走通 process_folder(CPU)
  并验证事件序列、CSV 产物与支出行解析。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_IMPORT_ORDER_CODE = (
    "from paycheck_workbench.convert import _detect_gpu;"
    " _detect_gpu(); import torch; import paddle; print('ok')"
)


def test_detect_gpu_import_order_keeps_torch_loadable():
    """回归：探测先导 paddle 会让同一进程的 torch 加载必失败（缺陷 1）。"""
    proc = subprocess.run(
        [sys.executable, "-c", _IMPORT_ORDER_CODE],
        capture_output=True, text=True, timeout=300,
    )
    if "ModuleNotFoundError" in proc.stderr and "paddle" in proc.stderr:
        pytest.skip("环境未安装 paddle，跳过导入顺序回归")
    assert proc.returncode == 0, f"stderr:\n{proc.stderr[-2000:]}"


_REAL_DIR = os.environ.get("PAYCHECK_SAMPLE_DIR", "")
HAS_REAL = bool(_REAL_DIR) and Path(_REAL_DIR).is_dir()


def _real_pdf() -> Path:
    """取最小的 PDF 样本（冒烟测试控制耗时，大文件留给人工回归）。"""
    pdfs = sorted(Path(_REAL_DIR).glob("BOC/*.pdf"), key=lambda p: p.stat().st_size)
    if pdfs:
        return pdfs[0]
    raise FileNotFoundError("PAYCHECK_SAMPLE_DIR/BOC 下未找到 PDF 样本")


@pytest.mark.skipif(not HAS_REAL, reason="需设置 PAYCHECK_SAMPLE_DIR 指向真实样本目录")
def test_real_pipeline_smoke(tmp_path):
    """真实 OCR 管线冒烟：CPU 推理整份 PDF，事件序列完整且产出含支出行的 CSV。"""
    from boc_pdf2csv.pipeline import process_folder

    pdf = _real_pdf()
    (tmp_path / pdf.name).write_bytes(pdf.read_bytes())
    events = []
    result = process_folder(
        str(tmp_path), device="cpu", timeout_minutes=30,
        progress_cb=lambda e, info: events.append((e, info)),
    )

    assert list(result.processed) == [str(tmp_path / pdf.name)], result.failed
    assert not result.skipped
    event_types = [e for e, _ in events]
    assert event_types[0] == "engine_loading"  # 模型加载阶段事件
    assert "pdf_start" in event_types and "page_done" in event_types
    assert ("pdf_done", pdf.name) in [(e, i.get("name")) for e, i in events]

    csv_path = tmp_path / (pdf.stem + ".csv")
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) > 1  # 表头 + 至少一条交易
    assert any("支出" in line for line in lines[1:])  # 真实对账单含支出（负数金额）
    assert result.total_transactions > 0
