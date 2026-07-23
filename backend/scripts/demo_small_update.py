"""
快速小数据测试 - 仅拉取 5 只股票最近 30 天
用于验证系统完整跑通
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import init_db, query_all, table_count
from updater.parallel_updater import ParallelKlineUpdater
from updater.checkpoint import CheckpointManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("demo")


def main():
    print("="*60)
    print("快速测试: 5 只股票 + 30 天数据")
    print("="*60)

    # 1. 初始化
    init_db()

    # 2. 准备测试股票(手动插入 5 只)
    test_stocks = [
        ("000001", "平安银行", "sz000001", "SZ"),
        ("000002", "万科A", "sz000002", "SZ"),
        ("600000", "浦发银行", "sh600000", "SH"),
        ("600519", "贵州茅台", "sh600519", "SH"),
        ("300750", "宁德时代", "sz300750", "SZ"),
    ]
    with __import__("db.database").database.get_conn() as conn:
        conn.execute("DELETE FROM stock_list")
        conn.executemany("""
            INSERT INTO stock_list
            (code, name, full_code, market, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, test_stocks)
    print(f"  ✓ 插入 {len(test_stocks)} 只测试股票")

    # 3. 重置断点
    cp = CheckpointManager("daily_kline")
    cp.reset()
    print("  ✓ 断点已重置")

    # 4. 拉取
    updater = ParallelKlineUpdater(max_workers=3)
    result = updater.update_all(adjust="qfq", days_back=30)

    # 5. 验证
    total = table_count("kline_daily")
    print(f"\n{'='*60}")
    print(f"数据库现有 K线: {total:,} 行")
    for code, name, _, _ in test_stocks:
        cnt = table_count("kline_daily")  # 全表
        rows = query_all(
            "SELECT COUNT(*) FROM kline_daily WHERE code=?",
            (code,)
        )
        print(f"  {code} {name}: {rows[0][0]} 条")

    print(f"\n✓ 测试完成,共写入 {result.get('rows', 0)} 行")


if __name__ == "__main__":
    main()
