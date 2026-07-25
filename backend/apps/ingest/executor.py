"""线程池执行器 — 替代 Celery 的异步任务调度

单例 ThreadPoolExecutor，在 Django 进程内执行导入任务。
"""

import atexit
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List

logger = logging.getLogger("paycheck.ingest.executor")

# 模块级单例
_executor: ThreadPoolExecutor | None = None
MAX_WORKERS = 4


def get_executor() -> ThreadPoolExecutor:
    """获取全局线程池（懒初始化 + atexit 优雅关闭）"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="ingest-",
        )
        atexit.register(_shutdown)
        logger.info("ThreadPoolExecutor initialized (max_workers=%d)", MAX_WORKERS)
    return _executor


def _shutdown(wait: bool = True, timeout: float = 30.0) -> None:
    """atexit 回调：优雅关闭线程池"""
    global _executor
    if _executor is not None:
        logger.info("Shutting down ThreadPoolExecutor...")
        _executor.shutdown(wait=wait, cancel_futures=not wait)
        if wait:
            logger.info("ThreadPoolExecutor shut down.")
        _executor = None


def run_parallel(
    tasks: List[Callable],
    callback: Callable | None = None,
    callback_args: tuple | None = None,
) -> List:
    """并行执行多个任务，全部完成后调用回调（等价 Celery chord）

    Args:
        tasks: 无参 callable 列表
        callback: 全部完成后调用的回调函数，接收 (results_list, *callback_args)
        callback_args: 传递给回调的额外位置参数

    Returns:
        每个任务的返回值列表（保持与 tasks 相同的顺序）
    """
    executor = get_executor()
    future_to_idx = {
        executor.submit(task): idx
        for idx, task in enumerate(tasks)
    }

    # 收集结果，保持原始顺序
    results: List = [None] * len(tasks)
    errors: List[Exception] = []

    for future in as_completed(future_to_idx):
        idx = future_to_idx[future]
        try:
            results[idx] = future.result()
        except Exception as exc:
            logger.exception("Task %d failed: %s", idx, exc)
            results[idx] = exc
            errors.append(exc)

    # 回调（即使部分任务失败也执行）
    if callback is not None:
        args = callback_args or ()
        callback(results, *args)

    return results
