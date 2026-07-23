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
