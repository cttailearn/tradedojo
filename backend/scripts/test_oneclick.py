"""
一键更新 - 真实端到端测试
限制 5 只股票,模拟 "已有日K + 缺分时" 场景
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

from updater.parallel_updater import ParallelKlineUpdater
from updater.checkpoint import CheckpointManager
from db.database import get_conn, query_one

# 准备场景:5 只活跃股票
TEST_CODES = ['000001', '000002', '600000', '600519', '300750']

with get_conn() as conn:
    conn.execute("UPDATE stock_list SET is_active = 0")
    placeholders = ','.join(['?'] * len(TEST_CODES))
    conn.execute(
        f"UPDATE stock_list SET is_active = 1 WHERE code IN ({placeholders})",
        TEST_CODES
    )
    print(f"[Setup] 激活 {len(TEST_CODES)} 只: {TEST_CODES}")

# 重置分时断点(模拟无分时)
CheckpointManager("minute_kline_5min").reset()
print("[Setup] 分时断点已重置\n")

# 执行 update_daily_smart
u = ParallelKlineUpdater(max_workers=2)
result = u.update_daily_smart(
    adjust='qfq',
    minute_period=5,
    minute_days=30,
    daily_days_back=1825,
    kline_workers=2,
    minute_workers=2,
)

# 恢复
with get_conn() as conn:
    conn.execute("UPDATE stock_list SET is_active = 1")

print(f"\n[结果] {result}")
print(f"\n数据库现状:")
print(f"  kline_daily:  {query_one('SELECT COUNT(*) FROM kline_daily')[0]:>8} 行")
print(f"  kline_minute: {query_one('SELECT COUNT(*) FROM kline_minute')[0]:>8} 行")
