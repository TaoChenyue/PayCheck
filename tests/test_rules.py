"""规则模块单元测试：校验、条件 SQL、自动命名、预设库与占位符、移除预设停用（TCY-15/TCY-24）"""

from __future__ import annotations

import pytest

from paycheck_workbench import db, rules


def _c(field, op, value):
    return {"field": field, "op": op, "value": value}


class TestValidate:
    def test_valid_rule_ok(self):
        rules.validate_rule("boc", [_c("tx_name", "eq", "网上快捷支付")], "hide")

    def test_unknown_source(self):
        with pytest.raises(rules.RuleError, match="未知数据源"):
            rules.validate_rule("xx", [_c("tx_name", "eq", "a")], "fold")

    def test_unknown_action(self):
        with pytest.raises(rules.RuleError, match="未知命中处理"):
            rules.validate_rule("boc", [_c("tx_name", "eq", "a")], "delete")

    def test_field_not_in_whitelist(self):
        with pytest.raises(rules.RuleError, match="字段不在白名单"):
            rules.validate_rule("boc", [_c("商品说明", "eq", "a")], "fold")

    def test_unknown_operator(self):
        with pytest.raises(rules.RuleError, match="未知操作符"):
            rules.validate_rule("alipay", [_c("商品说明", "regex", "a")], "fold")

    def test_empty_conditions(self):
        with pytest.raises(rules.RuleError, match="至少需要一条条件"):
            rules.validate_rule("alipay", [], "fold")

    def test_too_many_conditions(self):
        conditions = [_c("备注", "eq", f"v{i}") for i in range(6)]
        with pytest.raises(rules.RuleError, match="最多"):
            rules.validate_rule("alipay", conditions, "fold")

    def test_empty_value_rejected(self):
        with pytest.raises(rules.RuleError, match="条件值不能为空"):
            rules.validate_rule("boc", [_c("memo", "eq", " ")], "fold")

    def test_in_with_all_empty_parts_rejected(self):
        with pytest.raises(rules.RuleError, match="任一等于"):
            rules.validate_rule("wechat", [_c("交易类型", "in", " | ")], "fold")


class TestConditionSql:
    def test_eq(self):
        sql, params = rules.condition_sql(_c("tx_type", "eq", "收入"))
        assert sql == '"tx_type" = ?'
        assert params == ["收入"]

    def test_in_splits_values(self):
        sql, params = rules.condition_sql(_c("交易类型", "in", "零钱充值|零钱提现"))
        assert sql == '"交易类型" IN (?, ?)'
        assert params == ["零钱充值", "零钱提现"]

    def test_contains_escapes_wildcards(self):
        sql, params = rules.condition_sql(_c("商品说明", "contains", "100%_off"))
        assert sql.endswith('ESCAPE "\\"')
        assert params == ["%100\\%\\_off%"]

    def test_starts(self):
        sql, params = rules.condition_sql(_c("商品说明", "starts", "余额宝-"))
        assert params == ["余额宝-%"]

    def test_not_contains(self):
        sql, params = rules.condition_sql(_c("备注", "not_contains", "测试"))
        assert sql.startswith('"备注" NOT LIKE')

    def test_conditions_sql_and_join(self):
        sql, params = rules.conditions_sql([_c("tx_name", "eq", "银联入账"), _c("counterparty", "contains", "蚂蚁")])
        assert sql == ' WHERE "tx_name" = ? AND "counterparty" LIKE ? ESCAPE "\\"'
        assert params == ["银联入账", "%蚂蚁%"]


class TestNaming:
    def test_auto_name_single(self):
        assert rules.auto_name([_c("商品说明", "starts", "余额宝-")]) == "商品说明 开头是「余额宝-」"

    def test_auto_name_english_field(self):
        assert rules.auto_name([_c("tx_name", "eq", "x")]) == "交易名称 等于「x」"

    def test_summarize_multiple_and(self):
        summary = rules.summarize_conditions([_c("交易分类", "eq", "信用借还"), _c("交易对方", "eq", "花呗")])
        assert summary == "交易分类 等于「信用借还」 且 交易对方 等于「花呗」"

    def test_rule_key_order_independent(self):
        a = [_c("交易分类", "eq", "信用借还"), _c("交易对方", "eq", "花呗")]
        b = [_c("交易对方", "eq", "花呗"), _c("交易分类", "eq", "信用借还")]
        assert rules.rule_key(a) == rules.rule_key(b)


class TestPresets:
    def test_all_presets_valid(self):
        """预设库自身全部通过校验（含白名单、操作符、动作）。"""
        ids = [p["id"] for p in rules.PRESETS]
        assert len(ids) == len(set(ids)) == 8
        for preset in rules.PRESETS:
            assert preset["rules"], preset["id"]
            for rule in preset["rules"]:
                rules.validate_rule(rule["source"], rule["conditions"], rule["action"])

    def test_channel_presets_removed(self):
        """P7/P8 已移除（渠道重复识别由配对算法接管）；REMOVED_PRESET_IDS 记录其 id。"""
        ids = [p["id"] for p in rules.PRESETS]
        assert "preset-channel-pay" not in ids
        assert "preset-channel-refund" not in ids
        assert rules.REMOVED_PRESET_IDS == ("preset-channel-pay", "preset-channel-refund")

    def test_all_preset_actions_fold(self):
        """动作统一「忽略」：预设内规则一律 fold。"""
        for preset in rules.PRESETS:
            for rule in preset["rules"]:
                assert rule["action"] == "fold", rule["name"]

    def test_action_labels_unified(self):
        assert rules.ACTION_LABELS == {"fold": "忽略", "hide": "忽略"}

    def test_placeholders_only_in_p10(self):
        for preset in rules.PRESETS:
            placeholders = rules.preset_placeholders(preset)
            if preset["id"] == "preset-same-name":
                assert placeholders == ["本人姓名"]
            else:
                assert placeholders == []

    def test_default_disabled_presets(self):
        for preset in rules.PRESETS:
            for rule in preset["rules"]:
                if preset["id"] in ("preset-xiaohebao", "preset-same-name"):
                    assert rule["enabled"] is False, rule["name"]
                else:
                    assert rule["enabled"] is True, rule["name"]

    def test_instantiate_requires_placeholder_value(self):
        preset = rules.PRESETS_BY_ID["preset-same-name"]
        with pytest.raises(rules.RuleError, match="本人姓名"):
            rules.instantiate_preset(preset, {})

    def test_instantiate_replaces_placeholder(self):
        preset = rules.PRESETS_BY_ID["preset-same-name"]
        specs = rules.instantiate_preset(preset, {"本人姓名": "张三"})
        assert len(specs) == 1
        assert specs[0]["conditions"][0]["value"] == "张三"
        # 预设原始条件未被修改
        assert preset["rules"][0]["conditions"][0]["value"] == "{本人姓名}"


class TestRemovedPresetRetire:
    def test_init_db_disables_removed_preset_rules(self, tmp_path):
        """升级迁移：已导入的 P7/P8 实例按 preset_id 自动停用，保留可删、不参与求值。"""
        db_path = tmp_path / "t.db"
        db.init_db(db_path)
        conn = db.connect(db_path)
        kept = db.save_rule(conn, {"name": "花呗还款-银行侧", "source": "boc",
                                   "preset_id": "preset-huabei",
                                   "conditions": [{"field": "counterparty", "op": "eq", "value": "支付宝-还款"}],
                                   "action": "fold", "enabled": True})
        retired = db.save_rule(conn, {"name": "银行卡快捷支付-渠道行（支付宝）", "source": "boc",
                                      "preset_id": "preset-channel-pay",
                                      "conditions": [{"field": "tx_name", "op": "eq", "value": "网上快捷支付"}],
                                      "action": "hide", "enabled": True})
        # 升级时自动停用（init_db 幂等迁移）
        db.init_db(db_path)
        by_id = {r["id"]: r for r in db.list_rules(conn)}
        assert by_id[retired["id"]]["enabled"] is False
        assert by_id[kept["id"]]["enabled"] is True
        conn.close()
