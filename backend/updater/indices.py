"""
关键指数统一清单(单一数据源)。

采集端 (IndexDailyUpdater / ParallelKlineUpdater.update_index / check_missing)
与训练端 (/api/train/indices) 必须引用同一份,避免维护漂移。

新增/删除指数:只需修改本文件。
- 字段说明:
    code      数据源统一格式(baostock / ak-share / tushare 通用)
    name      中文名
    market    SH / SZ
"""
from typing import List, Dict


# 完整 7 只关键指数(覆盖大中小盘 + 创业板/科创板)
KEY_INDICES: List[Dict[str, str]] = [
    {"code": "sh000001", "name": "上证综指", "market": "SH"},
    {"code": "sz399001", "name": "深证成指", "market": "SZ"},
    {"code": "sh000300", "name": "沪深300",  "market": "SH"},
    {"code": "sh000905", "name": "中证500",  "market": "SH"},
    {"code": "sz399006", "name": "创业板指", "market": "SZ"},
    {"code": "sh000688", "name": "科创50",   "market": "SH"},
    {"code": "sh000016", "name": "上证50",   "market": "SH"},
]


# 仅 code 列表(便于采集端循环)
KEY_INDEX_CODES: List[str] = [idx["code"] for idx in KEY_INDICES]


def is_key_index(code: str) -> bool:
    """判断 code 是否在关键指数清单中"""
    return code in KEY_INDEX_CODES