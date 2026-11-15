"""PDF 可选依赖（extras: pdf）与惰性导入测试

- 依赖分层：重依赖只在 `pdf` extras 中，默认安装不含
- 未安装 extras 时：包导入与工作台启动不触发 ImportError
- 调用 PDF 功能时：CLI / 工作台转换任务给出安装提示（不裸崩）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from boc_pdf2csv import deps
from paycheck_workbench import convert as convert_module

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

_PDF_PACKAGES = [
    "paddleocr",
    "paddlepaddle-gpu",
    "PyMuPDF",
    "opencv-python",
    "Pillow",
    "numpy",
    "tqdm",
    "torch",
]


def _section(text: str, header: str) -> str:
    """取 TOML 某个 `[section]` 段的内容（到下一个段头为止）。"""
    match = re.search(rf"^{re.escape(header)}\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def _array_block(section: str, key: str) -> str:
    """取 TOML 段内 `key = [...]` 数组内容。"""
    match = re.search(rf"^{re.escape(key)}\s*=\s*\[(.*?)^\]", section, re.M | re.S)
    return match.group(1) if match else ""


def test_pdf_heavy_deps_only_in_pdf_extras():
    """重依赖只在 optional-dependencies.pdf，默认依赖保持轻量。"""
    text = PYPROJECT.read_text(encoding="utf-8")
    base_deps = _array_block(_section(text, "[project]"), "dependencies")
    pdf_deps = _array_block(_section(text, "[project.optional-dependencies]"), "pdf")

    assert base_deps, "pyproject 缺少 [project] dependencies"
    assert pdf_deps, "pyproject 缺少 pdf extras"
    for package in _PDF_PACKAGES:
        assert package.lower() not in base_deps.lower(), f"{package} 不应出现在默认依赖中"
        assert package.lower() in pdf_deps.lower(), f"{package} 应在 pdf extras 中"
    assert "openpyxl" in base_deps  # 微信 XLSX 解析仍需默认安装


def test_scripts_only_paycheck_entry():
    """命令收敛：只保留 paycheck / boc-pdf2csv，旧 paycheck-workbench 入口已移除。"""
    text = PYPROJECT.read_text(encoding="utf-8")
    scripts = _section(text, "[project.scripts]")
    assert "paycheck-workbench" not in scripts
    assert re.search(r'^paycheck\s*=\s*"paycheck_workbench\.cli:main"', scripts, re.M)
    assert re.search(r'^boc-pdf2csv\s*=\s*"boc_pdf2csv\.cli:main"', scripts, re.M)


def test_missing_dependency_message_has_install_command():
    message = deps.missing_dependency_message(["torch", "PyMuPDF"])
    assert "PDF 转换需要可选依赖" in message
    assert "torch" in message and "PyMuPDF" in message
    assert "uv sync --extra pdf" in message


def test_ensure_pdf_deps_raises_when_missing(monkeypatch):
    monkeypatch.setattr(deps, "missing_pdf_dependencies", lambda: ["paddleocr"])
    with pytest.raises(deps.MissingPdfDependency) as excinfo:
        deps.ensure_pdf_deps()
    assert "uv sync --extra pdf" in str(excinfo.value)


def test_extras_status_shape():
    status = deps.extras_status()
    assert set(status) == {"available", "missing", "install"}
    assert isinstance(status["missing"], list)
    assert status["install"] == "uv sync --extra pdf"


def test_pdf_modules_import_without_optional_deps():
    """模拟缺 extras 环境：包、管线、服务模块仍可导入（不抛 ImportError）。"""
    code = r"""
import importlib.abc
import sys

BLOCKED = {"torch", "paddle", "paddleocr", "fitz", "cv2", "numpy", "PIL", "tqdm"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r} (blocked)")
        return None


sys.meta_path.insert(0, Blocker())

import boc_pdf2csv
import boc_pdf2csv.pipeline
import paycheck_workbench.server
import paycheck_workbench.convert

print("import-ok")
"""
    env = dict(os.environ)
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert "import-ok" in proc.stdout, proc.stderr[-2000:]
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_cli_exit_code_5_when_deps_missing(monkeypatch, tmp_path, capsys):
    """CLI 缺 extras：stderr 给安装命令，退出码 5（区别于处理失败 3）。"""
    monkeypatch.setattr(deps, "missing_pdf_dependencies", lambda: ["paddleocr"])

    from boc_pdf2csv.cli import main

    monkeypatch.setattr(sys, "argv", ["boc-pdf2csv", str(tmp_path)])
    code = main()
    assert code == 5
    assert "uv sync --extra pdf" in capsys.readouterr().err


def test_probe_gpu_reports_missing_extras(monkeypatch):
    """未装 extras 时 GPU 探测直接返回安装提示，不导入 torch/paddle。"""
    monkeypatch.setattr(convert_module.deps, "missing_pdf_dependencies", lambda: ["torch"])
    available, reason = convert_module._probe_gpu()
    assert available is False
    assert "uv sync --extra pdf" in reason


def test_convert_job_fails_with_install_hint(monkeypatch, tmp_path):
    """工作台转换任务缺 extras：任务 failed 且逐文件错误含安装命令。"""
    monkeypatch.setattr(convert_module.deps, "missing_pdf_dependencies", lambda: ["torch"])
    monkeypatch.setattr(convert_module, "_jobs", {})
    monkeypatch.setattr(convert_module, "_current", None)

    job = convert_module.start_job(["示例.pdf"])
    convert_module.run_convert_job(job, tmp_path, 3.0, 60, False)

    snapshot = job.snapshot()
    assert snapshot["status"] == "failed"
    assert "uv sync --extra pdf" in snapshot["files"][0]["error"]
