"""
CLI 命令行工具 - 兼容入口,与 Web UI 共享同一份代码

用法(需在 backend/ 目录下):
    uv run cli.py init
    uv run cli.py update kline --days 365
    uv run cli.py backtest --code 000001
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# cli.py 本身在 backend/ 下,所以 backend/ 就是它的父目录
_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 先注入仓库根 .env,再 import config(否则 STOCK_DB_* / STOCK_SECRET_KEY 等读不到)
from dotenv import load_dotenv
_PROJECT_ROOT = Path(_BACKEND).parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from config import LOG_DIR, PROJECT_ROOT
from db.database import init_db, table_count, table_names


def setup_logging(level: str = "INFO"):
    """配置日志"""
    log_file = LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("main")


logger = setup_logging()


# ---------- 命令实现 ----------
def cmd_init(args):
    """初始化数据库"""
    print("="*60)
    print("初始化数据库")
    print("="*60)
    init_db(verbose=True)

    tables = table_names()
    print(f"\n表清单({len(tables)}):")
    for t in tables:
        cnt = table_count(t)
        print(f"  - {t:<30} {cnt:>10,} 行")


def cmd_update_stock_list(args):
    """更新股票列表"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater()
    n = updater.update_stock_list()
    print(f"[OK] 股票列表已更新,共 {n} 只")


def cmd_update_kline(args):
    """更新 K线"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater(max_workers=args.workers)
    result = updater.update_all(
        adjust=args.adjust,
        only_active=not args.include_delisted,
        days_back=args.days,
    )
    print(f"\n[OK] 完成: {result}")


def cmd_update_index(args):
    """更新指数"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater()
    n = updater.update_index()
    print(f"[OK] 指数 {n} 个已更新")


def cmd_update_minute(args):
    """更新分钟K线"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater(max_workers=args.workers)
    result = updater.update_minute_all(
        period=args.period,
        days_back=args.days,
        only_active=not args.include_delisted,
        limit=args.limit,
    )
    print(f"\n[OK] 分时K线完成: {result}")


def cmd_update_minute_smart(args):
    """智能更新分钟K线(只更新缺失的)"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater(max_workers=args.workers)
    result = updater.update_minute_smart(
        period=args.period,
        days_back=args.days,
        workers=args.workers,
        limit=args.limit,
    )
    print(f"\n[OK] 分钟K线智能更新完成: {result}")


def cmd_update_periodic(args):
    """聚合周K/月K(从 kline_daily 本地聚合写入 kline_minute)"""
    from updater.kline_periodic import KlinePeriodicUpdater
    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None
    if not all(codes or []):
        codes = None
    updater = KlinePeriodicUpdater({
        "period": args.period,
        "adjust": args.adjust,
        "codes": codes,
    })
    result = updater.run()
    print(f"\n[OK] 周期K线完成: {result}")


def cmd_update_enrich(args):
    """丰富股票信息(行业+上市日期)"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater()
    result = updater.enrich_stock_info(
        enrich_workers=args.workers,
        profile_limit=args.limit,
    )
    print(f"\n[OK] 股票信息丰富完成: {result}")


def cmd_update_all(args):
    """全量更新(列表+指数+K线+信息丰富)"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater(max_workers=args.workers)
    print("="*60)
    print("阶段 1/4: 更新股票列表")
    print("="*60)
    updater.update_stock_list()
    print("\n" + "="*60)
    print("阶段 2/4: 丰富股票信息(行业+上市日期)")
    print("="*60)
    updater.enrich_stock_info(
        enrich_workers=args.enrich_workers,
        profile_limit=args.enrich_limit,
    )
    print("\n" + "="*60)
    print("阶段 3/4: 更新主要指数")
    print("="*60)
    updater.update_index()
    print("\n" + "="*60)
    print("阶段 4/4: 更新日 K线")
    print("="*60)
    updater.update_all(
        adjust=args.adjust,
        only_active=not args.include_delisted,
        days_back=args.days,
    )
    print("\n[OK] 全部更新完成")


def cmd_status(args):
    """查看数据状态"""
    print("="*60)
    print("数据状态")
    print("="*60)
    tables = ['stock_list', 'kline_daily', 'kline_minute',
              'index_daily', 'update_log']
    for t in tables:
        try:
            cnt = table_count(t)
            print(f"  {t:<20} {cnt:>10,} 行")
        except Exception:
            print(f"  {t:<20}  (表不存在)")

    # K线按复权类型统计
    rows = query_all(
        "SELECT adjust_type, COUNT(*), MIN(trade_date), MAX(trade_date) "
        "FROM kline_daily GROUP BY adjust_type"
    )
    if rows:
        print(f"\nK线按复权类型:")
        print(f"  {'类型':<10} {'条数':>10} {'起始':<12} {'最新':<12}")
        for r in rows:
            print(f"  {r[0]:<10} {r[1]:>10,} {r[2] or '-':<12} {r[3] or '-':<12}")

    # 最近更新日志
    print(f"\n最近 5 条更新日志:")
    logs = query_all(
        "SELECT task_name, status, affected_rows, start_time, message "
        "FROM update_log ORDER BY id DESC LIMIT 5"
    )
    for log in logs:
        print(f"  [{log[3]}] {log[0]:<20} {log[1]:<8} rows={log[2]}")


def cmd_check(args):
    """检查数据缺失情况(不更新)"""
    from updater.parallel_updater import ParallelKlineUpdater
    print("="*60)
    print("数据缺失检查")
    print("="*60)
    updater = ParallelKlineUpdater()
    report = updater.check_missing()

    # 股票列表
    sl = report['stock_list']
    print(f"\n[股票列表]")
    print(f"  市场总数: {sl.get('market_total', '?')}")
    print(f"  数据库:   {sl.get('db_total', 0)}")
    print(f"  新增待入: {sl.get('new_count', 0)}")
    print(f"  退市标记: {sl.get('delisted_count', 0)}")
    if sl.get('new_sample'):
        print(f"  新增样例: {sl['new_sample'][:5]}")

    # 日K
    kd = report['kline_daily']
    print(f"\n[日K线]")
    print(f"  完全缺失: {len(kd['missing_stocks'])} 只")
    print(f"  数据过期: {len(kd['outdated_stocks'])} 只")
    if kd['missing_stocks']:
        print(f"  缺失样例: {kd['missing_stocks'][:5]}")
    if kd['outdated_stocks']:
        print(f"  过期样例: {kd['outdated_stocks'][:3]}")

    # 分时
    km = report['kline_minute']
    print(f"\n[分时K线]")
    print(f"  完全缺失: {len(km['missing_stocks'])} 只")
    print(f"  数据过期: {len(km['outdated_stocks'])} 只")

    # 指数
    idx = report['index_daily']
    print(f"\n[指数]")
    print(f"  完全缺失: {idx['missing']}")
    print(f"  数据过期: {len(idx['outdated'])} 个")

    # 总结建议
    print(f"\n[建议]")
    total_missing = (
        sl.get('new_count', 0) +
        len(kd['missing_stocks']) +
        len(km['missing_stocks'])
    )
    total_outdated = (
        len(kd['outdated_stocks']) +
        len(km['outdated_stocks']) +
        len(idx['outdated'])
    )
    if total_missing == 0 and total_outdated == 0:
        print("  [OK] 数据完整,无需更新")
    else:
        print(f"  待处理: {total_missing} 只新增, {total_outdated} 条需增量")
        print(f"  执行: python main.py update daily")


def cmd_update_daily(args):
    """一键智能更新(检查缺失 + 增量补齐)"""
    from updater.parallel_updater import ParallelKlineUpdater
    updater = ParallelKlineUpdater(max_workers=args.workers)
    result = updater.update_daily_smart(
        adjust=args.adjust,
        minute_period=args.minute_period,
        minute_days=args.minute_days,
        daily_days_back=args.days if args.full_init else None,
        kline_workers=args.workers,
        minute_workers=args.minute_workers,
        full_init=args.full_init,
    )
    return result


def cmd_query(args):
    """查询某只股票数据"""
    import pandas as pd
    sql = """
    SELECT trade_date, open, high, low, close, volume, amount, pct_change
    FROM kline_daily
    WHERE code = ? AND adjust_type = ?
    ORDER BY trade_date DESC
    LIMIT ?
    """
    rows = query_all(sql, (args.code, args.adjust, args.limit))
    if not rows:
        print(f"未找到 {args.code} 的数据,可能未下载")
        return
    df = pd.DataFrame(rows, columns=[
        'date', 'open', 'high', 'low', 'close',
        'volume', 'amount', 'pct_chg'
    ])
    print(df.to_string(index=False))


def cmd_backtest(args):
    """单股回测"""
    from backtest.runner import run_backtest
    from backtest.strategies import (
        SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy
    )
    strat_map = {
        'sma': SmaCrossStrategy,
        'momentum': MomentumStrategy,
        'buy_hold': BuyHoldStrategy,
    }
    params = {}
    if args.strategy == 'sma':
        params = {'fast': args.fast, 'slow': args.slow}
    elif args.strategy == 'momentum':
        params = {
            'lookback': args.lookback,
            'momentum_thresh': args.thresh,
            'stop_loss': args.stop_loss,
            'take_profit': args.take_profit,
        }

    run_backtest(
        code=args.code, start=args.start, end=args.end,
        adjust_type=args.adjust, initial_cash=args.cash,
        strategy_class=strat_map[args.strategy],
        strategy_params=params, plot=not args.no_plot,
    )


def cmd_backtest_portfolio(args):
    """组合回测"""
    from backtest.runner import run_portfolio
    from backtest.strategies import SmaCrossStrategy, MomentumStrategy
    strat_map = {'sma': SmaCrossStrategy, 'momentum': MomentumStrategy}
    params = {'fast': args.fast, 'slow': args.slow} \
        if args.strategy == 'sma' else {'lookback': args.lookback}

    codes = [c.strip() for c in args.codes.split(",")]
    run_portfolio(
        codes=codes, start=args.start, end=args.end,
        adjust_type=args.adjust, initial_cash=args.cash,
        strategy_class=strat_map[args.strategy],
        strategy_params=params, plot=False,
    )


def cmd_reset_checkpoint(args):
    """重置断点"""
    from updater.checkpoint import CheckpointManager
    cp = CheckpointManager(args.task)
    if args.yes or input(f"确认重置 {args.task}? (y/N): ").lower() == 'y':
        cp.reset()
        print(f"[OK] {args.task} 断点已重置")
    else:
        print("已取消")


def cmd_scheduler(args):
    """启动定时调度"""
    from updater.parallel_updater import ParallelKlineUpdater
    import schedule

    print("="*60)
    print("定时调度服务已启动,Ctrl+C 退出")
    print("="*60)

    def job_daily():
        logger.info("开始日终更新任务")
        u = ParallelKlineUpdater()
        try:
            u.update_stock_list()
            u.update_index()
            u.update_all(adjust='qfq', days_back=5)
            u.update_all(adjust='hfq', days_back=5)
        except Exception as e:
            logger.error(f"日终任务失败: {e}")

    schedule.every().day.at("16:30").do(job_daily)
    print("已注册任务: 每日 16:30 全量更新")

    while True:
        schedule.run_pending()
        time.sleep(30)


# ---------- CLI 解析 ----------
def main():
    parser = argparse.ArgumentParser(
        description="A股数据采集 + 回测系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--log", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # init
    p = sub.add_parser("init", help="初始化数据库")
    p.set_defaults(func=cmd_init)

    # update
    p = sub.add_parser("update", help="更新数据")
    sub_u = p.add_subparsers(dest="subcmd")

    p1 = sub_u.add_parser("list", help="更新股票列表")
    p1.set_defaults(func=cmd_update_stock_list)

    p2 = sub_u.add_parser("kline", help="更新日K线")
    p2.add_argument("--adjust", default="qfq",
                    choices=["qfq", "hfq", ""])
    p2.add_argument("--days", type=int, default=365,
                    help="回溯天数")
    p2.add_argument("--workers", type=int, default=8)
    p2.add_argument("--include-delisted", action="store_true")
    p2.set_defaults(func=cmd_update_kline)

    p3 = sub_u.add_parser("index", help="更新主要指数")
    p3.set_defaults(func=cmd_update_index)

    p3b = sub_u.add_parser("minute", help="更新分钟K线(全量)")
    p3b.add_argument("--period", type=int, default=5,
                     choices=[1, 5, 15, 30, 60],
                     help="分钟周期(1/5/15/30/60)")
    p3b.add_argument("--days", type=int, default=30,
                     help="回溯天数(AKShare限约1-2月)")
    p3b.add_argument("--workers", type=int, default=8)
    p3b.add_argument("--limit", type=int, default=None,
                     help="仅处理前N只(测试用)")
    p3b.add_argument("--include-delisted", action="store_true")
    p3b.set_defaults(func=cmd_update_minute)

    p3b2 = sub_u.add_parser("minute-smart", help="智能更新分钟K线(仅缺失)")
    p3b2.add_argument("--period", type=int, default=5,
                      choices=[1, 5, 15, 30, 60])
    p3b2.add_argument("--days", type=int, default=30)
    p3b2.add_argument("--workers", type=int, default=4)
    p3b2.add_argument("--limit", type=int, default=None)
    p3b2.set_defaults(func=cmd_update_minute_smart)

    p3p = sub_u.add_parser("periodic", help="聚合周K/月K(本地聚合,不拉取网络)")
    p3p.add_argument("--period", default="both",
                     choices=["weekly", "monthly", "both"],
                     help="weekly=周K, monthly=月K, both=两者(默认)")
    p3p.add_argument("--adjust", default="qfq",
                     choices=["qfq", "hfq", ""],
                     help="复权方式(对应 kline_daily 中的 adjust_type)")
    p3p.add_argument("--codes", default=None,
                     help="限定股票代码,逗号分隔,如 000001,600519;默认全部")
    p3p.set_defaults(func=cmd_update_periodic)


    p3e = sub_u.add_parser("enrich", help="丰富股票信息(行业+上市日期)")
    p3e.add_argument("--workers", type=int, default=4,
                     help="并行获取上市日期的线程数(0=仅行业+K线近似)")
    p3e.add_argument("--limit", type=int, default=None,
                     help="仅处理前N只(测试用)")
    p3e.set_defaults(func=cmd_update_enrich)

    p3c = sub_u.add_parser("daily", help="一键智能更新(检查+增量)")
    p3c.add_argument("--adjust", default="qfq", choices=["qfq", "hfq", ""])
    p3c.add_argument("--workers", type=int, default=8)
    p3c.add_argument("--minute-workers", type=int, default=4)
    p3c.add_argument("--minute-period", type=int, default=5,
                     choices=[1, 5, 15, 30, 60])
    p3c.add_argument("--minute-days", type=int, default=5)
    p3c.add_argument("--days", type=int, default=1825,
                     help="全量回溯天数(--full-init 时生效)")
    p3c.add_argument("--full-init", action="store_true",
                     help="全量初始化(覆盖现有数据)")
    p3c.set_defaults(func=cmd_update_daily)

    p4 = sub_u.add_parser("all", help="全量更新(列表+信息+指数+K线)")
    p4.add_argument("--adjust", default="qfq")
    p4.add_argument("--days", type=int, default=365)
    p4.add_argument("--workers", type=int, default=8)
    p4.add_argument("--enrich-workers", type=int, default=4,
                     help="获取上市日期线程数(0=仅行业+K线)")
    p4.add_argument("--enrich-limit", type=int, default=None,
                     help="限制获取上市日期的股票数(测试用)")
    p4.add_argument("--include-delisted", action="store_true")
    p4.set_defaults(func=cmd_update_all)

    # status
    p = sub.add_parser("status", help="查看数据状态")
    p.set_defaults(func=cmd_status)

    # check
    p = sub.add_parser("check", help="检查数据缺失")
    p.set_defaults(func=cmd_check)

    # query
    p = sub.add_parser("query", help="查询股票数据")
    p.add_argument("--code", required=True)
    p.add_argument("--adjust", default="qfq")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_query)

    # backtest
    p = sub.add_parser("backtest", help="单股回测")
    p.add_argument("--code", default="000001")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--adjust", default="qfq")
    p.add_argument("--cash", type=float, default=100000)
    p.add_argument("--strategy", default="sma",
                   choices=["sma", "momentum", "buy_hold"])
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--thresh", type=float, default=0.05)
    p.add_argument("--stop-loss", type=float, default=0.08)
    p.add_argument("--take-profit", type=float, default=0.20)
    p.add_argument("--no-plot", action="store_true")
    p.set_defaults(func=cmd_backtest)

    # portfolio
    p = sub.add_parser("portfolio", help="组合回测")
    p.add_argument("--codes", required=True,
                   help="股票代码,逗号分隔,如 000001,600000")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--adjust", default="qfq")
    p.add_argument("--cash", type=float, default=100000)
    p.add_argument("--strategy", default="sma",
                   choices=["sma", "momentum"])
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--lookback", type=int, default=20)
    p.set_defaults(func=cmd_backtest_portfolio)

    # checkpoint
    p = sub.add_parser("reset", help="重置断点")
    p.add_argument("--task", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_reset_checkpoint)

    # scheduler
    p = sub.add_parser("scheduler", help="启动定时调度")
    p.set_defaults(func=cmd_scheduler)

    # 解析
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    # 重新设置日志级别
    setup_logging(args.log)
    args.func(args)


if __name__ == "__main__":
    main()
