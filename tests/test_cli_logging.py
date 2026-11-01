"""CLI 文件日志测试：日志文件生成、关键行存在、--verbose 升级 DEBUG、无交易明细字段。

假管线（monkeypatch cli.process_folder）持有交易明细数据，但按真实管线约定
只写元数据日志；断言交易日期/金额/对方账户名不落盘（隐私红线）。
"""

from __future__ import annotations

import logging
import os
import sys

import boc_pdf2csv.cli as cli_module
from boc_pdf2csv.pipeline import FolderResult

_DETAIL_DATE = "2026-10-01"
_DETAIL_AMOUNT = "88.00"
_DETAIL_NAME = "示例面馆"


def _fake_process_folder(folder_path, scale=3.0, timeout_minutes=60, verbose=False,
                         device="gpu", force=False, **kwargs):
    """假管线：与真实管线同款元数据日志，交易明细只存在于数据中不写入日志。"""
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"输入路径不存在或非目录: {folder_path}")
    log = logging.getLogger("boc_pdf2csv.pipeline")
    log.info("扫描到 1 个 PDF 文件")
    log.info("跳过（同名 CSV 已存在）: 2025-01.pdf")
    log.info("2025-02.pdf → 2025-02.csv (2 条交易)")
    log.info("处理完成: 2 条交易, 耗时 12.3s")
    log.debug("行分组: 5 个OCR块 → 2 行")
    return FolderResult(
        processed={"2025-02.pdf": "2025-02.csv"},
        skipped=["2025-01.pdf"],
        total_transactions=2,
    )


def _cleanup():
    """移除 CLI 挂到 boc_pdf2csv logger 上的 handler 并恢复默认状态（测试隔离）。"""
    logger = logging.getLogger("boc_pdf2csv")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def _run_cli(tmp_path, monkeypatch, argv):
    monkeypatch.setattr(cli_module, "process_folder", _fake_process_folder)
    monkeypatch.setattr(sys, "argv", argv)
    try:
        return cli_module.main()
    finally:
        _cleanup()


def test_cli_writes_file_log_with_key_lines(tmp_path, monkeypatch, capsys):
    """默认级别：日志文件生成且含关键行（扫描/跳过/每文件结果/耗时），控制台不出现 INFO。"""
    rc = _run_cli(tmp_path, monkeypatch, ["boc-pdf2csv", str(tmp_path)])
    assert rc == 0

    log_file = tmp_path / "boc-pdf2csv.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "扫描到 1 个 PDF 文件" in content
    assert "跳过（同名 CSV 已存在）: 2025-01.pdf" in content
    assert "2025-02.pdf → 2025-02.csv (2 条交易)" in content
    assert "处理完成: 2 条交易, 耗时 12.3s" in content

    captured = capsys.readouterr()
    assert "扫描到 1 个 PDF 文件" not in captured.out + captured.err


def test_cli_file_log_no_transaction_details(tmp_path, monkeypatch):
    """隐私红线：日志只含文件名/条数/耗时，不出现交易日期/金额/对方账户名。"""
    _run_cli(tmp_path, monkeypatch, ["boc-pdf2csv", str(tmp_path)])
    content = (tmp_path / "boc-pdf2csv.log").read_text(encoding="utf-8")
    assert _DETAIL_DATE not in content
    assert _DETAIL_AMOUNT not in content
    assert _DETAIL_NAME not in content


def test_cli_file_log_verbose_upgrades_debug(tmp_path, monkeypatch):
    """--verbose：文件级别升级 DEBUG，管线 debug 行入文件。"""
    rc = _run_cli(tmp_path, monkeypatch, ["boc-pdf2csv", str(tmp_path), "--verbose"])
    assert rc == 0
    content = (tmp_path / "boc-pdf2csv.log").read_text(encoding="utf-8")
    assert "行分组: 5 个OCR块 → 2 行" in content


def test_cli_file_log_missing_dir_returns_1_without_log(tmp_path, monkeypatch):
    """输入目录不存在：正常退出码 1，不产生日志文件也不抛错。"""
    missing = tmp_path / "missing"
    rc = _run_cli(tmp_path, monkeypatch, ["boc-pdf2csv", str(missing)])
    assert rc == 1
    assert not (missing / "boc-pdf2csv.log").exists()
