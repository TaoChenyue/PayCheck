"""Django 日志配置模块 — 由 ``src/paycheck/core/log.py`` 迁移而来。

提供 Django ``LOGGING`` 配置字典（由 settings.py 自动加载）以及
日志工具函数：``get_logger()``、``log_time()``（上下文管理器）、
``log_execution_time()``（装饰器）。

用法::

    # settings.py 中自动引入 LOGGING 配置
    from config.logging import LOGGING

    # 工具函数
    from config.logging import get_logger, log_time, log_execution_time

    log = get_logger()
    log.info("处理了 %d 条交易", count)

    @log_execution_time
    def slow_function():
        ...

    with log_time("OCR 识别"):
        result = do_ocr()

行为:
    - 文件日志：自动写入 ``log/paycheck.log``，按 10MB×5 份轮转
    - 控制台：DEBUG 模式下 paycheck logger 同时输出到 stderr
    - 自动压制 paddle/PIL/matplotlib/urllib3 等第三方库噪声
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

# ── 目录与常量 ────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_DIR = os.path.join(BASE_DIR, "log")
_DEFAULT_LOG_FILE = "paycheck.log"

# 单个日志文件最大 10MB，保留 5 份备份
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

# 确保日志目录存在
os.makedirs(_DEFAULT_LOG_DIR, exist_ok=True)

_is_debug = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")


# =========================================================================
# Django LOGGING 配置字典
# =========================================================================

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
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(_DEFAULT_LOG_DIR, _DEFAULT_LOG_FILE),
            "maxBytes": _LOG_MAX_BYTES,
            "backupCount": _LOG_BACKUP_COUNT,
            "encoding": "utf-8",
            "formatter": "verbose_file",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "paycheck": {
            "handlers": ["console", "file"] if _is_debug else ["file"],
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
    },
}


def enable_file_logging(
    log_dir: str = _DEFAULT_LOG_DIR,
    log_file: str = _DEFAULT_LOG_FILE,
) -> None:
    """启用自定义路径的文件日志（RotatingFileHandler）。

    当默认 LOGGING 配置中的日志路径不满足需求时（如 CI 环境），
    在 manage.py 或 AppConfig.ready() 中调用此函数覆盖。

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


# =========================================================================
# 模块加载时自动压制第三方库噪声
# =========================================================================

# 在 settings.py import 本模块时立即生效，无需手动调用。
suppress_noisy_loggers()
