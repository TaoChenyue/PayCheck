"""日志配置模块

用法:
    from paycheck.core.log import setup_logging, get_logger, log_time
    setup_logging(verbose=args.verbose)

然后在各模块中:
    log = get_logger()  # 等价于 logging.getLogger(__name__)
    log.info("处理了 %d 条交易", count)

计时装饰器:
    @log_time
    def slow_function():
        ...  # 函数进入/退出时自动记录耗时

上下文管理器:
    with log_time("OCR 识别"):
        result = do_ocr()  # 记录该代码块的执行时间
"""

import functools
import logging
import logging.handlers
import os
import sys
import time
import warnings
from contextlib import contextmanager
from typing import Optional


_LOG_CONFIGURED = False

# 单个日志文件最大 10MB，保留 5 份备份
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def setup_logging(
    verbose: bool = False,
    log_dir: str = "log",
    log_file: str = "paycheck.log",
) -> logging.Logger:
    """配置日志系统

    行为:
        - 始终在 log_dir 下写日志文件（按大小轮转，上限 10MB×5 份）
        - verbose=True 时同时输出到控制台 (stderr)
        - 压制第三方库的烦人日志

    Args:
        verbose: 是否在控制台输出日志
        log_dir: 日志目录
        log_file: 日志文件名（默认 paycheck.log）

    Returns:
        paycheck 根日志器
    """
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return logging.getLogger("paycheck")

    # 日志目录
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, log_file)

    # ── 根日志器 ──
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 清除已有 handler（避免重复配置）
    root.handlers.clear()

    # 文件 handler: 按大小轮转（默认 10MB），保留 5 份
    fh = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # 控制台 handler: 仅 verbose 模式
    if verbose:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(ch)

    # ── 压制第三方库噪声 ──
    for name in [
        "paddle", "paddleocr", "ppocr",
        "PIL", "matplotlib", "fitz",
        "urllib3", "requests", "chardet", "charset_normalizer",
    ]:
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).propagate = False

    # 压制 Python 警告
    warnings.filterwarnings("ignore", category=UserWarning, module="paddle")
    warnings.filterwarnings("ignore", category=UserWarning, module="ppocr")
    warnings.filterwarnings("ignore", message=".*urllib3.*or.*chardet.*doesn't match")


    _LOG_CONFIGURED = True
    logger = logging.getLogger("paycheck")
    logger.info("=" * 50)
    logger.info("PayCheck 启动")
    logger.info(f"日志文件: {log_path}")
    logger.info(f"Verbose: {verbose}")
    logger.info("=" * 50)
    return logger


# =========================================================================
# 日志辅助函数
# =========================================================================


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 paycheck 日志器（推荐替代 logging.getLogger(__name__)）

    用法:
        from paycheck.core.log import get_logger
        log = get_logger()  # 自动使用 __name__
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
def log_time(label: str = "", level: int = logging.DEBUG, logger: Optional[logging.Logger] = None):
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
