"""
Backtrader 自定义数据源 - 通过 db.database 统一连接层读取 K线
(SQLite / PostgreSQL 双驱动,驱动由 STOCK_DB_DRIVER 决定)
"""
from datetime import datetime
from typing import Optional

from backtrader.feed import DataBase
from backtrader import date2num
from backtrader.utils.py3 import with_metaclass

import backtrader.metabase as metabase

from db.database import get_conn, CompatConnection


class SQLiteData(DataBase):
    """
    用法:
        data = SQLiteFeed(
            db_path='data/stock.db',
            code='000001',
            start_date='2020-01-01',
            end_date='2024-12-31',
            adjust_type='qfq'
        )
        cerebro.adddata(data)
    """
    lines = (
        'open', 'high', 'low', 'close', 'volume',
        'amount', 'turnover_rate', 'openinterest'
    )

    params = (
        ('db_path', 'data/stock.db'),
        ('code', '000001'),
        ('start_date', None),
        ('end_date', None),
        ('adjust_type', 'qfq'),
    )

    def __init__(self):
        super().__init__()
        self._conn: Optional[CompatConnection] = None
        self._conn_cm = None  # get_conn() 上下文管理器,stop() 时统一 __exit__ 关闭
        self._rows: list = []
        self._idx: int = 0

    def start(self):
        super().start()
        # 经 db.database.get_conn() 获取统一连接:
        # - sqlite 模式固定读取配置的 DB_PATH(stock.db),db_path 参数仅向后兼容保留;
        #   若调用方显式传入的 db_path 与配置路径不同,以配置路径为准。
        # - postgres 模式忽略 db_path,连接同一 PostgreSQL 库。
        self._conn_cm = get_conn()
        self._conn = self._conn_cm.__enter__()

        sql = """
        SELECT trade_date, open, high, low, close, volume,
               amount, turnover_rate
        FROM kline_daily
        WHERE code = ? AND adjust_type = ?
        """
        params = [self.p.code, self.p.adjust_type]
        if self.p.start_date:
            sql += " AND trade_date >= ?"
            params.append(self.p.start_date)
        if self.p.end_date:
            sql += " AND trade_date <= ?"
            params.append(self.p.end_date)
        sql += " ORDER BY trade_date ASC"

        cur = self._conn.execute(sql, params)
        self._rows = cur.fetchall()
        self._idx = 0
        print(f"[Feed] 加载 {self.p.code} {len(self._rows)} 条记录")

    def stop(self):
        if self._conn_cm is not None:
            self._conn_cm.__exit__(None, None, None)
            self._conn = None
            self._conn_cm = None
        super().stop()

    def _load(self):
        """Backtrader 框架逐行调用"""
        if self._idx >= len(self._rows):
            return False

        row = self._rows[self._idx]
        self._idx += 1

        # 时间
        try:
            dt = datetime.strptime(row['trade_date'], '%Y-%m-%d')
        except (ValueError, TypeError):
            return False
        self.lines.datetime[0] = date2num(dt)

        # 价格与成交量
        self.lines.open[0] = float(row['open'] or 0.0)
        self.lines.high[0] = float(row['high'] or 0.0)
        self.lines.low[0] = float(row['low'] or 0.0)
        self.lines.close[0] = float(row['close'] or 0.0)
        self.lines.volume[0] = float(row['volume'] or 0)
        self.lines.amount[0] = float(row['amount'] or 0.0)
        self.lines.turnover_rate[0] = float(row['turnover_rate'] or 0.0)
        self.lines.openinterest[0] = 0.0
        return True

    def _getlength(self):
        return len(self._rows)
