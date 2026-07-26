"""
股票信息增强 updater —— 写入 stock_list 扩展列(总股本/流通股本/详细行业/最近增强时间)。
两阶段: 1) 行业映射(批量,~500 调用)  2) 单股 profile(并行,慢)
不更新 stock_list 的核心字段(name/full_code/market/is_active),由 stock_list 任务负责。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from db.database import get_conn, query_all
from fetcher.manager import fetcher_manager
from .base import BaseUpdater
from .types import TaskType


class StockEnrichParams(BaseModel):
    limit: Optional[int] = Field(
        None, ge=1, description="仅处理前 N 只(测试用)"
    )
    workers: int = Field(
        4, ge=0, le=16,
        description="Phase 2 并发数;0=跳过 profile API,用 K线 最早日期兜底",
    )


class StockEnrichUpdater(BaseUpdater):
    task_type = TaskType.STOCK_ENRICH
    ParamModel = StockEnrichParams
    display_name = "股票信息增强"

    def run(self, progress_callback=None) -> dict:
        fetcher = fetcher_manager.get_fetcher()
        if fetcher is None:
            raise RuntimeError("无可用数据源")

        result = {
            "industry_updated": 0,
            "profile_updated": 0,
            "profile_failed": 0,
            "list_date_from_kline": 0,
        }
        now = datetime.now().isoformat()

        # ====== Phase 1: 行业批量映射 ======
        self.logger.info(f"{self._log_prefix} Phase 1: 行业映射")
        industry_map = fetcher.get_industry_map()
        if industry_map:
            with get_conn() as conn:
                updates = [(ind, code) for code, ind in industry_map.items()]
                conn.executemany(
                    "UPDATE stock_list SET industry = ? WHERE code = ?",
                    updates,
                )
                # 行业详情列也同步写入(若 fetcher 返回了 detail)
                for code, ind in industry_map.items():
                    if "::" in str(ind):  # "板块::细分" 格式
                        conn.execute(
                            "UPDATE stock_list SET industry_detail = ? WHERE code = ?",
                            (ind.split("::", 1)[1], code),
                        )
            result["industry_updated"] = len(industry_map)
            self.logger.info(f"{self._log_prefix} 已更新行业 {result['industry_updated']} 只")

        self._progress(progress_callback, phase="industry",
                       updated=result["industry_updated"])

        # ====== Phase 2: 上市日期 + 总/流通股本 ======
        if self.params.workers <= 0:
            self.logger.info(f"{self._log_prefix} Phase 2: 跳过 profile API, 用 K线 兜底")
            result["list_date_from_kline"] = self._fill_list_date_from_kline()
            self._mark_enriched_now()
            return result

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT code FROM stock_list "
                "WHERE (list_date IS NULL OR list_date = '' "
                "       OR last_enriched_at IS NULL "
                "       OR last_enriched_at < datetime('now', '-30 days')) "
                "  AND is_active = 1"
            ).fetchall()
        todo = [r[0] for r in rows]
        if self.params.limit:
            todo = todo[:self.params.limit]

        self.logger.info(f"{self._log_prefix} Phase 2: 处理 {len(todo)} 只 (workers={self.params.workers})")
        if not todo:
            self._mark_enriched_now()
            return result

        done = 0
        with ThreadPoolExecutor(
            max_workers=self.params.workers, thread_name_prefix="Enrich"
        ) as pool:
            futures = {pool.submit(fetcher.get_stock_profile, code): code for code in todo}
            for fut in as_completed(futures):
                if self.is_interrupted():
                    break
                code = futures[fut]
                done += 1
                try:
                    profile = fut.result()
                    if profile:
                        self._apply_profile(code, profile, now)
                        result["profile_updated"] += 1
                    else:
                        result["profile_failed"] += 1
                except Exception as e:
                    self.logger.warning(f"{self._log_prefix} {code} profile 失败: {e}")
                    result["profile_failed"] += 1

                if done % 200 == 0 or done == len(todo):
                    self._progress(
                        progress_callback, phase="profile",
                        done=done, total=len(todo),
                        ok=result["profile_updated"], fail=result["profile_failed"],
                    )

        # 兜底:API 没拿到 list_date 的,用 K线 最早日期补
        result["list_date_from_kline"] = self._fill_list_date_from_kline()
        self._mark_enriched_now()
        return result

    # ---------- helpers ----------
    def _apply_profile(self, code: str, profile: dict, now: str):
        sets, params = [], []
        mapping = {
            "list_date":       "list_date",
            "total_share":     "total_share",
            "float_share":     "float_share",
        }
        for src, dst in mapping.items():
            v = profile.get(src)
            if v is not None:
                sets.append(f"{dst} = ?")
                params.append(v)
        # 行业详情
        ind_detail = profile.get("industry_detail")
        if ind_detail and not profile.get("industry"):
            sets.append("industry_detail = ?")
            params.append(ind_detail)
        # 最后增强时间
        sets.append("last_enriched_at = ?")
        params.append(now)

        if not sets:
            return
        params.append(code)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE stock_list SET {', '.join(sets)} WHERE code = ?",
                params,
            )

    def _fill_list_date_from_kline(self) -> int:
        with get_conn() as conn:
            conn.execute("""
                UPDATE stock_list
                SET list_date = (
                    SELECT MIN(k.trade_date)
                    FROM kline_daily k
                    WHERE k.code = stock_list.code
                )
                WHERE (list_date IS NULL OR list_date = '')
                  AND code IN (SELECT DISTINCT code FROM kline_daily)
            """)
            return conn.total_changes

    def _mark_enriched_now(self):
        with get_conn() as conn:
            conn.execute(
                "UPDATE stock_list SET last_enriched_at = ? "
                "WHERE last_enriched_at IS NULL",
                (datetime.now().isoformat(),),
            )