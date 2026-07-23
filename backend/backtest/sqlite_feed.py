"""
Backtrader 自定义数据源 - 从 SQLite 读取 K线
"""
import sqlite3
from datetime import datetime
from typing import Optional

from backtrader.feed import DataBase
from backtrader import date2num
from backtrader.utils.py3 import with_metaclass

import backtrader.metabase as metabase


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
        self._conn: Optional[sqlite3.Connection] = None
        self._rows: list = []
        self._idx: int = 0

    def start(self):
        super().start()
        self._conn = sqlite3.connect(self.p.db_path)
        self._conn.row_factory = sqlite3.Row

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
        if self._conn:
            self._conn.close()
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
