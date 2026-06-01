"""日志配置模块

用法:
    from paycheck.core.log import setup_logging
    setup_logging(verbose=args.verbose)

然后在各模块中:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("...")
"""

import logging
import logging.handlers
import os
import sys
import warnings
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
