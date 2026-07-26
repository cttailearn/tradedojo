"""
Updater 基类 —— 统一参数校验、日志前缀、中断标志、进度回调。
每个数据类型的 updater 继承此类,实现 run() 方法即可。
"""
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from .types import TaskType


class BaseUpdater(ABC):
    """所有 updater 的基类"""

    # 子类必须声明:
    task_type: TaskType
    ParamModel: type[BaseModel]

    # 子类可重写:用于日志前缀显示
    display_name: str = ""

    def __init__(self, params: Optional[dict] = None):
        if self.ParamModel is None:
            raise RuntimeError(f"{type(self).__name__} 未声明 ParamModel")
        self.params = self.ParamModel(**(params or {}))
        self._interrupted = threading.Event()
        self._log_prefix = f"[{self.task_type.value}]"
        self.logger = logging.getLogger(f"updater.{self.task_type.value}")

    @abstractmethod
    def run(self, progress_callback=None) -> dict:
        """
        执行更新,返回统计字典(dict 会写入 task_manager.progress["result"])。
        progress_callback(dict) 可被调用以更新前端进度。
        """
        ...

    def request_stop(self):
        """外部(信号/停止按钮)调用,要求优雅退出"""
        self._interrupted.set()
        self.logger.warning(f"{self._log_prefix} 收到停止请求")

    def is_interrupted(self) -> bool:
        return self._interrupted.is_set()

    def _progress(self, callback, **kw):
        if callback:
            try:
                callback(kw)
            except Exception as e:  # 进度回调失败不影响主流程
                self.logger.debug(f"progress callback error: {e}")