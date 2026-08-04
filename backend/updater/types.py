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
    KLINE_PERIODIC = "kline_periodic"  # 周K/月K 本地聚合(kline_daily → kline_minute)

    # ---------- 组合型任务(面向终端用户的两个入口) ----------
    FETCH_ALL = "fetch_all"         # 全量拉取:股票列表 + 行业 + K线 + 指数
    SYNC_LATEST = "sync_latest"     # 增量同步:仅拉最近 K线 + 指数


# 调度器默认 cron 配置(每类一个独立 job)
# 日常调度只需 sync_latest 即可;fetch_all 通常首次或手动触发
DEFAULT_JOBS = [
    # task,         cron,            enabled, params
    ("sync_latest",  "30 16 * * 1-5", True,   {"adjust": "qfq", "days_back": 10, "workers": 4}),
]