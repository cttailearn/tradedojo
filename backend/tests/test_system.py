"""
单元测试 - 不依赖网络

运行(在 backend/ 目录下):
    uv run python tests/test_system.py
    # 或: uv run pytest tests/
"""
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

# 把 backend/ 加进 sys.path 以便导入 config / db / updater 等
sys.path.insert(0, str(Path(__file__).parent.parent))

# 使用临时 DB 跑测试
TEST_DIR = Path(tempfile.mkdtemp(prefix="stock_test_"))
os.environ["STOCK_TEST"] = "1"

from config import DB_PATH
import db.database as db_module
db_module.DB_PATH = TEST_DIR / "test.db"

from db.database import init_db, get_conn, query_one, query_all
from updater.checkpoint import CheckpointManager


def test_db_init():
    """测试数据库初始化"""
    print("Test 1: 数据库初始化")
    init_db(verbose=False)
    tables = [r[0] for r in query_all(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )]
    expected = {'stock_list', 'kline_daily', 'kline_minute',
                'index_daily', 'update_log'}
    assert expected.issubset(set(tables)), f"缺失表: {expected - set(tables)}"
    print(f"  ✓ {len(tables)} 个表已创建")


def test_checkpoint_basic():
    """测试断点续传基础流程"""
    print("\nTest 2: 断点续传")
    cp = CheckpointManager("test_basic", max_retry=2)
    cp.reset()  # 先清空,避免上次运行污染

    # 初始状态
    assert len(cp.completed) == 0
    assert cp.need_retry("000001")

    # 标记成功
    cp.mark_success("000001", 100)
    assert cp.is_done("000001")
    assert not cp.need_retry("000001")

    # 标记失败 + 重试
    cp.mark_failed("000002", "网络超时")
    assert cp.need_retry("000002")

    # 模拟重启
    cp.save_snapshot()
    cp2 = CheckpointManager("test_basic", max_retry=2)
    assert cp2.is_done("000001")
    assert cp2.need_retry("000002")
    print("  ✓ 断点保存/恢复正常")


def test_checkpoint_retry_exhausted():
    """测试重试耗尽"""
    print("\nTest 3: 重试耗尽保护")
    cp = CheckpointManager("test_retry", max_retry=2)
    cp.mark_failed("600000", "err1")  # retry=1
    cp.mark_failed("600000", "err2")  # retry=2
    assert not cp.need_retry("600000"), "应停止重试"
    print("  ✓ 重试超过上限后不再处理")


def test_wal_mode():
    """测试 WAL 模式生效"""
    print("\nTest 4: WAL 模式")
    with get_conn() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"期望 WAL,实际 {mode}"
    print(f"  ✓ journal_mode = {mode}")


def test_upsert():
    """测试 INSERT OR REPLACE"""
    print("\nTest 5: 写入/更新")
    with get_conn() as conn:
        conn.execute("DELETE FROM kline_daily")
        conn.execute("""
            INSERT INTO kline_daily
            (code, trade_date, close, volume, adjust_type)
            VALUES (?, ?, ?, ?, ?)
        """, ("000001", "2024-01-01", 10.5, 1000, "qfq"))

        # 查询
        row = query_one(
            "SELECT close FROM kline_daily WHERE code=? AND trade_date=?",
            ("000001", "2024-01-01")
        )
        assert row[0] == 10.5

        # REPLACE
        conn.execute("""
            INSERT OR REPLACE INTO kline_daily
            (code, trade_date, close, volume, adjust_type)
            VALUES (?, ?, ?, ?, ?)
        """, ("000001", "2024-01-01", 11.0, 1500, "qfq"))

        row = query_one(
            "SELECT close, volume FROM kline_daily WHERE code=? AND trade_date=?",
            ("000001", "2024-01-01")
        )
        assert row[0] == 11.0
        assert row[1] == 1500
    print("  ✓ 写入/替换正常")


def test_data_fetcher_normalize():
    """测试市场代码识别"""
    print("\nTest 6: 市场代码识别")
    try:
        from fetcher.data_fetcher import _normalize_market
    except ImportError as e:
        print(f"  跳过(缺依赖): {e}")
        return
    assert _normalize_market("600000") == "sh"
    assert _normalize_market("000001") == "sz"
    assert _normalize_market("300750") == "sz"
    assert _normalize_market("688981") == "sh"
    assert _normalize_market("833454") == "bj"
    print("  ✓ 各市场代码前缀识别正确")


def test_backtest_imports():
    """测试 Backtrader 相关导入"""
    print("\nTest 7: Backtrader 集成")
    try:
        from backtest.sqlite_feed import SQLiteData
        from backtest.strategies import (
            SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy
        )
        from backtest.runner import run_backtest, run_portfolio, AShareCommInfo
        print("  ✓ 所有 backtrader 模块导入成功")
    except ImportError as e:
        print(f"  跳过(缺依赖): {e}")
        return


def test_comm_info():
    """测试 A股手续费模型"""
    print("\nTest 8: A股手续费")
    try:
        from backtest.runner import AShareCommInfo
    except ImportError as e:
        print(f"  跳过(缺依赖): {e}")
        return
    comm = AShareCommInfo()

    # 用大额交易测试(避免最低 5 元佣金触发)
    # 买入 10000 股,价格 50 元 = 50万
    buy = comm._getcommission(10000, 50.0, pseudoexec=True)
    # 卖出 10000 股,价格 50 元
    sell = comm._getcommission(-10000, 50.0, pseudoexec=True)

    # 期望:
    # buy = 500000 * 0.0003 = 150
    # sell = 150 + 500000 * 0.001 = 650
    expected_buy = 500000 * 0.0003
    expected_sell = expected_buy + 500000 * 0.001

    print(f"  买入手续费: {buy:.2f} (期望 {expected_buy:.2f})")
    print(f"  卖出手续费: {sell:.2f} (期望 {expected_sell:.2f})")
    assert abs(buy - expected_buy) < 0.01
    assert abs(sell - expected_sell) < 0.01
    assert sell > buy, "卖出应比买入贵(印花税)"
    print("  ✓ 手续费模型正确(佣金+印花税)")

    # 测试最低佣金
    comm_min = comm._getcommission(10, 10.0, pseudoexec=True)
    assert comm_min >= 5.0, "应触发最低 5 元"
    print(f"  最低佣金: {comm_min:.2f} (应 >= 5)")


def run_all():
    """运行所有测试"""
    print("="*60)
    print("单元测试 - A股数据系统")
    print("="*60)

    tests = [
        test_db_init, test_checkpoint_basic, test_checkpoint_retry_exhausted,
        test_wal_mode, test_upsert, test_data_fetcher_normalize,
        test_backtest_imports, test_comm_info,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ 失败: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"测试结果: {passed} 通过 / {failed} 失败 / {passed+failed} 总计")
    print("="*60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
