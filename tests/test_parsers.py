"""解析层测试：合成样本（恒跑）+ 真实样本（设置 PAYCHECK_SAMPLE_DIR 环境变量时跑）"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from paycheck_workbench.parsing import ParseError, parse_file
from paycheck_workbench.sources import (
    ALIPAY_COLUMNS,
    BOC_COLUMNS,
    SOURCE_ALIPAY,
    SOURCE_BOC,
    SOURCE_WECHAT,
    WECHAT_COLUMNS,
    dedup_key,
)

_REAL_DIR = os.environ.get("PAYCHECK_SAMPLE_DIR", "")
REAL = Path(_REAL_DIR)
HAS_REAL = bool(_REAL_DIR) and REAL.is_dir()

BOC_FILE = REAL / "BOC" / "20240801-20260731.csv"
ALIPAY_FILE = REAL / "ALIPAY" / "支付宝交易明细(20240801-20250731).csv"
WECHAT_FILE = next((REAL / "WECHAT").glob("*(20240801-20250731)*.xlsx"), None) if HAS_REAL else None


def _boc_csv_text(rows=3):
    lines = [",".join(BOC_COLUMNS)]
    for i in range(rows):
        lines.append(
            "2024-08-0{0},12:00:{0:02d},支出,{0}.50,支付宝-超市,银企对接,100.00,附言,"
            "快捷支付,人民币,网点,123456,中国银行".format(i + 1)
        )
    return "\r\n".join(lines) + "\r\n"


def _alipay_csv_text():
    info = ["支付宝交易明细", "共2笔记录", "导出时间：[2026-07-24]"]
    header = ",".join(ALIPAY_COLUMNS) + ","
    rows = [
        "2025-07-31 18:05:17,餐饮美食,上海亚惠,/,商品A,支出,27.00,中国银行储蓄卡(3569),交易成功,ORDER001,M001,备注1,",
        "2025-07-30 06:02:38,投资理财,余额宝,/,收益发放,不计收支,5.22,余额宝,交易成功,ORDER002\t,\t,,",
    ]
    return "\n".join([*info, header, *rows])


def test_boc_parse_synthetic():
    result = parse_file(SOURCE_BOC, "a.csv", _boc_csv_text().encode("utf-8-sig"))
    assert result.columns == BOC_COLUMNS
    assert len(result.rows) == 3
    assert result.rows[0].values[:4] == ["2024-08-01", "12:00:01", "支出", "1.50"]
    assert not result.errors


def test_boc_header_mismatch_rejected():
    bad = "a,b,c\r\n1,2,3\r\n".encode("utf-8-sig")
    with pytest.raises(ParseError, match="表头不匹配"):
        parse_file(SOURCE_BOC, "a.csv", bad)


def test_boc_wrong_extension_rejected():
    with pytest.raises(ParseError, match="只支持"):
        parse_file(SOURCE_BOC, "a.xlsx", _boc_csv_text().encode("utf-8-sig"))


def test_alipay_gbk_info_header_and_tabs():
    result = parse_file(SOURCE_ALIPAY, "a.csv", _alipay_csv_text().encode("gbk"))
    assert result.columns == ALIPAY_COLUMNS
    assert len(result.rows) == 2
    # 信息头已跳过，表头行后的数据行正常解析
    first = result.rows[0].as_dict(ALIPAY_COLUMNS)
    assert first["交易订单号"] == "ORDER001"
    # 制表符被清洗（ORDER002\t → ORDER002），尾逗号空列被规整
    second = result.rows[1].as_dict(ALIPAY_COLUMNS)
    assert second["交易订单号"] == "ORDER002"
    assert second["商家订单号"] == ""
    assert second["收/支"] == "不计收支"
    assert all("\t" not in v for row in result.rows for v in row.values)


def test_alipay_missing_header_rejected():
    with pytest.raises(ParseError, match="未找到明细表头"):
        parse_file(SOURCE_ALIPAY, "a.csv", "随便几行\n没有表头\n".encode("gbk"))


def test_alipay_dedup_key_primary_and_fallback():
    values = dict(zip(ALIPAY_COLUMNS, [""] * len(ALIPAY_COLUMNS)))
    values["交易订单号"] = "ORDER123"
    assert dedup_key(SOURCE_ALIPAY, values) == "ORDER123"
    values["交易订单号"] = ""
    values["交易时间"] = "2025-07-31 18:05:17"
    values["金额"] = "27.00"
    values["交易对方"] = "上海亚惠"
    assert dedup_key(SOURCE_ALIPAY, values) == "2025-07-31 18:05:17|27.00|上海亚惠"


def test_wechat_csv_variant():
    info = ["微信支付账单明细", "共2笔记录"]
    header = ",".join(WECHAT_COLUMNS)
    rows = [
        "2025-07-31 19:33:35,商户消费,丰巢,快件畅存费,支出,0.50,中国银行储蓄卡(3569),支付成功,W001,M001,/",
        "45868.81,零钱提现,/,/,/,107.67,/,已到账,W002,M002,备注",
    ]
    text = "\n".join([*info, header, *rows])
    result = parse_file(SOURCE_WECHAT, "a.csv", text.encode("utf-8-sig"))
    assert result.columns == WECHAT_COLUMNS
    assert len(result.rows) == 2
    first = result.rows[0].as_dict(WECHAT_COLUMNS)
    assert first["交易时间"] == "2025-07-31 19:33:35"
    assert first["收/支"] == "支出"
    # 序列号文本日期被转换；收/支 '/' 归一化为中性交易
    second = result.rows[1].as_dict(WECHAT_COLUMNS)
    assert second["交易时间"].startswith("2025-07-")
    assert second["收/支"] == "中性交易"


def test_wechat_dedup_key():
    values = dict(zip(WECHAT_COLUMNS, [""] * len(WECHAT_COLUMNS)))
    values["交易单号"] = "W001"
    assert dedup_key(SOURCE_WECHAT, values) == "W001"
    values["交易单号"] = ""
    values["交易时间"] = "2025-07-31 19:33:35"
    values["金额(元)"] = "0.50"
    values["交易对方"] = "丰巢"
    assert dedup_key(SOURCE_WECHAT, values) == "2025-07-31 19:33:35|0.50|丰巢"


# ---------------- 真实样本（PAYCHECK_SAMPLE_DIR 指向的样本目录存在时跑）----------------

@pytest.mark.skipif(not (HAS_REAL and BOC_FILE.exists()), reason="无真实样本")
def test_boc_real_sample():
    result = parse_file(SOURCE_BOC, BOC_FILE.name, BOC_FILE.read_bytes())
    assert result.columns == BOC_COLUMNS
    assert len(result.rows) == 1423
    assert not result.errors
    first = result.rows[0].as_dict(BOC_COLUMNS)
    assert first["date"] == "2024-08-02"
    assert first["amount"] == "8.43"
    assert first["cp_bank"] == ""  # 尾列空值
    kinds = Counter(r.as_dict(BOC_COLUMNS)["tx_type"] for r in result.rows)
    assert set(kinds) <= {"支出", "收入"}


@pytest.mark.skipif(not (HAS_REAL and ALIPAY_FILE.exists()), reason="无真实样本")
def test_alipay_real_sample():
    result = parse_file(SOURCE_ALIPAY, ALIPAY_FILE.name, ALIPAY_FILE.read_bytes())
    assert result.columns == ALIPAY_COLUMNS
    assert len(result.rows) == 1707
    assert not result.errors
    kinds = Counter(r.as_dict(ALIPAY_COLUMNS)["收/支"] for r in result.rows)
    assert kinds == {"支出": 1097, "不计收支": 610}  # 设计 8.2：1707 笔中 610 笔不计收支
    assert all("\t" not in v for r in result.rows for v in r.values)
    orders = [r.as_dict(ALIPAY_COLUMNS)["交易订单号"] for r in result.rows]
    assert all(orders)  # 本样本订单号均非空（回退键路径由合成测试覆盖）


@pytest.mark.skipif(not (HAS_REAL and WECHAT_FILE and WECHAT_FILE.exists()), reason="无真实样本")
def test_wechat_real_sample():
    result = parse_file(SOURCE_WECHAT, WECHAT_FILE.name, WECHAT_FILE.read_bytes())
    assert result.columns == WECHAT_COLUMNS
    assert len(result.rows) == 540
    assert not result.errors
    kinds = Counter(r.as_dict(WECHAT_COLUMNS)["收/支"] for r in result.rows)
    assert kinds == {"支出": 439, "中性交易": 31, "收入": 70}  # 设计 8.2：540 笔中 31 笔中性
    times = [r.as_dict(WECHAT_COLUMNS)["交易时间"] for r in result.rows]
    assert all(t.startswith("2024-") or t.startswith("2025-") for t in times)  # 序列号已转日期
