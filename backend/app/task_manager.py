"""
后台任务管理器
- 使用 threading 在 FastAPI 中执行耗时任务(更新/回测)
- 维护内存中的任务状态,支持前端轮询
- 日志通过 logging 写入 settings.LOG_DIR,并保留最近 200 行
"""
import inspect
import logging
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Callable, Dict, Optional

from app.config import settings


def _func_accepts_progress_callback(func: Callable) -> bool:
    """
    检查函数是否声明了 progress_callback 参数(或有 **kwargs)
    - 有命名参数 progress_callback → True
    - 有 **kwargs → True
    - 否则 → False(避免传错参数导致 TypeError)
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        # 内置函数 / C 扩展无法 inspect,默认不接受
        return False
    if "progress_callback" in sig.parameters:
        return True
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False


# ---- 日志收集器 ----
class _TailLogHandler(logging.Handler):
    """把日志同时推送到指定任务的 log_tail"""

    def __init__(self):
        super().__init__()
        self._buffers: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def attach(self, task_id: str, maxlen: int = 200):
        with self._lock:
            self._buffers[task_id] = deque(maxlen=maxlen)

    def detach(self, task_id: str):
        with self._lock:
            self._buffers.pop(task_id, None)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        with self._lock:
            for buf in self._buffers.values():
                buf.append(msg)


_tail_handler = _TailLogHandler()
_tail_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
)
logging.getLogger().addHandler(_tail_handler)
# 确保根 logger 至少有 INFO 级别
if logging.getLogger().level > logging.INFO or not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


# ---- 文件日志 ----
def _ensure_file_logger():
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = settings.LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    root = logging.getLogger()
    # 避免重复添加
    has_file = any(
        isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_file)
        for h in root.handlers
    )
    if not has_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        )
        root.addHandler(fh)


_ensure_file_logger()


# ---- 任务状态 ----
class TaskRecord:
    def __init__(self, task_id: str, name: str):
        self.task_id = task_id
        self.name = name
        self.status = "pending"
        self.progress = {}
        self.started_at: Optional[str] = None
        self.ended_at: Optional[str] = None
        self.message = ""
        self._error: Optional[str] = None

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "task_id": self.task_id,
                "task_name": self.name,
                "status": self.status,
                "progress": dict(self.progress),
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "message": self.message,
                "log_tail": list(_tail_handler._buffers.get(self.task_id, [])),
            }

    _lock = threading.Lock()


# ---- 任务管理器 ----
class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, func: Callable, *args, **kwargs) -> str:
        task_id = f"{name}_{int(time.time() * 1000)}"
        rec = TaskRecord(task_id, name)
        with self._lock:
            self._tasks[task_id] = rec

        _tail_handler.attach(task_id)

        def _wrapper():
            rec.status = "running"
            rec.started_at = datetime.now().isoformat(timespec="seconds")
            try:
                # 只在函数接受 progress_callback 时才注入,避免 TypeError
                if _func_accepts_progress_callback(func):
                    kwargs["progress_callback"] = lambda p: self._update_progress(rec, p)
                result = func(*args, **kwargs)
                rec.status = "success"
                rec.message = "完成"
                if isinstance(result, dict):
                    rec.progress["result"] = result
            except Exception as e:
                rec.status = "failed"
                rec.message = f"{type(e).__name__}: {e}"
                rec._error = traceback.format_exc()
                logging.error(f"[Task:{task_id}] 失败: {e}\n{rec._error}")
            finally:
                rec.ended_at = datetime.now().isoformat(timespec="seconds")
                # 日志保留 30 秒后清理
                def _cleanup():
                    time.sleep(30)
                    _tail_handler.detach(task_id)
                threading.Thread(target=_cleanup, daemon=True).start()

        t = threading.Thread(target=_wrapper, name=f"Task-{task_id}", daemon=True)
        with self._lock:
            self._threads[task_id] = t
        t.start()
        return task_id

    def _update_progress(self, rec: TaskRecord, progress: dict):
        rec.progress.update(progress)

    def get(self, task_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._tasks.get(task_id)
            return rec.to_dict() if rec else None

    def list_recent(self, limit: int = 20) -> list:
        with self._lock:
            recs = sorted(
                self._tasks.values(),
                key=lambda r: r.started_at or "",
                reverse=True,
            )[:limit]
        return [r.to_dict() for r in recs]


task_manager = TaskManager()