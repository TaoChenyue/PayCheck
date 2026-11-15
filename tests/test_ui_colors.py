"""界面配色稳定性测试（TCY-67）：切换数据源不得重新分配 / 轮换配色。

用户反馈：点击不同数据源时，总账户与各数据源区域的配色会一起变化。
根因是「当前选中的数据源」通过 body[data-source] 覆盖了全局品牌色变量，而导航项
圆点 / 笔数徽标又都用这个变量取色，于是切换一次就把所有区域重染一遍。

本文件直接断言服务端下发的 index.html（不依赖浏览器、不使用任何真实账单数据）：
- 品牌色与各数据源标识色是固定常量，选中态不再参与配色；
- 每个导航项（总账户 / BOC / 支付宝 / 微信）各有固定且互不相同的标识色；
- 选中态只用背景 / 左侧指示条 / 字重表达，不改写颜色变量；
- 圆点与笔数徽标用固定标识色，不再跟随应用品牌色。
"""

from __future__ import annotations

import re
from pathlib import Path

import paycheck_workbench

INDEX_HTML = Path(paycheck_workbench.__file__).parent / "static" / "index.html"
SOURCES_IN_NAV = ("total", "boc", "alipay", "wechat")


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _css() -> str:
    match = re.search(r"<style>(.*?)</style>", _html(), re.S)
    assert match, "index.html 缺少 <style> 块"
    return re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)


def _rule(css: str, selector: str) -> str:
    """取某个选择器的声明块（按行首精确匹配选择器，简化实现够用）。"""
    match = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return match.group(1) if match else ""


def _decls(block: str) -> dict:
    result = {}
    for part in block.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            result[key.strip()] = value.strip()
    return result


class TestColorStability:
    def test_brand_color_is_a_fixed_global_constant(self):
        """品牌色只在 :root 定义一次，不再按选中的数据源覆盖。"""
        css = _css()
        assert len(re.findall(r"--brand\s*:", css)) == 1
        assert "--brand:" in _rule(css, ":root")

    def test_selected_source_does_not_drive_palette(self):
        """选中数据源不参与配色：不再存在 body[data-source] 配色覆盖。"""
        assert "body[data-source" not in _css()

    def test_each_nav_item_has_fixed_distinct_color(self):
        """总账户与三个数据源各有固定标识色，且互不相同。"""
        css = _css()
        colors = {}
        for source in SOURCES_IN_NAV:
            decls = _decls(_rule(css, f'.nav-item[data-source="{source}"]'))
            assert "--item-color" in decls, f"{source} 缺少固定标识色"
            colors[source] = decls["--item-color"]
        assert len(set(colors.values())) == len(SOURCES_IN_NAV)

    def test_source_colors_are_not_theme_overridable(self):
        """标识色只在 :root 定义一次：主题切换可以换底色，但不能换数据源标识色。"""
        css = _css()
        for name in ("--accent-total", "--accent-boc", "--accent-alipay", "--accent-wechat"):
            assert len(re.findall(re.escape(name) + r"\s*:", css)) == 1

    def test_selected_state_uses_non_color_cue(self):
        """选中态靠背景 + 左侧指示条 + 字重表达，不改写该项配色。"""
        active = _decls(_rule(_css(), ".nav-item.active"))
        assert "box-shadow" in active  # 左侧指示条
        assert active.get("color") == "var(--text)"
        assert "--item-color" not in active
        assert "--brand" not in _rule(_css(), ".nav-item.active")

    def test_nav_badge_and_dot_use_identity_color(self):
        """圆点与笔数徽标（数字区域）用固定标识色，不跟随应用品牌色。"""
        css = _css()
        for selector in (".nav-item .badge", ".nav-dot"):
            block = _rule(css, selector)
            assert "var(--item-color)" in block
            assert "var(--brand)" not in block

    def test_nav_markup_emits_source_attribute(self):
        """渲染模板给每个导航项输出 data-source，固定标识色才能按项生效。"""
        assert 'data-source="${s}"' in _html()
