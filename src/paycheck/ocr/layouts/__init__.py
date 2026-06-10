"""银行流水布局注册表

新增银行:
  1. 实现 BankLayout 子类
  2. 在此文件注册: register_layout("icbc", IcbcLayout)
"""

import logging

from typing import Dict, Type, Optional

from paycheck.ocr.layouts.base import BankLayout
from paycheck.ocr.layouts.boc import BocLayout


log = logging.getLogger("paycheck.layout")

_registry: Dict[str, Type[BankLayout]] = {}


def register_layout(name: str, cls: Type[BankLayout]) -> None:
    log.debug("注册布局: %s", name)
    _registry[name] = cls


def get_layout(name: str) -> Optional[BankLayout]:
    """按名称获取 layout 实例"""
    log.debug("获取布局: %s", name)
    cls = _registry.get(name)
    if cls is None:
        log.warning("未找到布局: %s", name)
    return cls() if cls is not None else None


def list_layouts() -> list[str]:
    return list(_registry.keys())


# 注册内置布局
register_layout("boc", BocLayout)
