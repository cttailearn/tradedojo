"""
周K/月K 聚合 updater —— 从 kline_daily 本地聚合生成周期 K 线,写入 kline_minute。

周期约定(kline_minute.period 字段复用并扩展原有 1/5/15/30/60):
  weekly  = 10080(周K)
  monthly = 43200(月K)

依赖 kline_daily 已存在(按 adjust 复权),本任务只做纯本地聚合,不拉取任何网络数据。
"""
import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from db.database import query_all, get_conn
from .base import BaseUpdater
from .types import TaskType

# 周期名称 -> (kline_minute.period 值, 中文名)
_PERIODS = {
    "weekly": (10080, "周K"),
    "monthly": (43200, "月K"),
}


class KlinePeriodicParams(BaseModel):
    period: str = Field(
        "both", description="weekly=周K, monthly=月K, both=两者"
    )
    adjust: str = Field(
        "qfq", description="复权方式(qfq/hfq)"
    )
    codes: Optional[list[str]] = Field(
        None, description="限定到指定代码,None=全部"
    )


class KlinePeriodicUpdater(BaseUpdater):
    task_type = TaskType.KLINE_PERIODIC
    ParamModel = KlinePeriodicParams
    display_name = "周/月K"

    def _emit(self, callback, **kw):
        self._progress(callback, **kw)

    @staticmethod
    def _bucket_key(trade_date: str, period_name: str) -> str:
        """返回聚合桶 key。周K 用 ISO 年-ISO 周,月K 用 YYYY-MM。"""
        dt = datetime.strptime(trade_date[:10], "%Y-%m-%d")
        if period_name == "monthly":
            return dt.strftime("%Y-%m")
        iso = dt.isocalendar()
        return f"{iso[0]}-{iso[1]}"  # 如 2026-31(ISO 年-周)

    def _aggregate(self, rows, period_name) -> list[dict]:
        """把 (code, trade_date, open, high, low, close, volume, amount)
        逐行归入聚合桶:open=首日, high=max, low=min, close=末日,
        volume/amount 求和;trade_time=桶内最后交易日 15:00:00。"""
        buckets: dict[str, dict] = {}
        order: list[str] = []
        for r in rows:
            _code, trade_date, open_, high, low, close, volume, amount = r

            def _num(v):
                return 0.0 if v is None else v

            key = self._bucket_key(trade_date, period_name)
            if key not in buckets:
                buckets[key] = {
                    "last_date": trade_date,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": _num(volume),
                    "amount": _num(amount),
                }
                order.append(key)
            else:
                b = buckets[key]
                b["last_date"] = trade_date
                b["high"] = max(_num(b["high"]), _num(high))
                b["low"] = min(_num(b["low"]), _num(low))
                b["close"] = close          # 末日收盘
                b["volume"] += _num(volume)
                b["amount"] += _num(amount)

        out = []
        for key in order:
            b = buckets[key]
            out.append({
                "trade_time": f"{b['last_date']} 15:00:00",
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
                "amount": b["amount"],
            })
        return out

    def run(self, progress_callback=None) -> dict:
        p = self.params
        if p.period not in _PERIODS and p.period != "both":
            raise ValueError(f"不支持的周期: {p.period!r},可选 {list(_PERIODS)} / both")
        periods = _PERIODS if p.period == "both" else {p.period: _PERIODS[p.period]}

        where = ["adjust_type = ?"]
        params: list = [p.adjust]
        if p.codes:
            placeholders = ",".join("?" * len(p.codes))
            where.append(f"code IN ({placeholders})")
            params.extend(p.codes)

        # 从 kline_daily 读原始日线(按 code+日期排序)
        sql = (
            "SELECT code, trade_date, open, high, low, close, volume, amount "
            f"FROM kline_daily WHERE {' AND '.join(where)} "
            "ORDER BY code ASC, trade_date ASC"
        )
        self._emit(progress_callback, stage="read", status="running", source="kline_daily")
        rows = query_all(sql, tuple(params))
        self._emit(progress_callback, stage="read", status="done", rows=len(rows))

        per_code: dict[str, list] = {}
        for r in rows:
            per_code.setdefault(r[0], []).append(r)
        code_keys = list(per_code.keys())
        self.logger.info(
            f"{self._log_prefix} 读取 {len(rows)} 行日线, 覆盖 {len(code_keys)} 只 "
            f"period={p.period} adjust={p.adjust}"
        )

        insert_sql = """
        -- ON CONFLICT 语法,兼容 SQLite/PostgreSQL
        INSERT INTO kline_minute
            (code, trade_time, period, open, high, low,
             close, volume, amount, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (code, trade_time, period) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            amount=excluded.amount,
            updated_at=excluded.updated_at
        """
        now = datetime.now().isoformat()

        summary: dict = {}
        for idx, code in enumerate(code_keys):
            if self.is_interrupted():
                break
            code_rows = per_code[code]
            for period_name, (period_int, name) in periods.items():
                buckets = self._aggregate(code_rows, period_name)
                # 先清空该 code 该周期全部旧聚合行(聚合桶会变,覆盖不彻底)
                with get_conn() as conn:
                    conn.execute(
                        "DELETE FROM kline_minute WHERE code=? AND period=?",
                        (code, period_int),
                    )
                    if buckets:
                        conn.executemany(insert_sql, [
                            (code, b["trade_time"], period_int,
                             b["open"], b["high"], b["low"],
                             b["close"], b["volume"], b["amount"], now)
                            for b in buckets
                        ])
                summary.setdefault(name, {})[code] = len(buckets)

            self._emit(progress_callback, stage="build", status="running",
                       done=idx + 1, total=len(code_keys), code=code)

        result = {
            "period": p.period,
            "adjust": p.adjust,
            "codes": len(code_keys),
            "buckets": summary,
        }
        self._emit(progress_callback, stage="build", status="done")
        self.logger.info(f"{self._log_prefix} 完成: {result}")
        return result