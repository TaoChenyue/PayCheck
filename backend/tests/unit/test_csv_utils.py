"""CSV 行解析器测试 — 覆盖引号、逗号、转义等边界情况。

测试 parse_csv_line() 函数 (apps/ingest/csv_utils.py)。
"""

import pytest
from apps.ingest.csv_utils import parse_csv_line


class TestBasicParsing:
    """基本解析 — 无引号的标准 CSV"""

    def test_simple_three_fields(self):
        result = parse_csv_line("a,b,c")
        assert result == ["a", "b", "c"]

    def test_single_field(self):
        result = parse_csv_line("hello")
        assert result == ["hello"]

    def test_empty_string(self):
        result = parse_csv_line("")
        assert result == [""]

    def test_empty_fields(self):
        result = parse_csv_line("a,,c")
        assert result == ["a", "", "c"]

    def test_trailing_comma(self):
        """尾随逗号产生空字段"""
        result = parse_csv_line("a,b,")
        assert result == ["a", "b", ""]

    def test_leading_comma(self):
        result = parse_csv_line(",b,c")
        assert result == ["", "b", "c"]

    def test_numbers_and_dots(self):
        result = parse_csv_line("35.50,199.00,0")
        assert result == ["35.50", "199.00", "0"]


class TestQuotedFields:
    """引号包裹字段 — CSV 标准引号处理"""

    def test_quoted_simple(self):
        result = parse_csv_line('"hello"')
        assert result == ["hello"]

    def test_quoted_with_comma_inside(self):
        """引号内逗号不作为分隔符"""
        result = parse_csv_line('"hello, world",b')
        assert result == ["hello, world", "b"]

    def test_mixed_quoted_unquoted(self):
        result = parse_csv_line('a,"b,c",d')
        assert result == ["a", "b,c", "d"]

    def test_escaped_quotes(self):
        """CSV 中用 "" 转义引号"""
        result = parse_csv_line('"say ""hello"""')
        assert result == ['say "hello"']

    def test_escaped_quotes_in_middle(self):
        result = parse_csv_line('"a""b"')
        assert result == ['a"b']

    def test_quote_at_start_of_field(self):
        """引号包裹的空字符串"""
        result = parse_csv_line('"",b')
        assert result == ["", "b"]

    def test_multiple_quoted_fields(self):
        result = parse_csv_line('"a,b","c,d"')
        assert result == ["a,b", "c,d"]


class TestSpecialCharacters:
    """特殊字符处理"""

    def test_chinese_characters(self):
        result = parse_csv_line("麦当劳,午餐,35.50")
        assert result == ["麦当劳", "午餐", "35.50"]

    def test_chinese_quoted(self):
        result = parse_csv_line('"麦当劳，北京",午餐')
        assert result == ["麦当劳，北京", "午餐"]

    def test_spaces_preserved(self):
        result = parse_csv_line(" a , b ")
        assert result == [" a ", " b "]

    def test_spaces_in_quotes_preserved(self):
        result = parse_csv_line('" a "," b "')
        assert result == [" a ", " b "]

    def test_newline_like_content(self):
        """字段内容含 \n 字面值（非真实换行）"""
        result = parse_csv_line('a,"b\\nc",d')
        assert result == ["a", "b\\nc", "d"]


class TestEdgeCases:
    """极端/边界情况"""

    def test_only_commas(self):
        result = parse_csv_line(",,,")
        assert result == ["", "", "", ""]

    def test_all_quoted_empty(self):
        result = parse_csv_line('"","",""')
        assert result == ["", "", ""]

    def test_unclosed_quote(self):
        """未闭合引号 — 解析器应优雅处理（不复原样保留）"""
        result = parse_csv_line('"unclosed')
        # 未闭合引号使整行被当作一个字段（含开引号）
        assert len(result) == 1

    def test_quote_inside_unquoted(self):
        """非引号字段中的引号开启引号模式（状态机标准行为）"""
        result = parse_csv_line('a"b,c')
        # " 在 b 之前开启引号模式，b,c 被当作一个带引号字段
        assert result == ["ab,c"]

    def test_many_fields(self):
        """大量字段"""
        line = ",".join(["x"] * 100)
        result = parse_csv_line(line)
        assert len(result) == 100
        assert result[0] == "x"
