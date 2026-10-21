"""内部转账筛选规则：字段白名单、操作符、条件求值 SQL 与内置预设库（TCY-15）

- 规则 = 一组条件（AND）+ 命中处理（fold 内部流动 / hide 重复记录，存储值不变，仅含义重新表述）；OR 场景用多条规则表达
- 条件字段只取自该源明细表的物理列（白名单见 SOURCE_FIELDS）
- 内置预设 = 打包的一组规则（可跨源）；导入后每条规则独立出现在规则列表，
  preset_id 仅作「来自预设」标识，不锁定内容
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from paycheck_workbench.sources import SOURCE_ALIPAY, SOURCE_BOC, SOURCE_WECHAT

# ---- 字段白名单（按源取现有物理列，设计 §3.2）----
SOURCE_FIELDS: Dict[str, List[str]] = {
    SOURCE_BOC: ["tx_name", "counterparty", "memo", "channel", "tx_type"],
    SOURCE_ALIPAY: ["交易分类", "交易对方", "商品说明", "收/付款方式", "交易状态", "备注", "收/支"],
    SOURCE_WECHAT: ["交易类型", "交易对方", "商品", "支付方式", "当前状态", "备注", "收/支"],
}

# 英文物理列的中文名（用于条件摘要与自动命名；中文列名即本身）
FIELD_LABELS: Dict[str, str] = {
    "tx_name": "交易名称",
    "counterparty": "对方账户名",
    "memo": "附言",
    "channel": "渠道",
    "tx_type": "类型",
}

OPERATOR_LABELS: Dict[str, str] = {
    "eq": "等于",
    "in": "任一等于",
    "contains": "包含",
    "starts": "开头是",
    "not_contains": "不包含",
}

ACTIONS = ("fold", "hide")
ACTION_LABELS = {"fold": "内部流动", "hide": "重复记录"}
MAX_CONDITIONS = 5

# P10 同名账户互转的占位符（导入时提示填写，设计 §4）
PLACEHOLDER_NAME = "{本人姓名}"

_LIKE_ESCAPE = '"\\"'  # SQL 片段：ESCAPE "\"（与存储层 LIKE 口径一致）
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class RuleError(ValueError):
    """规则校验失败（HTTP 400 级）"""


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符（\\ % _），保证条件值按字面匹配。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_rule(source: str, conditions: List[dict], action: str) -> None:
    """校验规则三要素；不合法抛 RuleError。"""
    if source not in SOURCE_FIELDS:
        raise RuleError(f"未知数据源：{source}")
    if action not in ACTIONS:
        raise RuleError(f"未知命中处理：{action}")
    if not conditions:
        raise RuleError("至少需要一条条件")
    if len(conditions) > MAX_CONDITIONS:
        raise RuleError(f"条件最多 {MAX_CONDITIONS} 条")
    for cond in conditions:
        field = cond.get("field", "")
        op = cond.get("op", "")
        value = (cond.get("value") or "").strip()
        if field not in SOURCE_FIELDS[source]:
            raise RuleError(f"字段不在白名单：{field}")
        if op not in OPERATOR_LABELS:
            raise RuleError(f"未知操作符：{op}")
        if op == "in":
            if not any(v.strip() for v in value.split("|")):
                raise RuleError("「任一等于」需要至少一个值（多个值用 | 分隔）")
        elif not value:
            raise RuleError(f"条件值不能为空（{field_label(field)}）")


def condition_sql(cond: dict) -> Tuple[str, List[str]]:
    """单条条件 → (SQL 片段, 参数)。字段名来自白名单，参数一律走占位符。"""
    field, op, value = cond["field"], cond["op"], (cond.get("value") or "").strip()
    col = f'"{field}"'
    if op == "eq":
        return f"{col} = ?", [value]
    if op == "in":
        parts = [v.strip() for v in value.split("|") if v.strip()]
        return f"{col} IN ({', '.join('?' for _ in parts)})", parts
    if op == "contains":
        return f"{col} LIKE ? ESCAPE {_LIKE_ESCAPE}", [f"%{_escape_like(value)}%"]
    if op == "starts":
        return f"{col} LIKE ? ESCAPE {_LIKE_ESCAPE}", [f"{_escape_like(value)}%"]
    if op == "not_contains":
        return f"{col} NOT LIKE ? ESCAPE {_LIKE_ESCAPE}", [f"%{_escape_like(value)}%"]
    raise RuleError(f"未知操作符：{op}")


def conditions_sql(conditions: List[dict]) -> Tuple[str, List[str]]:
    """条件数组（AND）→ WHERE 片段与参数。"""
    clauses: List[str] = []
    params: List[str] = []
    for cond in conditions:
        sql, p = condition_sql(cond)
        clauses.append(sql)
        params.extend(p)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def cond_summary(cond: dict) -> str:
    """单条件一行式摘要：「字段 操作符「值」」。"""
    return f"{field_label(cond['field'])} {OPERATOR_LABELS[cond['op']]}「{cond.get('value', '')}」"


def summarize_conditions(conditions: List[dict]) -> str:
    """条件数组一行式摘要，多条件以「且」连接。"""
    return " 且 ".join(cond_summary(c) for c in conditions)


def auto_name(conditions: List[dict]) -> str:
    """名称留空时按条件自动生成。"""
    return summarize_conditions(conditions)


def rule_key(conditions: List[dict]) -> str:
    """条件数组的规范化键（AND 顺序无关），用于「同名同条件」重复判断。"""
    return json.dumps(
        sorted((c["field"], c["op"], c["value"]) for c in conditions),
        ensure_ascii=False,
    )


def preset_placeholders(preset: dict) -> List[str]:
    """预设全部条件值中的占位符名（去重保序，如 [{本人姓名}]）。"""
    found: List[str] = []
    for rule in preset["rules"]:
        for cond in rule["conditions"]:
            for key in _PLACEHOLDER_RE.findall(cond.get("value", "")):
                if key not in found:
                    found.append(key)
    return found


def instantiate_preset(preset: dict, replacements: Dict[str, str]) -> List[dict]:
    """预设 → 用户规则列表：替换条件值中的占位符（未填写的抛 RuleError），深拷贝不共享。"""
    placeholders = preset_placeholders(preset)
    missing = [p for p in placeholders if not (replacements.get(p) or "").strip()]
    if missing:
        raise RuleError(f"请填写占位符「{'」「'.join('{' + p + '}' for p in missing)}」对应的内容")
    specs: List[dict] = []
    for rule in preset["rules"]:
        conditions = json.loads(json.dumps(rule["conditions"], ensure_ascii=False))
        for cond in conditions:
            cond["value"] = _PLACEHOLDER_RE.sub(
                lambda m: (replacements.get(m.group(1)) or "").strip(), cond["value"]
            )
        specs.append({
            "name": rule["name"],
            "source": rule["source"],
            "conditions": conditions,
            "action": rule["action"],
            "enabled": bool(rule.get("enabled", True)),
        })
    return specs


def _cond(field: str, op: str, value: str) -> dict:
    return {"field": field, "op": op, "value": value}


# ---- 内置预设库 P1–P10（条件、默认状态与动作，设计 §4）----
PRESETS: List[dict] = [
    {
        "id": "preset-yuebao",
        "name": "余额宝-转入转出",
        "description": "余额宝收益发放/转入/转出等货币基金资金池变动，命中行标「内部流动」且不计入真实收支",
        "rules": [
            {"name": "余额宝-转入转出", "source": SOURCE_ALIPAY,
             "conditions": [_cond("商品说明", "starts", "余额宝-")], "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-lingqiantong",
        "name": "零钱通-转入转出",
        "description": "银行卡↔零钱通、零钱↔零钱通互转，命中行标「内部流动」且不计入真实收支",
        "rules": [
            {"name": "零钱通-转入转出", "source": SOURCE_WECHAT,
             "conditions": [_cond("交易类型", "contains", "零钱通")], "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-wechat-recharge",
        "name": "微信零钱-充值提现",
        "description": "银行卡↔微信零钱互转（零钱充值/零钱提现），命中行标「内部流动」且不计入真实收支",
        "rules": [
            {"name": "微信零钱-充值提现", "source": SOURCE_WECHAT,
             "conditions": [_cond("交易类型", "in", "零钱充值|零钱提现")], "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-alipay-withdraw",
        "name": "支付宝余额-提现",
        "description": "余额提现到银行卡（余额宝路径已由「余额宝-转入转出」覆盖），兜底规则",
        "rules": [
            {"name": "支付宝余额-提现", "source": SOURCE_ALIPAY,
             "conditions": [_cond("交易分类", "eq", "账户存取")], "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-huabei",
        "name": "花呗还款",
        "description": "花呗还款的支付宝侧与银行侧两条记录，命中行标「内部流动」且不计入真实收支（花呗消费本身是真实支出，不在此列）",
        "rules": [
            {"name": "花呗还款-支付宝侧", "source": SOURCE_ALIPAY,
             "conditions": [_cond("交易分类", "eq", "信用借还"), _cond("交易对方", "eq", "花呗")],
             "action": "fold", "enabled": True},
            {"name": "花呗还款-银行侧", "source": SOURCE_BOC,
             "conditions": [_cond("counterparty", "eq", "支付宝-还款")], "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-xiaohebao",
        "name": "支付宝小荷包",
        "description": "小荷包转入/转出。小荷包可能是共享资金池，转入可视作支出，默认不启用，确认后手动开启",
        "rules": [
            {"name": "支付宝小荷包", "source": SOURCE_ALIPAY,
             "conditions": [_cond("交易对方", "contains", "小荷包")], "action": "fold", "enabled": False},
        ],
    },
    {
        "id": "preset-channel-pay",
        "name": "银行卡快捷支付-渠道行",
        "description": "银行卡经支付宝/微信渠道消费的银行侧通道行，与平台侧明细重复，银行侧标「重复记录」，平台侧明细保留在真实收支（聚合级）",
        "rules": [
            {"name": "银行卡快捷支付-渠道行（支付宝）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "网上快捷支付"), _cond("counterparty", "starts", "支付宝")],
             "action": "hide", "enabled": True},
            {"name": "银行卡快捷支付-渠道行（财付通）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "网上快捷支付"), _cond("counterparty", "starts", "财付通")],
             "action": "hide", "enabled": True},
        ],
    },
    {
        "id": "preset-channel-refund",
        "name": "银行卡渠道退款",
        "description": "渠道消费退款的银行侧记录，与平台侧退款行重复，银行侧标「重复记录」，平台侧明细保留在真实收支（聚合级）",
        "rules": [
            {"name": "银行卡渠道退款（支付宝）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "网上快捷退款"), _cond("counterparty", "starts", "支付宝")],
             "action": "hide", "enabled": True},
            {"name": "银行卡渠道退款（财付通）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "网上快捷退款"), _cond("counterparty", "starts", "财付通")],
             "action": "hide", "enabled": True},
        ],
    },
    {
        "id": "preset-platform-income",
        "name": "平台提现/基金入账",
        "description": "余额宝转出到银行卡、平台代付入账的银行侧记录，命中行标「内部流动」且不计入真实收支",
        "rules": [
            {"name": "平台提现入账", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "网上快捷提现")], "action": "fold", "enabled": True},
            {"name": "基金/平台入账（蚂蚁）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "银联入账"), _cond("counterparty", "contains", "蚂蚁")],
             "action": "fold", "enabled": True},
            {"name": "基金/平台入账（支付宝）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "银联入账"), _cond("counterparty", "contains", "支付宝")],
             "action": "fold", "enabled": True},
            {"name": "基金/平台入账（财付通）", "source": SOURCE_BOC,
             "conditions": [_cond("tx_name", "eq", "银联入账"), _cond("counterparty", "contains", "财付通")],
             "action": "fold", "enabled": True},
        ],
    },
    {
        "id": "preset-same-name",
        "name": "同名账户互转",
        "description": "本人名下其他账户互转（对方含本人姓名）。导入时填写本人姓名，默认不启用，确认后手动开启",
        "rules": [
            {"name": "同名账户互转", "source": SOURCE_BOC,
             "conditions": [_cond("counterparty", "contains", PLACEHOLDER_NAME)],
             "action": "fold", "enabled": False},
        ],
    },
]

PRESETS_BY_ID: Dict[str, dict] = {p["id"]: p for p in PRESETS}
