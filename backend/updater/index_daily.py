"""
主要指数日线 updater —— 维护固定几只主要指数(sh/sz)的全量历史。
指数列表可由用户在 params.codes 中覆盖。
"""
import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from db.database import get_conn
from fetcher.manager import fetcher_manager
from .base import BaseUpdater
from .indices import KEY_INDEX_CODES
from .types import TaskType


class IndexDailyParams(BaseModel):
    codes: Optional[list[str]] = Field(
        None, description="指数代码列表,为空时使用内置默认"
    )


class IndexDailyUpdater(BaseUpdater):
    task_type = TaskType.INDEX_DAILY
    ParamModel = IndexDailyParams
    display_name = "主要指数"

    def run(self, progress_callback=None) -> dict:
        fetcher = fetcher_manager.get_fetcher()
        if fetcher is None:
            raise RuntimeError("无可用数据源")

        codes = self.params.codes or KEY_INDEX_CODES
        self.logger.info(f"{self._log_prefix} 更新指数 {codes}")

        success = 0
        for i, code in enumerate(codes):
            if self.is_interrupted():
                break
            try:
                df = fetcher.get_index_daily(code)
                if df is None or df.empty:
                    continue
                sql = """
                -- ON CONFLICT 语法,兼容 SQLite/PostgreSQL
                INSERT INTO index_daily
                    (code, name, trade_date, open, high, low, close,
                     volume, amount, pct_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    name=excluded.name,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    pct_change=excluded.pct_change
                """
                with get_conn() as conn:
                    conn.executemany(sql, [
                        (
                            r.code,
                            getattr(r, "name", None),
                            r.trade_date,
                            r.open, r.high, r.low, r.close,
                            r.volume,
                            getattr(r, "amount", None),
                            getattr(r, "pct_change", None),
                        )
                        for r in df.itertuples()
                    ])
                success += 1
            except Exception as e:
                self.logger.warning(f"{self._log_prefix} 指数 {code} 失败: {e}")

            self._progress(progress_callback, done=i + 1, total=len(codes))

        self.logger.info(f"{self._log_prefix} 指数 {success}/{len(codes)}")
        return {"updated": success, "total": len(codes)}