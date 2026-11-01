"""工作台文件日志：转换任务与服务端关键操作，便于问题回溯（成员验收反馈 4）。

约定：
- 日志文件随库走：<paycheck.db 所在目录>/paycheck.log，RotatingFileHandler 轮转
  （1MB × 3 份），路径经 /api/meta 的 log_file 字段返回。
- 敏感信息不落日志：只记录文件名、条数、耗时、job id、设备、错误摘要等元数据，
  不记录账单明细（交易日期/金额/对方账户等隐私数据）。
- 只由 serve() 调用 setup()：CLI 进程不经过本模块，命令行日志行为不变。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "paycheck_workbench"
_PIPELINE_LOGGER_NAME = "boc_pdf2csv"  # 管线页级/文件级日志一并入文件，便于回溯
_MAX_BYTES = 1024 * 1024
_BACKUP_COUNT = 3

_configured = False
_path: Optional[Path] = None


def setup(db_path) -> logging.Logger:
    """配置文件日志（幂等，首次调用生效）；返回工作台 logger。"""
    global _configured, _path
    logger = logging.getLogger(_LOGGER_NAME)
    if not _configured:
        _configured = True
        _path = Path(db_path).parent / "paycheck.log"
        handler = RotatingFileHandler(
            _path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False  # 文件日志不进控制台，避免与 stdout 输出混杂
        pipeline_logger = logging.getLogger(_PIPELINE_LOGGER_NAME)
        pipeline_logger.setLevel(logging.INFO)
        pipeline_logger.addHandler(handler)
        pipeline_logger.propagate = False
    return logger


def get() -> logging.Logger:
    """返回工作台 logger；未 setup 时不写文件（安全兜底，不抛错）。"""
    return logging.getLogger(_LOGGER_NAME)


def path() -> Optional[str]:
    """日志文件路径；未配置返回 None（供 /api/meta 展示）。"""
    return str(_path) if _path else None


def reset() -> None:
    """解除文件日志配置并关闭文件句柄（仅测试隔离用，避免临时目录清理失败）。"""
    global _configured, _path
    _configured = False
    _path = None
    for name in (_LOGGER_NAME, _PIPELINE_LOGGER_NAME):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
