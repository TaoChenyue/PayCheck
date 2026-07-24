"""标签表达式解析器测试 — tokenize / parse / compile 核心路径。

覆盖 tag_expr.py 中的 tokenize、Parser、validate_expression、
compile_expression 函数。
"""

import pytest
from apps.transactions.tag_expr import (
    tokenize, Parser, ParseError, Token, TokenType,
    validate_expression, compile_expression,
    TagLeaf, BinOp, ExprNode, ALL_TAG_ID, ALL_TAG_NAME,
)


# ═══════════════════════════════════════════════════════════
# tokenize 测试
# ═══════════════════════════════════════════════════════════

class TestTokenize:
    """词法分析：拆分输入为 token 流"""

    def test_single_tag(self, tag_map):
        tokens = tokenize("餐饮", tag_map)
        assert len(tokens) == 2  # TAG + EOF
        assert tokens[0].type == TokenType.TAG
        assert tokens[0].value == "餐饮"
        assert tokens[0].tag_id == 1
        assert tokens[1].type == TokenType.EOF

    def test_tag_union(self, tag_map):
        tokens = tokenize("餐饮 ∪ 交通", tag_map)
        assert len(tokens) == 4  # TAG UNION TAG EOF
        assert tokens[0].value == "餐饮"
        assert tokens[1].type == TokenType.UNION
        assert tokens[2].value == "交通"

    def test_tag_intersect(self, tag_map):
        tokens = tokenize("餐饮 ∩ 购物", tag_map)
        assert tokens[1].type == TokenType.INTERSECT

    def test_tag_subtract(self, tag_map):
        tokens = tokenize("餐饮 - 报销", tag_map)
        assert tokens[1].type == TokenType.SUBTRACT

    def test_parentheses(self, tag_map):
        tokens = tokenize("( 餐饮 ∪ 交通 ) ∩ 购物", tag_map)
        types = [t.type for t in tokens]
        assert types == [TokenType.LPAREN, TokenType.TAG, TokenType.UNION,
                         TokenType.TAG, TokenType.RPAREN, TokenType.INTERSECT,
                         TokenType.TAG, TokenType.EOF]

    def test_no_spaces_around_operators(self, tag_map):
        """运算符/括号两侧无空格时自动拆分"""
        tokens = tokenize("(餐饮∪交通)", tag_map)
        types = [t.type for t in tokens]
        assert types == [TokenType.LPAREN, TokenType.TAG, TokenType.UNION,
                         TokenType.TAG, TokenType.RPAREN, TokenType.EOF]

    def test_all_tag(self, tag_map):
        """全部 标签映射到 ALL_TAG_ID"""
        tokens = tokenize("全部", tag_map)
        assert tokens[0].type == TokenType.TAG
        assert tokens[0].tag_id == ALL_TAG_ID

    def test_all_tag_subtract(self, tag_map):
        tokens = tokenize("全部 - 餐饮", tag_map)
        assert tokens[0].tag_id == ALL_TAG_ID
        assert tokens[1].type == TokenType.SUBTRACT
        assert tokens[2].tag_id == 1

    def test_unknown_tag_raises(self, tag_map):
        with pytest.raises(ValueError, match="未知标签"):
            tokenize("不存在的标签", tag_map)

    def test_empty_input(self, tag_map):
        tokens = tokenize("", tag_map)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self, tag_map):
        tokens = tokenize("   ", tag_map)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF


# ═══════════════════════════════════════════════════════════
# Parser.parse 测试 — 递归下降解析
# ═══════════════════════════════════════════════════════════

class TestParse:
    """语法分析：token 流 → AST"""

    def _parse(self, text, tag_map):
        tokens = tokenize(text, tag_map)
        return Parser(tokens).parse()

    def test_single_tag_leaf(self, tag_map):
        ast = self._parse("餐饮", tag_map)
        assert isinstance(ast, TagLeaf)
        assert ast.tag_id == 1
        assert ast.tag_name == "餐饮"

    def test_union_two_tags(self, tag_map):
        ast = self._parse("餐饮 ∪ 交通", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.UNION
        assert isinstance(ast.left, TagLeaf)
        assert isinstance(ast.right, TagLeaf)

    def test_intersect_two_tags(self, tag_map):
        ast = self._parse("餐饮 ∩ 购物", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.INTERSECT

    def test_subtract_two_tags(self, tag_map):
        ast = self._parse("餐饮 - 报销", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.SUBTRACT

    def test_precedence_intersect_over_union(self, tag_map):
        """∩ 优先级高于 ∪: 餐饮 ∪ 购物 ∩ 报销 → 餐饮 ∪ (购物 ∩ 报销)"""
        ast = self._parse("餐饮 ∪ 购物 ∩ 报销", tag_map)
        assert ast.op == TokenType.UNION
        assert isinstance(ast.left, TagLeaf)
        assert ast.left.tag_name == "餐饮"
        assert isinstance(ast.right, BinOp)
        assert ast.right.op == TokenType.INTERSECT

    def test_parentheses_override_precedence(self, tag_map):
        """括号覆盖优先级: (餐饮 ∪ 购物) ∩ 报销"""
        ast = self._parse("(餐饮 ∪ 购物) ∩ 报销", tag_map)
        assert ast.op == TokenType.INTERSECT
        assert isinstance(ast.left, BinOp)
        assert ast.left.op == TokenType.UNION
        assert isinstance(ast.right, TagLeaf)
        assert ast.right.tag_name == "报销"

    def test_chain_union_left_assoc(self, tag_map):
        """∪ 左结合: 餐饮 ∪ 交通 ∪ 购物 → (餐饮 ∪ 交通) ∪ 购物"""
        ast = self._parse("餐饮 ∪ 交通 ∪ 购物", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.UNION
        assert isinstance(ast.left, BinOp)
        assert isinstance(ast.right, TagLeaf)

    def test_missing_rparen_raises(self, tag_map):
        with pytest.raises(ParseError):
            self._parse("(餐饮", tag_map)

    def test_dangling_operator_raises(self, tag_map):
        """运算符后缺操作数"""
        with pytest.raises(ParseError):
            self._parse("餐饮 ∪", tag_map)

    def test_nested_parentheses(self, tag_map):
        ast = self._parse("((餐饮 ∩ 购物))", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.INTERSECT

    def test_all_tag_expr(self, tag_map):
        ast = self._parse("全部 - 娱乐", tag_map)
        assert isinstance(ast, BinOp)
        assert ast.op == TokenType.SUBTRACT
        assert ast.left.tag_id == ALL_TAG_ID


# ═══════════════════════════════════════════════════════════
# compile_expression 测试 — 生成 SQL
# ═══════════════════════════════════════════════════════════

class TestCompile:
    """SQL 编译：AST → SQLite 集合运算 SQL"""

    def test_single_tag_sql(self, tag_map):
        sql = compile_expression("餐饮", tag_map)
        assert "transaction_tags" in sql
        assert "tag_id = 1" in sql

    def test_all_tag_sql(self, tag_map):
        sql = compile_expression("全部", tag_map)
        assert "FROM transactions" in sql
        assert "tag_id" not in sql  # 全部 直接查 transactions

    def test_union_sql(self, tag_map):
        sql = compile_expression("餐饮 ∪ 交通", tag_map)
        assert "UNION" in sql

    def test_intersect_sql(self, tag_map):
        sql = compile_expression("餐饮 ∩ 购物", tag_map)
        assert "INTERSECT" in sql

    def test_subtract_sql(self, tag_map):
        sql = compile_expression("餐饮 - 报销", tag_map)
        assert "EXCEPT" in sql

    def test_complex_expr_sql(self, tag_map):
        """复合表达式外层包裹子查询"""
        sql = compile_expression("餐饮 ∪ 交通 ∩ 购物", tag_map)
        assert sql.startswith("SELECT * FROM (")

    def test_single_tag_no_outer_wrap(self, tag_map):
        """单标签不包裹外层子查询"""
        sql = compile_expression("餐饮", tag_map)
        assert not sql.startswith("SELECT * FROM (")

    def test_all_subtract_expr_sql(self, tag_map):
        sql = compile_expression("全部 - 娱乐 - 医疗", tag_map)
        assert "EXCEPT" in sql
        assert "FROM transactions" in sql


# ═══════════════════════════════════════════════════════════
# validate_expression 测试
# ═══════════════════════════════════════════════════════════

class TestValidate:
    """表达式校验：合法/非法判断"""

    def test_valid_simple(self, tag_map):
        ok, err = validate_expression("餐饮", tag_map)
        assert ok is True
        assert err == ""

    def test_valid_complex(self, tag_map):
        ok, err = validate_expression("(餐饮 ∪ 购物) ∩ (交通 ∪ 娱乐) - 报销", tag_map)
        assert ok is True

    def test_valid_empty(self, tag_map):
        ok, err = validate_expression("", tag_map)
        assert ok is True

    def test_valid_all(self, tag_map):
        ok, _ = validate_expression("全部 - 餐饮", tag_map)
        assert ok is True

    def test_invalid_unknown_tag(self, tag_map):
        ok, err = validate_expression("幽灵标签", tag_map)
        assert ok is False
        assert "未知标签" in err

    def test_invalid_syntax(self, tag_map):
        ok, err = validate_expression("(", tag_map)
        assert ok is False

    def test_invalid_dangling_union(self, tag_map):
        ok, err = validate_expression("餐饮 ∪", tag_map)
        assert ok is False
