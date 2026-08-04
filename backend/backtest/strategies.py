"""
Backtrader 策略集合
"""
import backtrader as bt


class SmaCrossStrategy(bt.Strategy):
    """双均线交叉策略"""
    params = (
        ('fast', 5),
        ('slow', 20),
        ('printlog', False),
        ('position_pct', 0.95),  # 仓位比例
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(
            self.data.close, period=self.p.fast
        )
        self.slow_ma = bt.indicators.SMA(
            self.data.close, period=self.p.slow
        )
        self.crossover = bt.indicators.CrossOver(
            self.fast_ma, self.slow_ma
        )
        self.order = None
        self.trade_count = 0

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY 价={order.executed.price:.2f} '
                    f'量={order.executed.size} '
                    f'费={order.executed.comm:.2f}'
                )
                self.trade_count += 1
            else:
                self.log(
                    f'SELL 价={order.executed.price:.2f} '
                    f'量={order.executed.size} '
                    f'PnL={order.executed.pnl:.2f}'
                )
        elif order.status in [order.Canceled, order.Margin,
                              order.Rejected]:
            self.log('订单 取消/保证金不足/拒绝')
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(
                f'平仓: 毛收益={trade.pnl:.2f} '
                f'净收益={trade.pnlcomm:.2f}'
            )

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:  # 金叉
                size = int(
                    self.broker.getcash() * self.p.position_pct
                    / self.data.close[0] / 100
                ) * 100
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            if self.crossover < 0:  # 死叉
                self.order = self.sell(size=self.position.size)


class MomentumStrategy(bt.Strategy):
    """N日动量策略 + 止损止盈"""
    params = (
        ('lookback', 20),
        ('momentum_thresh', 0.05),  # 动量阈值
        ('stop_loss', 0.08),        # 8% 止损
        ('take_profit', 0.20),      # 20% 止盈
        ('printlog', False),
    )

    def __init__(self):
        self.momentum = (
            self.data.close - self.data.close(-self.p.lookback)
        ) / self.data.close(-self.p.lookback)
        self.entry_price = None
        self.order = None

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.log(f'BUY 价={self.entry_price:.2f}')
            else:
                self.entry_price = None
                self.log(f'SELL 价={order.executed.price:.2f}')
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            # 动量为正且超过阈值
            if self.momentum[0] > self.p.momentum_thresh:
                cash = self.broker.getcash() * 0.95
                size = int(cash / self.data.close[0] / 100) * 100
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 止盈止损
            assert self.entry_price is not None
            ret = (self.data.close[0] - self.entry_price) / self.entry_price
            if ret <= -self.p.stop_loss or ret >= self.p.take_profit:
                self.order = self.sell(size=self.position.size)
                self.log(f'止盈止损 ret={ret:.2%}')
            elif self.momentum[0] < -self.p.momentum_thresh:
                self.order = self.sell(size=self.position.size)
                self.log(f'动量反转 ret={ret:.2%}')


class BuyHoldStrategy(bt.Strategy):
    """买入持有基准策略"""
    def __init__(self):
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            self.order = self.buy(size=int(
                self.broker.getcash() * 0.95 / self.data.close[0] / 100
            ) * 100)


class MaAlignmentStrategy(bt.Strategy):
    """均线多头排列策略 (2026-08-04 新增)

    买入(全部满足,参数均可配置):
      1. 快线(fast)上穿中线(mid) —— 金叉
      2. 中线(mid) > 慢线(slow)  —— 多头结构
      3. 成交量 > 量能均线(vol_period) × vol_ratio —— 放量确认

    卖出:
      - 快线(fast)下穿中线(mid) —— 死叉,当日收盘卖出;
      - T+1 规则:若死叉发生在买入当日,次日开盘价卖出(限价=次日开盘价)。
    """
    params = (
        ('fast', 5),
        ('mid', 10),
        ('slow', 20),
        ('vol_period', 20),
        ('vol_ratio', 1.2),   # 放量倍数
        ('position_pct', 0.95),
        ('printlog', False),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.mid_ma = bt.indicators.SMA(self.data.close, period=self.p.mid)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=self.p.vol_period)
        self.cross = bt.indicators.CrossOver(self.fast_ma, self.mid_ma)
        self.order = None
        self.trade_count = 0
        self._buy_day = None      # 当前持仓的买入日(自然日)
        self._sell_pending = False  # T+1: 等待次日开盘卖出
        self._pending_day = None    # 触发 T+1 锁定的死叉日

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY 价={order.executed.price:.2f} '
                    f'量={order.executed.size} '
                    f'费={order.executed.comm:.2f}'
                )
                self.trade_count += 1
                # 买入成交日 = 下单日(backtrader 当日撮合)
                self._buy_day = self.data.datetime.date(0)
            else:
                self.log(
                    f'SELL 价={order.executed.price:.2f} '
                    f'量={order.executed.size} '
                    f'PnL={order.executed.pnl:.2f}'
                )
                self._buy_day = None
                self._sell_pending = False
        elif order.status in [order.Canceled, order.Margin,
                              order.Rejected]:
            self.log('订单 取消/保证金不足/拒绝')
        self.order = None

    def next(self):
        if self.order:
            return

        # 1) T+1 锁定的死叉: 次日开盘卖出
        if self._sell_pending and self._pending_day is not None:
            today = self.data.datetime.date(0)
            if today > self._pending_day:
                # 次日(或之后)的第一根 bar, 以开盘价卖出
                self.order = self.sell(
                    size=self.position.size,
                    exectype=bt.Order.Limit,
                    price=self.data.open[0],
                )
                self.log(f'SELL T+1 次日开盘 {self.data.open[0]:.2f}')
                self._sell_pending = False
                self._pending_day = None
            return

        if not self.position:
            # 金叉 + 多头结构 + 放量 → 买入
            if (
                self.cross[0] > 0
                and self.mid_ma[0] > self.slow_ma[0]
                and self.data.volume[0] > self.vol_ma[0] * self.p.vol_ratio
            ):
                size = int(
                    self.broker.getcash() * self.p.position_pct
                    / self.data.close[0] / 100
                ) * 100
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            if self.cross[0] < 0:  # 死叉
                today = self.data.datetime.date(0)
                if self._buy_day is not None and today <= self._buy_day:
                    # T+1: 当日买入, 次日开盘才能卖
                    self._sell_pending = True
                    self._pending_day = today
                    self.log(f'T+1 锁定, 次日开盘卖出')
                else:
                    self.order = self.sell(size=self.position.size)
                    self.log(f'SELL 死叉 {self.data.close[0]:.2f}')
