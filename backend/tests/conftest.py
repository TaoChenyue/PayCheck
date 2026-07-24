"""共享测试夹具 — 隔离的临时数据库和标签映射。

提供通过 conftest.py 和依赖注入使用的 fixtures，
使测试独立且可重复运行。

Django 环境自动初始化，确保 ``apps.*`` 导入可用。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# ── Django 环境初始化 ─────────────────────────────────────────
# 确保从 backend/tests/ 运行时也能正确导入 apps.* 模块

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()


@pytest.fixture
def temp_db():
    """使用临时数据库路径，每次测试完全隔离。"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="paycheck_test_")
    os.close(fd)
    yield path
    # 清理
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def tag_map():
    """预定义的标签名→ID 映射，模拟数据库中的标签。"""
    return {
        "餐饮": 1,
        "交通": 2,
        "购物": 3,
        "娱乐": 4,
        "房租": 5,
        "工资": 6,
        "报销": 7,
        "医疗": 8,
    }


@pytest.fixture
def sample_transactions():
    """标准测试用的交易记录列表。"""
    return [
        {
            "platform": "wechat",
            "time": "2025-01-15 12:30:00",
            "category": "餐饮",
            "counterparty": "麦当劳",
            "amount": 35.50,
            "tx_type": "支出",
            "payment_method": "零钱",
            "description": "午餐",
            "balance": None,
            "currency": "",
            "branch": "",
            "cp_account": "",
            "cp_bank": "",
        },
        {
            "platform": "alipay",
            "time": "2025-01-16 18:00:00",
            "category": "购物",
            "counterparty": "淘宝",
            "amount": 199.00,
            "tx_type": "支出",
            "payment_method": "花呗",
            "description": "耳机",
            "balance": None,
            "currency": "",
            "branch": "",
            "cp_account": "",
            "cp_bank": "",
        },
        {
            "platform": "wechat",
            "time": "2025-02-01 09:00:00",
            "category": "工资",
            "counterparty": "公司",
            "amount": 15000.00,
            "tx_type": "收入",
            "payment_method": "银行转账",
            "description": "1月工资",
            "balance": None,
            "currency": "",
            "branch": "",
            "cp_account": "",
            "cp_bank": "",
        },
    ]
