"""BOC PDF 转换任务：内存单例注册表 + 后台线程执行 + 线程安全进度快照

任务模型（设计 §6）：
  - 同一时间仅一个转换任务（GPU / PaddleOCR 模型单例的天然约束）；
    任务在线程内执行，进度通过管线 progress_cb 写入任务对象，轮询接口读取快照。
  - 注册表仅存内存：服务重启后任务失联，前端通过「任务不存在 → interrupted」提示重新开始。
  - device="auto" 的 GPU 探测只在本层做（惰性、缓存），管线与 CLI 保持 gpu/cpu 原语义。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

GPU_UNAVAILABLE_HINT = "未检测到可用 GPU，且推理设备为 GPU。请改用「自动」或「CPU」后重试"

_gpu_cache: Optional[bool] = None
_gpu_lock = threading.Lock()


def gpu_available() -> bool:
    """GPU 可用性（首次调用时惰性探测并缓存，避免拖慢工作台启动）。"""
    global _gpu_cache
    with _gpu_lock:
        if _gpu_cache is None:
            _gpu_cache = _detect_gpu()
        return _gpu_cache


def gpu_available_cached() -> Optional[bool]:
    """返回缓存的探测结果，未探测过返回 None（不触发探测，供 /api/meta 使用）。"""
    return _gpu_cache


def _detect_gpu() -> bool:
    """探测 paddle 是否具备可用的 GPU 推理环境（仅探测，不加载 OCR 模型）。

    torch 必须先于 paddle 导入：Windows 上 paddle 的 DLL 搜索路径会干扰 torch
    加载自身的 shm.dll（WinError 127），与 ocr_engine 的导入顺序保持一致。
    GPU 可用 = CUDA 编译 + 设备数 > 0 + cudnn DLL 就位（缺 cudnn 时 GPU 推理
    运行时必失败，auto 模式按不可用处理走 CPU）。
    """
    try:
        import torch  # noqa: F401
        import paddle
        if not (paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0):
            return False
        return _cudnn_available(paddle)
    except Exception:
        return False


def _cudnn_available(paddle) -> bool:
    """cudnn DLL 是否可加载（仅 Windows 检查；其余平台交由 paddle 自行处理）。"""
    if os.name != "nt":
        return True
    import ctypes

    # 与 ocr_engine._add_nvidia_dll_dirs 同源：pip 安装的 nvidia-*-cu12 包
    site_packages = os.path.dirname(os.path.dirname(os.path.abspath(paddle.__file__)))
    nvidia_root = os.path.join(site_packages, "nvidia")
    if os.path.isdir(nvidia_root):
        for name in os.listdir(nvidia_root):
            bin_dir = os.path.join(nvidia_root, name, "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
    try:
        ctypes.WinDLL("cudnn64_9.dll")
        return True
    except OSError:
        return False


class JobBusy(Exception):
    """已有转换任务运行中"""

    def __init__(self, job_id: str):
        super().__init__("已有转换任务进行中")
        self.job_id = job_id


class ConvertFile:
    """单个 PDF 的转换状态（字段仅在任务锁内读写）。"""

    def __init__(self, name: str):
        self.name = name
        self.state = "waiting"  # waiting / running / done / skipped / failed
        self.pages_done = 0
        self.pages_total = 0
        self.transactions = 0
        self.duration_s = 0.0
        self.error: Optional[str] = None


class ConvertJob:
    """单个转换任务：文件状态 + 汇总，线程安全。"""

    def __init__(self, file_names: List[str]):
        self.id = uuid.uuid4().hex
        self.files = [ConvertFile(name) for name in file_names]
        self.status = "running"  # running / done / partial / failed
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.finished_at: Optional[str] = None
        self.gpu_hint: Optional[str] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self.status == "running"

    def set_gpu_hint(self, hint: str) -> None:
        with self._lock:
            self.gpu_hint = hint

    def _by_name(self, name) -> Optional[ConvertFile]:
        for f in self.files:
            if f.name == name:
                return f
        return None

    def update(self, event: str, info: dict) -> None:
        """管线 progress_cb 入口：按事件推进文件状态（忽略本任务外的文件名）。"""
        info = info or {}
        with self._lock:
            if event == "engine_loading":
                # 模型加载事件不带文件名：推进第一个等待中的文件
                for f in self.files:
                    if f.state == "waiting":
                        f.state = "running"
                        break
            elif event == "pdf_start":
                f = self._by_name(info.get("name"))
                if f:
                    f.state = "running"
                    f.pages_total = int(info.get("pages_total") or 0)
            elif event == "page_done":
                f = self._by_name(info.get("name"))
                if f:
                    f.state = "running"
                    f.pages_done = int(info.get("page") or 0)
                    f.pages_total = int(info.get("pages_total") or f.pages_total or 0)
                    f.transactions = int(info.get("transactions_so_far") or 0)
            elif event == "pdf_done":
                f = self._by_name(info.get("name"))
                if f:
                    f.state = "done"
                    f.transactions = int(info.get("transactions") or 0)
                    f.duration_s = float(info.get("duration_s") or 0)
            elif event == "pdf_skipped":
                f = self._by_name(info.get("name"))
                if f:
                    f.state = "skipped"
                    f.error = None
            elif event == "pdf_failed":
                f = self._by_name(info.get("name"))
                if f:
                    f.state = "failed"
                    f.error = self._map_error(str(info.get("error") or "未知错误"))

    def _map_error(self, error: str) -> str:
        # 强制 GPU 但无 GPU：管线报错文案换成页面语境（设计 §5.2）
        if self.gpu_hint and "未检测到可用 GPU" in error:
            return self.gpu_hint
        return error

    def fail_remaining(self, message: str) -> None:
        """把未进入终态的文件标记为失败（管线异常兜底）。"""
        with self._lock:
            for f in self.files:
                if f.state in ("waiting", "running"):
                    f.state = "failed"
                    f.error = message

    def settle_silent_files(self, convert_dir) -> None:
        """管线正常返回后补齐无事件文件的终态（服务端层，管线零改动）。

        渲染 0 图等提前返回路径不发进度事件，但 CLI 语义已写出表头 CSV 并计为
        已处理——按同名 CSV 是否存在补记 done（0 条）/ failed。
        """
        with self._lock:
            for f in self.files:
                if f.state not in ("waiting", "running"):
                    continue
                csv_path = Path(convert_dir) / (Path(f.name).stem + ".csv")
                if csv_path.exists():
                    f.state = "done"
                    f.transactions = 0
                else:
                    f.state = "failed"
                    f.error = f.error or "转换未完成（服务异常）"

    def finish(self) -> None:
        """任务收尾：补齐遗漏终态并汇总状态。"""
        with self._lock:
            for f in self.files:
                if f.state in ("waiting", "running"):
                    f.state = "failed"
                    f.error = f.error or "转换未完成（服务异常）"
            done = sum(1 for f in self.files if f.state == "done")
            skipped = sum(1 for f in self.files if f.state == "skipped")
            failed = sum(1 for f in self.files if f.state == "failed")
            if failed == 0:
                self.status = "done"
            elif done == 0 and skipped == 0:
                self.status = "failed"
            else:
                self.status = "partial"
            self.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def snapshot(self) -> dict:
        """轮询接口返回的任务快照。"""
        with self._lock:
            done = sum(1 for f in self.files if f.state == "done")
            skipped = sum(1 for f in self.files if f.state == "skipped")
            failed = sum(1 for f in self.files if f.state == "failed")
            transactions = sum(f.transactions for f in self.files if f.state == "done")
            return {
                "status": self.status,
                "files": [
                    {
                        "name": f.name,
                        "state": f.state,
                        "pages_done": f.pages_done,
                        "pages_total": f.pages_total,
                        "transactions": f.transactions,
                        "duration_s": round(f.duration_s, 1),
                        "error": f.error,
                    }
                    for f in self.files
                ],
                "totals": {
                    "done": done,
                    "skipped": skipped,
                    "failed": failed,
                    "transactions": transactions,
                },
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


# ---------------------------------------------------------------------------
# 内存单例任务注册表（服务重启即失联）
# ---------------------------------------------------------------------------

_jobs: Dict[str, ConvertJob] = {}
_current: Optional[ConvertJob] = None
_start_lock = threading.Lock()


def start_job(file_names: List[str]) -> ConvertJob:
    """登记新任务；已有任务运行中时抛 JobBusy。"""
    global _current
    with _start_lock:
        if _current is not None and _current.is_running():
            raise JobBusy(_current.id)
        job = ConvertJob(file_names)
        _jobs[job.id] = job
        _current = job
        return job


def get_job(job_id: str) -> Optional[ConvertJob]:
    return _jobs.get(job_id)


def current_running() -> Optional[ConvertJob]:
    if _current is not None and _current.is_running():
        return _current
    return None


def run_convert_job(job: ConvertJob, convert_dir, scale: float, device: str,
                    timeout_minutes: int, force: bool) -> None:
    """后台线程执行体：解析 device、惰性导入管线、运行并维护任务状态。"""
    try:
        gpu = gpu_available()
        resolved = device if device != "auto" else ("gpu" if gpu else "cpu")
        if resolved == "gpu" and not gpu:
            job.set_gpu_hint(GPU_UNAVAILABLE_HINT)

        from boc_pdf2csv.pipeline import process_folder

        try:
            process_folder(
                str(convert_dir),
                scale=scale,
                timeout_minutes=timeout_minutes,
                device=resolved,
                force=force,
                progress_cb=job.update,
                pdf_names=[f.name for f in job.files],
            )
        except Exception as exc:
            job.fail_remaining(str(exc))
        else:
            # 管线正常返回但个别文件未收到事件（如渲染 0 图提前返回）：
            # 按同名 CSV 是否存在补记终态，与 CLI 结果口径一致
            job.settle_silent_files(convert_dir)
    finally:
        job.finish()
