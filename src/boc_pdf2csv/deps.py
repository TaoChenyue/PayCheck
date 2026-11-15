"""PDF 可选依赖（extras: pdf）检测与安装提示

PyMuPDF / opencv / numpy / Pillow / tqdm / PaddleOCR / paddlepaddle / torch 只被
PDF → CSV 链路使用，属于可选 extras（`pdf`）：默认 `uv sync` 不安装。

未安装 extras 时，本包其余部分（版本、CSV 写出、工作台与 CSV/Excel 导入）照常
可用；只有真正调用 PDF 功能时才由本模块给出统一的缺依赖提示与安装命令，
不出现启动即崩或裸 ImportError。
"""

from __future__ import annotations

import importlib.util
from typing import Dict, List

EXTRAS_NAME = "pdf"
INSTALL_COMMAND = "uv sync --extra pdf"
INSTALL_DOC = "docs/installation.md"

# 发行包名 → 顶层模块名（用 importlib.util.find_spec 探测，不实际导入）
_PDF_MODULES: Dict[str, str] = {
    "paddleocr": "paddleocr",
    "paddlepaddle-gpu": "paddle",
    "PyMuPDF": "fitz",
    "opencv-python": "cv2",
    "Pillow": "PIL",
    "numpy": "numpy",
    "tqdm": "tqdm",
    "torch": "torch",
}


def missing_pdf_dependencies() -> List[str]:
    """当前环境缺少的 PDF 可选依赖（发行包名列表；空列表表示 extras 齐全）。"""
    missing: List[str] = []
    for package, module in _PDF_MODULES.items():
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):  # 模块存在但自身导入失败：按缺失处理
            found = False
        if not found:
            missing.append(package)
    return missing


def missing_dependency_message(missing: List[str]) -> str:
    """缺依赖时的统一提示文案（含安装命令，CLI / 工作台共用）。"""
    return (
        "PDF 转换需要可选依赖（extras: pdf），当前环境缺少："
        + "、".join(missing)
        + f"。请先运行 `{INSTALL_COMMAND}` 安装后重试（详见 {INSTALL_DOC}）。"
    )


class MissingPdfDependency(RuntimeError):
    """PDF 功能所需可选依赖缺失（extras: pdf）。

    继承 RuntimeError 以兼容既有「PDF 处理失败」的调用方语义；
    调用方（CLI / 工作台任务）捕获后可给出安装提示。
    """

    def __init__(self, missing: List[str]):
        self.missing = list(missing)
        super().__init__(missing_dependency_message(self.missing))


def ensure_pdf_deps() -> None:
    """PDF 入口统一检查：缺依赖时抛 MissingPdfDependency（附安装命令）。"""
    missing = missing_pdf_dependencies()
    if missing:
        raise MissingPdfDependency(missing)


def extras_status() -> Dict[str, object]:
    """供 HTTP API / 界面展示的 extras 状态快照。"""
    missing = missing_pdf_dependencies()
    return {
        "available": not missing,
        "missing": missing,
        "install": INSTALL_COMMAND,
    }
