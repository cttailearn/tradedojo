"""
数据更新任务类型枚举 —— 按数据类型划分,每个类型对应一个 updater 子模块。
新增任务只需: 1) 在此加枚举 2) 新建 updater/<type>.py 3) 在 registry.py 注册。
"""
from enum import Enum


class TaskType(str, Enum):
    STOCK_LIST = "stock_list"       # 股票基础信息
    STOCK_ENRICH = "stock_enrich"   # 股票信息增强(写入 stock_list 扩展列)
    INDEX_DAILY = "index_daily"     # 主要指数日线
    KLINE_DAILY = "kline_daily"     # 日 K 线(含 mode=full/smart)


# 调度器默认 cron 配置(每类一个独立 job)
DEFAULT_JOBS = [
    # task,         cron,            enabled, params
    ("stock_list",   "0 8 * * 1-5",   True,   {}),
    ("index_daily",  "15 16 * * 1-5", True,   {}),
    ("kline_daily",  "30 16 * * 1-5", True,   {"mode": "smart", "adjust": "qfq", "days_back": 365, "workers": 6}),
    ("stock_enrich", "0 2 * * 0",     False,  {"limit": None}),
]