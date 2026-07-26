"""
股票基础信息 updater —— 从主数据源拉取全市场股票列表,UPSERT 到 stock_list。
保留已有 industry / list_date / 扩展列(避免 enrich 数据被覆盖)。
"""
import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from db.database import get_conn
from fetcher.manager import fetcher_manager
from .base import BaseUpdater
from .types import TaskType


class StockListParams(BaseModel):
    full_refresh: bool = Field(
        False, description="是否强制全量重建(默认增量 UPSERT)"
    )


class StockListUpdater(BaseUpdater):
    task_type = TaskType.STOCK_LIST
    ParamModel = StockListParams
    display_name = "股票基础信息"

    def run(self, progress_callback=None) -> dict:
        fetcher = fetcher_manager.get_fetcher()
        if fetcher is None:
            raise RuntimeError("无可用数据源")

        self.logger.info(f"{self._log_prefix} 开始更新股票列表 (full_refresh={self.params.full_refresh})")
        df = fetcher.get_stock_list()
        if df is None or df.empty:
            return {"updated": 0, "skipped": True}

        now = datetime.now().isoformat()
        with get_conn() as conn:
            if self.params.full_refresh:
                # 全量模式:清空再重建
                conn.execute("DELETE FROM stock_list")

            # UPSERT: 保留已有 industry / list_date / 扩展列
            sql = """
            INSERT INTO stock_list
                (code, name, full_code, market, is_active, updated_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(code) DO UPDATE SET
                name       = excluded.name,
                full_code  = excluded.full_code,
                market     = excluded.market,
                is_active  = 1,
                updated_at = excluded.updated_at
            """
            rows = [
                (r.code, r.name, r.full_code, r.market, now)
                for r in df.itertuples()
            ]
            conn.executemany(sql, rows)

        self.logger.info(f"{self._log_prefix} 完成: {len(rows)} 只")
        self._progress(progress_callback, updated=len(rows), total=len(rows))
        return {"updated": len(rows), "skipped": False}