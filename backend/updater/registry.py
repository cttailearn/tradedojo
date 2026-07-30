"""
Updater 注册表 —— 集中管理 TaskType → Updater 子类的映射。
路由层(tasks.py / scheduler.py)只需查表,无需 hardcode if-elif。

注册方式:在下面的 REGISTER 字典添加条目,value = (UpdaterClass, 默认参数 dict)。
新增任务类型时只需:1) types.py 加枚举  2) updater/<name>.py 写 updater 类
                   3) 本文件 import 并登记  4) (可选) DEFAULT_JOBS 加 cron。
"""
from typing import Dict, Tuple, Type

from .base import BaseUpdater
from .types import TaskType


# 延迟 import,避免循环依赖
def _load_stock_list():
    from .stock_list import StockListUpdater, StockListParams
    return StockListUpdater, StockListParams


def _load_stock_enrich():
    from .stock_enrich import StockEnrichUpdater, StockEnrichParams
    return StockEnrichUpdater, StockEnrichParams


def _load_index_daily():
    from .index_daily import IndexDailyUpdater, IndexDailyParams
    return IndexDailyUpdater, IndexDailyParams


def _load_kline_daily():
    from .kline_daily import KlineDailyUpdater, KlineDailyParams
    return KlineDailyUpdater, KlineDailyParams


def _load_fetch_all():
    from .composite import FetchAllUpdater, FetchAllParams
    return FetchAllUpdater, FetchAllParams


def _load_sync_latest():
    from .composite import SyncLatestUpdater, SyncLatestParams
    return SyncLatestUpdater, SyncLatestParams


# TaskType -> (UpdaterClass, ParamModelClass)
REGISTER: Dict[TaskType, Tuple[Type[BaseUpdater], type]] = {
    # ---------- 基础 updater(保留,scheduler/单步任务仍可用) ----------
    TaskType.STOCK_LIST:   _load_stock_list(),
    TaskType.STOCK_ENRICH: _load_stock_enrich(),
    TaskType.INDEX_DAILY:  _load_index_daily(),
    TaskType.KLINE_DAILY:  _load_kline_daily(),
    # ---------- 组合型 updater(面向用户的两个入口) ----------
    TaskType.FETCH_ALL:    _load_fetch_all(),
    TaskType.SYNC_LATEST:  _load_sync_latest(),
}


# 旧任务名 -> 新 TaskType + 默认参数(保持向后兼容)
# 旧前端/旧 API 仍可能传 task="daily_smart" / "index" / "enrich" 等
LEGACY_TASK_ALIAS = {
    # 旧 task 字符串      新 TaskType,         默认参数覆盖
    "stock_list":   (TaskType.STOCK_LIST,   {}),
    "index":        (TaskType.INDEX_DAILY,  {}),
    "kline_daily":  (TaskType.KLINE_DAILY,  {"mode": "full"}),
    "enrich":       (TaskType.STOCK_ENRICH, {}),
    "daily_smart":  (TaskType.SYNC_LATEST,  {"days_back": 10}),
    # 旧 API 完整一键更新 → 新全量入口
    "full_update":  (TaskType.FETCH_ALL,    {"days_back": 365}),
    "oneclick":     (TaskType.FETCH_ALL,    {"days_back": 365}),
}


def resolve_task(task_name: str) -> Tuple[TaskType, dict]:
    """
    把传入的 task 字符串(TaskType 或旧别名)解析为 (TaskType, 默认参数字典)。
    解析失败抛 ValueError,调用方应转为 400。
    """
    # 新枚举
    try:
        tt = TaskType(task_name)
        return tt, {}
    except ValueError:
        pass
    # 旧别名
    if task_name in LEGACY_TASK_ALIAS:
        return LEGACY_TASK_ALIAS[task_name]
    raise ValueError(
        f"未知任务类型: {task_name!r},可选 {[t.value for t in TaskType]}"
    )