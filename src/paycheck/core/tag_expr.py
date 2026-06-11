"""标签表达式递归下降解析器 — 将用户输入编译为 SQL 集合运算

支持运算符:
    ∪ (并集)   ∩ (交集)   - (差集)
    括号 () 覆盖默认优先级

特殊标签: "全部" 表示所有交易

运算符优先级 (从高到低):
    1. ∩ (交集)
    2. ∪ (并集) 和 - (差集)  — 同级, 左结合
    括号优先于所有运算符

示例:
    "餐饮 ∪ 购物 ∩ 报销"      → 解析为 "餐饮 ∪ (购物 ∩ 报销)"
    "(餐饮 ∪ 购物) ∩ 报销"    → 解析为 "(餐饮 ∪ 购物) ∩ 报销"
    "全部 - 餐饮"             → 所有交易排除餐饮标签
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Tuple


class TokenType(Enum):
    """token 类型"""

    TAG = auto()        # 标签名
    UNION = auto()      # ∪
    INTERSECT = auto()  # ∩
    SUBTRACT = auto()   # -
    LPAREN = auto()     # (
    RPAREN = auto()     # )
    EOF = auto()        # 输入结束


@dataclass
class Token:
    """词法单元"""

    type: TokenType
    value: str = ""
    tag_id: int = -1


# ── AST 节点 ──────────────────────────────────────────────

ALL_TAG_ID = -1  # 特殊 tag_id，表示"全部"标签 — 匹配所有交易
ALL_TAG_NAME = "全部"


class ExprNode:
    """表达式 AST 节点基类"""

    def to_sql(self) -> str:
        raise NotImplementedError


class TagLeaf(ExprNode):
    """叶子节点: 单个标签"""

    def __init__(self, tag_id: int, tag_name: str) -> None:
        self.tag_id = tag_id
        self.tag_name = tag_name

    def to_sql(self) -> str:
        if self.tag_id == ALL_TAG_ID:
            return "SELECT DISTINCT id FROM transactions"
        return (
            "SELECT DISTINCT transaction_id FROM transaction_tags"
            f" WHERE tag_id = {self.tag_id}"
        )


class BinOp(ExprNode):
    """二元运算节点: 左 op 右"""

    def __init__(self, op: TokenType, left: ExprNode, right: ExprNode) -> None:
        self.op = op
        self.left = left
        self.right = right

    def to_sql(self) -> str:
        op_map = {
            TokenType.UNION: "UNION",
            TokenType.INTERSECT: "INTERSECT",
            TokenType.SUBTRACT: "EXCEPT",
        }
        sql_op = op_map[self.op]
        left_sql = self.left.to_sql()
        right_sql = self.right.to_sql()
        # 子 BinOp 用 SELECT * FROM 包裹，确保每个操作数是简单 SELECT
        if isinstance(self.left, BinOp):
            left_sql = f"SELECT * FROM ({left_sql})"
        if isinstance(self.right, BinOp):
            right_sql = f"SELECT * FROM ({right_sql})"
        return f"({left_sql} {sql_op} {right_sql})"


# ── 异常 ───────────────────────────────────────────────────


class ParseError(ValueError):
    """解析异常"""

    pass


# ── 词法分析 ──────────────────────────────────────────────


def tokenize(text: str, tag_map: Dict[str, int]) -> List[Token]:
    """将输入字符串拆分为 token 列表

    预处理: 将运算符/括号作为独立 token 分开,
    即使用户在它们之间漏了空格也能正常解析 (例如 "(餐饮" → "(" "餐饮")。

    Args:
        text: 用户输入的标签表达式, 如 "餐饮 ∪ 购物"
        tag_map: 标签名到 tag_id 的映射

    Returns:
        Token 列表, 末尾始终包含 EOF

    Raises:
        ValueError: 遇到未知标签
    """
    # 预处理: 在运算符和括号两侧插入空格, 确保按空格拆分时各自独立
    _OPERATORS = "∪∩-()"
    chars: list[str] = []
    for ch in text:
        if ch in _OPERATORS:
            chars.append(f" {ch} ")
        else:
            chars.append(ch)
    prepared = "".join(chars)

    tokens: List[Token] = []
    for tok in prepared.split():
        if tok == "(":
            tokens.append(Token(TokenType.LPAREN, "("))
        elif tok == ")":
            tokens.append(Token(TokenType.RPAREN, ")"))
        elif tok == "∪":
            tokens.append(Token(TokenType.UNION, "∪"))
        elif tok == "∩":
            tokens.append(Token(TokenType.INTERSECT, "∩"))
        elif tok == "-":
            tokens.append(Token(TokenType.SUBTRACT, "-"))
        elif tok == ALL_TAG_NAME:
            tokens.append(Token(TokenType.TAG, ALL_TAG_NAME, ALL_TAG_ID))
        elif tok in tag_map:
            tokens.append(Token(TokenType.TAG, tok, tag_map[tok]))
        else:
            raise ValueError(f"未知标签: {tok}")
            tokens.append(Token(TokenType.TAG, tok, tid))
    tokens.append(Token(TokenType.EOF))
    return tokens


# ── 递归下降解析器 ────────────────────────────────────────


class Parser:
    """递归下降解析器

    文法 (优先级由低到高):
        expr ← term (('∪' | '-') term)*
        term ← factor ('∩' factor)*
        factor ← TAG | '(' expr ')'
    """

    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # ── 辅助方法 ──

    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self) -> Token:
        return self.tokens[self.pos + 1]

    def advance(self) -> Token:
        tok = self.current()
        self.pos += 1
        return tok

    def expect(self, tt: TokenType) -> Token:
        tok = self.current()
        if tok.type != tt:
            raise ParseError(f"期望 {tt.name}, 实际遇到 {tok.type.name}")
        return self.advance()

    # ── 入口 ──

    def parse(self) -> ExprNode:
        node = self.expr()
        self.expect(TokenType.EOF)
        return node

    # ── 产生式 ──

    def expr(self) -> ExprNode:
        """expr ← term (('∪' | '-') term)*"""
        left = self.term()
        while self.current().type in (TokenType.UNION, TokenType.SUBTRACT):
            op = self.advance().type
            right = self.term()
            left = BinOp(op, left, right)
        return left

    def term(self) -> ExprNode:
        """term ← factor ('∩' factor)*"""
        left = self.factor()
        while self.current().type == TokenType.INTERSECT:
            op = self.advance().type
            right = self.factor()
            left = BinOp(op, left, right)
        return left

    def factor(self) -> ExprNode:
        """factor ← TAG | '(' expr ')'"""
        tok = self.current()
        if tok.type == TokenType.TAG:
            self.advance()
            return TagLeaf(tok.tag_id, tok.value)
        if tok.type == TokenType.LPAREN:
            self.advance()
            node = self.expr()
            self.expect(TokenType.RPAREN)
            return node
        raise ParseError(f"意外的 token: {tok.value or tok.type.name}")


# ── 对外接口 ──────────────────────────────────────────────


def validate_expression(text: str, tag_map: Dict[str, int]) -> Tuple[bool, str]:
    """校验标签表达式是否合法

    Args:
        text: 用户输入的表达式字符串
        tag_map: 标签名到 tag_id 的映射

    Returns:
        (是否合法, 错误信息) — 合法时错误信息为空字符串
    """
    if not text.strip():
        return True, ""
    try:
        tokens = tokenize(text, tag_map)
        Parser(tokens).parse()
    except (ValueError, ParseError) as e:
        return False, str(e)
    return True, ""


def compile_expression(text: str, tag_map: Dict[str, int]) -> str:
    """将标签表达式编译为 SQL 字符串

    Args:
        text: 用户输入的表达式字符串
        tag_map: 标签名到 tag_id 的映射

    Returns:
        SQLite 兼容的集合运算 SQL
    """
    tokens = tokenize(text, tag_map)
    ast = Parser(tokens).parse()
    sql = ast.to_sql()
    # 对复合表达式用子查询包裹，避免外层括号导致 SQLite 语法错误
    if isinstance(ast, BinOp):
        sql = f"SELECT * FROM ({sql})"
    return sql
