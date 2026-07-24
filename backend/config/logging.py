"""Django 日志配置模块

提供 Django 环境的日志配置与工具函数。

用法:
    # settings.py 中引入 LOGGING 配置
    from config.logging import LOGGING  # noqa: F401

    # 工具函数
    from config.logging import get_logger, log_time, log_execution_time

    log = get_logger()
    log.info("处理了 %d 条交易", count)

    @log_execution_time
    def slow_function():
        ...

    with log_time("OCR 识别"):
        result = do_ocr()
"""

from __future__ import annotations

import functools
import logging
import os
import time
import warnings
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# ── 日志文件配置 ──────────────────────────────────────────────
# 单个日志文件最大 10MB，保留 5 份备份
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5
_DEFAULT_LOG_DIR = "log"
_DEFAULT_LOG_FILE = "paycheck.log"


# =========================================================================
# Django LOGGING 配置字典
# =========================================================================

def _build_file_handler(log_dir: str, log_file: str) -> dict:
    """构建文件 handler 配置字典。"""
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": os.path.join(log_dir, log_file),
        "maxBytes": _LOG_MAX_BYTES,
        "backupCount": _LOG_BACKUP_COUNT,
        "encoding": "utf-8",
        "formatter": "verbose_file",
    }


LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "verbose_file": {
            "format": "{asctime} [{levelname:7s}] {name}: {message}",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "style": "{",
        },
        "simple": {
            "format": "{message}",
            "style": "{",
        },
    },
    "filters": {},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "paycheck": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # ── 压制第三方库噪声 ──
        "paddle": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "paddleocr": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "ppocr": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "PIL": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "matplotlib": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "fitz": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "urllib3": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "requests": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "chardet": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "charset_normalizer": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def enable_file_logging(
    log_dir: str = _DEFAULT_LOG_DIR,
    log_file: str = _DEFAULT_LOG_FILE,
) -> None:
    """启用文件日志（RotatingFileHandler）。

    在 manage.py 或 AppConfig.ready() 中调用，为 root 和 paycheck
    logger 添加文件 handler。

    Args:
        log_dir: 日志目录路径
        log_file: 日志文件名
    """
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, log_file)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "{asctime} [{levelname:7s}] {name}: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style="{",
    ))

    root = logging.getLogger()
    root.addHandler(file_handler)

    logger = logging.getLogger("paycheck")
    logger.info("=" * 50)
    logger.info("PayCheck 启动")
    logger.info("日志文件: %s", log_path)
    logger.info("=" * 50)


def enable_console_verbose() -> None:
    """启用控制台 DEBUG 级别日志（verbose 模式）。

    在需要调试时调用，将 root logger 的 console handler 级别降至 DEBUG。
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter("{message}", style="{"))
    root.setLevel(logging.DEBUG)


def suppress_noisy_loggers() -> None:
    """运行时压制第三方库的烦人日志和警告。

    在 AppConfig.ready() 中调用以确保在 Django 日志配置加载后生效。
    """
    for name in [
        "paddle", "paddleocr", "ppocr",
        "PIL", "matplotlib", "fitz",
        "urllib3", "requests", "chardet", "charset_normalizer",
    ]:
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).propagate = False

    warnings.filterwarnings("ignore", category=UserWarning, module="paddle")
    warnings.filterwarnings("ignore", category=UserWarning, module="ppocr")
    warnings.filterwarnings(
        "ignore", message=".*urllib3.*or.*chardet.*doesn't match"
    )


# =========================================================================
# 日志辅助函数
# =========================================================================


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取模块日志器（推荐替代 logging.getLogger(__name__)）

    用法:
        from config.logging import get_logger
        log = get_logger()  # 自动使用调用者的 __name__
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back  # type: ignore[union-attr]
            module = inspect.getmodule(caller_frame)
            name = module.__name__ if module else "paycheck"
        finally:
            del frame
    return logging.getLogger(name)


@contextmanager
def log_time(
    label: str = "",
    level: int = logging.DEBUG,
    logger: Optional[logging.Logger] = None,
):
    """上下文管理器：记录代码块执行耗时

    用法:
        with log_time("OCR 识别"):
            result = do_ocr()

    输出:
        [DEBUG] paycheck.xxx: ⏱ OCR 识别 耗时 3.21s
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        if elapsed >= 1.0:
            unit = "s"
            val = f"{elapsed:.2f}"
        elif elapsed >= 0.001:
            unit = "ms"
            val = f"{elapsed * 1000:.1f}"
        else:
            unit = "μs"
            val = f"{elapsed * 1_000_000:.0f}"
        msg = f"⏱ {label} 耗时 {val}{unit}" if label else f"⏱ 耗时 {val}{unit}"
        (logger or logging.getLogger("paycheck")).log(level, msg)


def log_execution_time(func=None, *, level: int = logging.DEBUG):
    """装饰器：自动记录函数执行耗时

    用法:
        @log_execution_time
        def heavy_function():
            ...

        @log_execution_time(level=logging.INFO)
        def important_function():
            ...

    输出:
        [DEBUG] paycheck.xxx: ⏱ heavy_function() 耗时 3.21s
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return f(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - t0
                logger = logging.getLogger(f.__module__)
                if elapsed >= 1.0:
                    unit = "s"
                    val = f"{elapsed:.2f}"
                elif elapsed >= 0.001:
                    unit = "ms"
                    val = f"{elapsed * 1000:.1f}"
                else:
                    unit = "μs"
                    val = f"{elapsed * 1_000_000:.0f}"
                logger.log(level, "⏱ %s() 耗时 %s%s", f.__qualname__, val, unit)
        return wrapper
    if func is None:
        return decorator
    return decorator(func)
