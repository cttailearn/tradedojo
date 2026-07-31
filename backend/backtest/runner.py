"""
Backtrader 回测引擎
- 支持单股和多股组合
- A股手续费模型(佣金+印花税+滑点)
- 完整分析器
"""
import logging
from pathlib import Path
from typing import Type, Optional

import backtrader as bt
import pandas as pd

from config import BacktestConfig, PROJECT_ROOT
from backtest.sqlite_feed import SQLiteData
from backtest.strategies import (
    SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy
)

# 无头模式(适用于无 GUI 的服务器)
import matplotlib
matplotlib.use('Agg')

logger = logging.getLogger(__name__)


class AShareCommInfo(bt.CommInfoBase):
    """A 股手续费模型:
    - 佣金: 万三(双边,最低 5 元)
    - 印花税: 千一(仅卖出)
    """

    params = (
        ('commission', BacktestConfig.COMMISSION),
        ('stamp_tax', BacktestConfig.STAMP_TAX),
        ('min_commission', 5.0),  # 最低佣金 5 元
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
        ('percabs', True),
    )

    def _getcommission(self, size, price, pseudoexec):
        turnover = abs(size) * price
        # 佣金(双边,含最低 5 元)
        comm = turnover * self.p.commission
        if comm < self.p.min_commission:
            comm = self.p.min_commission
        # 印花税(仅卖出,size < 0)
        if size < 0:
            comm += turnover * self.p.stamp_tax
        return comm


def run_backtest(
    code: str = "000001",
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    adjust_type: str = "qfq",
    initial_cash: float = None,
    strategy_class: Type[bt.Strategy] = SmaCrossStrategy,
    strategy_params: Optional[dict] = None,
    plot: bool = True,
    plot_path: Optional[str] = None,
) -> dict:
    """
    运行单股回测
    :return: 回测结果字典
    """
    initial_cash = initial_cash or BacktestConfig.INITIAL_CASH
    strategy_params = strategy_params or {}

    cerebro = bt.Cerebro(stdstats=True)

    # 1. 添加策略
    cerebro.addstrategy(strategy_class, **strategy_params)

    # 2. 数据源
    db_path = str(PROJECT_ROOT / "data" / "stock.db")
    data = SQLiteData(
        db_path=db_path, code=code,
        start_date=start, end_date=end,
        adjust_type=adjust_type,
    )
    cerebro.adddata(data)

    # 3. Broker
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.addcommissioninfo(AShareCommInfo())
    cerebro.broker.set_slippage_perc(BacktestConfig.SLIPPAGE)

    # 4. 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.025, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return',
                        timeframe=bt.TimeFrame.Years)

    # 5. 执行
    logger.info(f"回测 {code} | {start} ~ {end} | {adjust_type}")
    logger.info(f"策略: {strategy_class.__name__} | 初始资金: {initial_cash:,.2f}")

    results = cerebro.run()
    strat = results[0]

    # 6. 结果报告
    final_value = cerebro.broker.getvalue()
    pnl = final_value - initial_cash
    pnl_pct = pnl / initial_cash * 100

    returns = strat.analyzers.returns.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    sqn = strat.analyzers.sqn.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    print(f"\n{'='*60}\n【回测结果】 {code}")
    print(f"  期末资金:    {final_value:>15,.2f}")
    print(f"  总盈亏:      {pnl:>+15,.2f} ({pnl_pct:+.2f}%)")
    print(f"  年化收益:    {returns.get('rnorm100', 0):>14.2f}%")
    print(f"  最大回撤:    {dd.max.drawdown:>14.2f}%")
    print(f"  夏普比率:    {sharpe.get('sharperatio', 0) or 0:>14.3f}")
    print(f"  SQN 评分:    {sqn.get('sqn', 0):>14.2f}")

    if 'total' in trades:
        total = trades['total']
        won = trades.get('won', {}).get('total', 0)
        lost = trades.get('lost', {}).get('total', 0)
        total_trades = total.get('total', 0)
        win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
        print(f"  交易次数:    {total_trades:>14d}")
        print(f"  胜率:        {win_rate:>14.1f}% ({won}胜/{lost}负)")
        if 'pnl' in trades and trades['pnl'].get('won') and trades['pnl'].get('lost'):
            avg_win = trades['pnl']['won'].get('average', 0)
            avg_loss = abs(trades['pnl']['lost'].get('average', 0))
            profit_ratio = avg_win / avg_loss if avg_loss > 0 else 0
            print(f"  盈亏比:      {profit_ratio:>14.2f}")

    # 7. 绘图
    if plot:
        try:
            figs = cerebro.plot(
                style='candlestick',
                barup='red', bardown='green',  # A股:红涨绿跌
                volume=True,
                figsize=(14, 8),
            )
            for f in figs:
                if hasattr(f, 'savefig'):
                    fname = plot_path or f"backtest_{code}.png"
                    f.savefig(fname, dpi=120, bbox_inches='tight')
                    print(f"  图表已保存: {fname}")
                    break
        except Exception as e:
            logger.warning(f"绘图失败(可忽略): {e}")

    return {
        'code': code,
        'final_value': final_value,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'annual_return': returns.get('rnorm100', 0),
        'max_drawdown': dd.max.drawdown,
        'sharpe': sharpe.get('sharperatio', 0) or 0,
        'sqn': sqn.get('sqn', 0),
    }


def run_portfolio(
    codes: list,
    strategy_class: Type[bt.Strategy] = SmaCrossStrategy,
    strategy_params: Optional[dict] = None,
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    adjust_type: str = "qfq",
    initial_cash: float = None,
    plot: bool = False,
) -> pd.DataFrame:
    """
    多股"独立回测" (2026-07-31 改名为 run_independent_loop) - 兼容保留.

    ⚠️ 注意: 这是"每只股独立回测"取均值, 不是真组合回测!
    - 每只股都从 100% 资金开始 (默认 initial_cash=1000000)
    - 适用于: 评估"策略在多只股上的平均表现" / 横向对比
    - 不适用于: 真实"一篮子资金调仓"场景 (如同时持有 5 只股 + 再平衡)

    如需真组合回测(资金均分 N 份 → 加总净值), 请用 run_basket()。
    """
    return _run_independent_loop_impl(
        codes=codes,
        strategy_class=strategy_class,
        strategy_params=strategy_params,
        start=start, end=end,
        adjust_type=adjust_type,
        initial_cash=initial_cash,
        plot=plot,
    )


def run_independent_loop(
    codes: list,
    strategy_class: Type[bt.Strategy] = SmaCrossStrategy,
    strategy_params: Optional[dict] = None,
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    adjust_type: str = "qfq",
    initial_cash: float = None,
    plot: bool = False,
) -> pd.DataFrame:
    """独立回测每只股(2026-07-31 起的"真名"), 保留 run_portfolio 别名."""
    return _run_independent_loop_impl(
        codes=codes,
        strategy_class=strategy_class,
        strategy_params=strategy_params,
        start=start, end=end,
        adjust_type=adjust_type,
        initial_cash=initial_cash,
        plot=plot,
    )


def _run_independent_loop_impl(
    codes, strategy_class, strategy_params, start, end, adjust_type, initial_cash, plot,
) -> pd.DataFrame:
    results = []
    for code in codes:
        try:
            r = run_backtest(
                code=code, start=start, end=end, adjust_type=adjust_type,
                initial_cash=initial_cash,
                strategy_class=strategy_class,
                strategy_params=strategy_params,
                plot=plot,
            )
            results.append(r)
        except Exception as e:
            logger.warning(f"{code} 回测失败: {e}")

    df = pd.DataFrame(results)
    if df.empty:
        return df

    print(f"\n{'='*60}\n【独立回测汇总】 {len(df)} 只股票")
    print(df[['code', 'pnl_pct', 'annual_return',
              'max_drawdown', 'sharpe']].to_string(index=False))
    print(f"\n  平均收益:  {df['pnl_pct'].mean():.2f}%")
    print(f"  中位收益:  {df['pnl_pct'].median():.2f}%")
    print(f"  胜出比例:  {(df['pnl_pct'] > 0).sum() / len(df) * 100:.1f}%")

    return df


def run_basket(
    codes: list,
    strategy_class: Type[bt.Strategy] = SmaCrossStrategy,
    strategy_params: Optional[dict] = None,
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    adjust_type: str = "qfq",
    initial_cash: float = None,
    plot: bool = False,
) -> dict:
    """
    真组合回测(2026-07-31 P1-11 新增) - 一篮子资金等权分仓 + 加总净值.

    与 run_independent_loop 的区别:
      - run_independent_loop: 每只股 100% 资金, 取平均
      - run_basket: 资金均分 N 份进 N 只股, 加总求组合净值与收益

    返回 dict 包含:
      - items: 每只股明细 (含 pnl_pct, final_value 等)
      - summary: 组合汇总 (总资金 / 总盈亏 / 加权夏普 / 胜出比例)
    """
    initial_cash = initial_cash or BacktestConfig.INITIAL_CASH
    strategy_params = strategy_params or {}
    n = len(codes)
    if n == 0:
        return {"items": [], "summary": {}, "initial_cash": initial_cash}
    per_cash = initial_cash / n

    results = []
    for code in codes:
        try:
            r = run_backtest(
                code=code, start=start, end=end, adjust_type=adjust_type,
                initial_cash=per_cash,
                strategy_class=strategy_class,
                strategy_params=strategy_params,
                plot=plot,
            )
            r["allocated_cash"] = per_cash
            results.append(r)
        except Exception as e:
            logger.warning(f"{code} 回测失败: {e}")

    if not results:
        return {"items": [], "summary": {}, "initial_cash": initial_cash}

    total_final = sum(r["final_value"] for r in results)
    total_pnl = total_final - initial_cash
    total_pnl_pct = total_pnl / initial_cash * 100
    win_count = sum(1 for r in results if r.get("pnl", 0) > 0)
    # 加权夏普: 按 allocated_cash 加权
    sharpe_sum = sum(
        (r.get("sharpe") or 0) * r.get("allocated_cash", per_cash) for r in results
    )
    weighted_sharpe = sharpe_sum / initial_cash if initial_cash else 0
    # 平均最大回撤(算术平均, 简化)
    avg_max_dd = sum(r.get("max_drawdown") or 0 for r in results) / len(results)

    print(f"\n{'='*60}\n【真组合回测汇总】 {len(results)} 只股票 / 总资金 ¥{initial_cash:,.0f}")
    for r in results:
        print(f"  {r['code']:8s} 期末 ¥{r['final_value']:>12,.0f}  收益 {r['pnl_pct']:>6.2f}%")
    print(f"\n  组合总盈亏:  ¥{total_pnl:>+12,.0f} ({total_pnl_pct:+.2f}%)")
    print(f"  组合期末:    ¥{total_final:>12,.0f}")
    print(f"  胜出比例:    {win_count}/{len(results)} ({win_count/len(results)*100:.1f}%)")
    print(f"  加权夏普:    {weighted_sharpe:.3f}")
    print(f"  平均最大回撤: {avg_max_dd:.2f}%")

    return {
        "items": results,
        "summary": {
            "count": len(results),
            "initial_cash": initial_cash,
            "per_cash": per_cash,
            "total_final": round(total_final, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "win_rate": round(win_count / len(results) * 100, 1),
            "weighted_sharpe": round(weighted_sharpe, 3),
            "avg_max_drawdown": round(avg_max_dd, 2),
        },
        "initial_cash": initial_cash,
    }
