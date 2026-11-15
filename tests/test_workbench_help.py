"""工作台「使用帮助」离线静态内容测试

帮助内容内联在 index.html（不引入前端依赖 / 外部 CDN），覆盖启动访问、账单导入、
总账户与标签、PDF 需额外安装 extras、常见问题。
"""

from __future__ import annotations

import re
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "src" / "paycheck_workbench" / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_help_entry_present_in_topbar():
    html = _html()
    assert 'id="btn-help"' in html
    assert "使用帮助" in html
    # 顶栏入口 + 弹窗容器 + 关闭绑定
    assert 'id="help-mask"' in html
    assert 'id="btn-help-close"' in html
    assert 'openHelpModal' in html and 'closeHelpModal' in html


def test_help_content_sections():
    html = _html()
    for heading in (
        "启动与访问",
        "账单来源与导入步骤",
        "总账户与标签",
        "PDF 转换（需额外安装可选依赖）",
        "常见问题",
    ):
        assert heading in html, f"使用帮助缺少章节：{heading}"
    # PDF 需额外安装 extras 的提示与安装命令
    assert "uv sync --extra pdf" in html
    assert "本地工具" in html  # 本地访问 / 数据不上传说明


def test_help_is_offline_no_external_assets():
    """离线可用：不引用外部 CDN / 前端资源（仅帮助文案里的本机地址）。"""
    html = _html()
    assert not re.search(
        r"<(?:script|link|img)[^>]+(?:src|href)\s*=\s*[\"']https?://", html, re.IGNORECASE
    )
