"""
项目全局配置
"""
from pathlib import Path

# ---------- 路径配置 ----------
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
LOG_DIR = PROJECT_ROOT / "logs"

# 两个独立 SQLite:
#   STOCK_DB_PATH  股票 + 管理员 (stock_list/kline_daily/index_daily/admin_user 等)
#   USER_DB_PATH   训练用户与训练业务 (training_user/wallet/session/order/redeem_code 等)
# 拆分后两库可独立备份 / 权限管理 / 迁移。
DB_PATH = DATA_DIR / "stock.db"   # = STOCK_DB_PATH,保留向后兼容
USER_DB_PATH = DATA_DIR / "user.db"

# 自动创建目录
for d in [DATA_DIR, CHECKPOINT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ---------- 采集配置 ----------
class FetchConfig:
    """数据采集相关配置"""
    # 限流配置(防止被源站封 IP)
    # NOTE: AKShare 底层调用东方财富接口,服务端限流较严
    # 实测:并发 ≥ 4 时大量 RemoteDisconnected,推荐 ≤ 2
    # 进一步压低并发 + 拉长间隔,避免 14:30~15:00 流量高峰被封
    MAX_CONCURRENT_FETCH = 2        # 最大并发请求数 (从 3 降到 2)
    REQUEST_INTERVAL = 3.0          # 单次请求间隔(秒) (从 2.0 提到 3.0)
    RETRY_TIMES = 3                 # 失败重试次数 (从 5 降到 3,避免长时间占着连接)
    RETRY_BACKOFF = 5.0             # 退避基数(秒) (从 3.0 提到 5.0)
    BACKOFF_JITTER = 0.5            # 退避抖动(避免雷鸣群)

    # Writer 批量写配置
    BATCH_SIZE = 200                # 批量提交大小
    WRITE_INTERVAL = 1.0            # Writer 写盘间隔(秒)

    # 线程池
    MAX_WORKERS = 4                 # (从 6 降到 4,与 MAX_CONCURRENT_FETCH 协调)

    # 历史数据回溯
    DEFAULT_DAYS_BACK = 365         # 默认拉取最近 1 年
    FULL_HISTORY_YEARS = 5          # 全量初始化 5 年


# ---------- 回测配置 ----------
class BacktestConfig:
    """回测默认参数"""
    INITIAL_CASH = 100_000.0
    COMMISSION = 0.0003             # 万三佣金
    STAMP_TAX = 0.001               # 千一印花税(卖出)
    SLIPPAGE = 0.001                # 千一滑点


# ---------- 调度配置 ----------
class ScheduleConfig:
    """定时任务时间"""
    DAILY_UPDATE_TIME = "16:30"     # 日终更新
    MINUTE_UPDATE_INTERVAL = 5      # 分钟级更新间隔(分钟)
    TRADING_MORNING = (9, 30, 11, 30)
    TRADING_AFTERNOON = (13, 0, 15, 0)
