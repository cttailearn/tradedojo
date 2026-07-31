"""
组合型 updater —— 把多个基础 updater 串成一个语义完整的任务。

两个面向用户的入口:
  - FETCH_ALL   : 全量拉取。一次性把股票列表 + 行业 + K线 + 指数全部初始化。
                  适合: 首次部署 / 换数据源 / 长时间没跑。
  - SYNC_LATEST : 增量同步。K线只补缺失/过期的部分,指数只补最近几天。
                  适合: 日常调度 / 手动刷新。

内部直接复用已有 updater,避免重复逻辑。
"""
import logging
from typing import Optional

from pydantic import BaseModel, Field

from .base import BaseUpdater
from .types import TaskType


# ============================================================
# FETCH_ALL —— 全量拉取
# ============================================================
class FetchAllParams(BaseModel):
    """全量拉取的参数。days_back / workers / adjust 与单任务对齐。"""
    days_back: int = Field(
        0, ge=0, le=3650,
        description="K线回溯天数(0=自上市以来全量,>0=按天数回溯)",
    )
    adjust: str = Field("qfq", description="复权方式 qfq/hfq")
    workers: int = Field(4, ge=1, le=16, description="K线并发线程数")
    skip_enrich: bool = Field(
        False,
        description="是否跳过 stock_enrich(行业映射+profile);True 时只跑列表+K线+指数",
    )


class FetchAllUpdater(BaseUpdater):
    """
    一次性完成:
      1. stock_list    —— 拉取股票列表
      2. stock_enrich  —— 行业映射(+ 可选 profile,关闭)
      3. kline_daily   —— 全量回溯 K线
      4. index_daily   —— 主要指数

    步骤之间通过 _progress 反馈,前端能看到当前阶段。
    """
    task_type = TaskType.FETCH_ALL
    ParamModel = FetchAllParams
    display_name = "全量拉取数据"

    def run(self, progress_callback=None) -> dict:
        # 延迟 import 避免循环依赖
        from updater.stock_list import StockListUpdater
        from updater.stock_enrich import StockEnrichUpdater
        from updater.kline_daily import KlineDailyUpdater
        from updater.index_daily import IndexDailyUpdater

        p = self.params
        result = {
            "stages": {},
            "days_back": p.days_back,
            "adjust": p.adjust,
        }

        # ---- Stage 1: 股票列表 ----
        self._emit(progress_callback, stage="stock_list", status="running")
        try:
            r1 = StockListUpdater({"full_refresh": False}).run()
            result["stages"]["stock_list"] = r1
        except Exception as e:
            self.logger.warning(f"{self._log_prefix} stock_list 失败: {e}")
            result["stages"]["stock_list"] = {"error": str(e)}
            # 列表失败 → 后续无标的,直接结束
            self._emit(progress_callback, stage="stock_list", status="failed", error=str(e))
            return result
        self._emit(progress_callback, stage="stock_list", status="done", **result["stages"]["stock_list"])

        # ---- Stage 2: 行业增强(可选) ----
        if not p.skip_enrich:
            self._emit(progress_callback, stage="stock_enrich", status="running")
            try:
                # 2026-07-31 P1-10: 默认 workers=2(适度并发, ~30 分钟可补完 5000 只)
                #   之前 workers=0 完全跳 Phase 2,导致大量股票 list_date 缺失
                #   影响训练选股的 since_list_date 准确性
                r2 = StockEnrichUpdater({"limit": None, "workers": 2}).run()
                result["stages"]["stock_enrich"] = r2
            except Exception as e:
                self.logger.warning(f"{self._log_prefix} stock_enrich 失败: {e}")
                result["stages"]["stock_enrich"] = {"error": str(e)}
            self._emit(progress_callback, stage="stock_enrich", status="done", **result["stages"].get("stock_enrich", {}))
        else:
            result["stages"]["stock_enrich"] = {"skipped": True}

        # ---- Stage 3: K线全量 ----
        if self.is_interrupted():
            return result
        self._emit(progress_callback, stage="kline_daily", status="running")
        try:
            # days_back=0 时按各自 list_date 拉取(自上市以来全量),否则按天数回溯
            is_full = p.days_back == 0
            r3 = KlineDailyUpdater({
                "mode": "full",
                "adjust": p.adjust,
                "days_back": p.days_back,
                "workers": p.workers,
                "since_list_date": is_full,
            }).run()
            result["stages"]["kline_daily"] = r3.get("stats", r3)
        except Exception as e:
            self.logger.warning(f"{self._log_prefix} kline_daily 失败: {e}")
            result["stages"]["kline_daily"] = {"error": str(e)}
        self._emit(progress_callback, stage="kline_daily", status="done", **result["stages"].get("kline_daily", {}))

        # ---- Stage 4: 指数 ----
        if self.is_interrupted():
            return result
        self._emit(progress_callback, stage="index_daily", status="running")
        try:
            r4 = IndexDailyUpdater({}).run()
            result["stages"]["index_daily"] = r4
        except Exception as e:
            self.logger.warning(f"{self._log_prefix} index_daily 失败: {e}")
            result["stages"]["index_daily"] = {"error": str(e)}
        self._emit(progress_callback, stage="index_daily", status="done", **result["stages"].get("index_daily", {}))

        self._emit(progress_callback, stage="all", status="done")
        self.logger.info(f"{self._log_prefix} 全量拉取完成: {result['stages']}")
        return result

    def _emit(self, callback, **kw):
        self._progress(callback, **kw)


# ============================================================
# SYNC_LATEST —— 增量同步到最新
# ============================================================
class SyncLatestParams(BaseModel):
    """增量同步参数。"""
    days_back: int = Field(10, ge=1, le=120, description="K线回溯天数(增量只需覆盖最近几天)")
    adjust: str = Field("qfq", description="复权方式")
    workers: int = Field(4, ge=1, le=16, description="K线并发线程数")
    only_active: bool = Field(True, description="是否只处理在市股票")
    codes: Optional[list[str]] = Field(None, description="限定股票代码,None=自动选缺失/过期")
    update_stock_list: bool = Field(
        True, description="是否顺便同步股票列表(增量更新新上市/退市)"
    )
    since_list_date: bool = Field(
        False,
        description=(
            "True 时单股/批量按各自上市日期补全 K线(超出 days_back 部分按 days_back 上限截断)"
        ),
    )


class SyncLatestUpdater(BaseUpdater):
    """
    增量同步:
      1. stock_list(smart UPSERT,捕获新上市/退市)
      2. kline_daily(smart mode,仅处理缺失/过期)
      3. index_daily(主要指数)
    """
    task_type = TaskType.SYNC_LATEST
    ParamModel = SyncLatestParams
    display_name = "增量同步到最新"

    def run(self, progress_callback=None) -> dict:
        from updater.stock_list import StockListUpdater
        from updater.kline_daily import KlineDailyUpdater
        from updater.index_daily import IndexDailyUpdater

        p = self.params
        result = {
            "stages": {},
            "days_back": p.days_back,
            "adjust": p.adjust,
        }

        # ---- Stage 1: 同步股票列表(可选) ----
        if p.update_stock_list:
            self._emit(progress_callback, stage="stock_list", status="running")
            try:
                r1 = StockListUpdater({"full_refresh": False}).run()
                result["stages"]["stock_list"] = r1
            except Exception as e:
                self.logger.warning(f"{self._log_prefix} stock_list 失败: {e}")
                result["stages"]["stock_list"] = {"error": str(e)}
            self._emit(progress_callback, stage="stock_list", status="done", **result["stages"].get("stock_list", {}))
        else:
            result["stages"]["stock_list"] = {"skipped": True}

        # ---- Stage 2: K线增量 ----
        if self.is_interrupted():
            return result
        self._emit(progress_callback, stage="kline_daily", status="running")
        try:
            r2 = KlineDailyUpdater({
                "mode": "smart",
                "adjust": p.adjust,
                "days_back": p.days_back,
                "workers": p.workers,
                "only_active": p.only_active,
                "codes": p.codes,
                "since_list_date": p.since_list_date,
            }).run()
            result["stages"]["kline_daily"] = r2.get("stats", r2)
        except Exception as e:
            self.logger.warning(f"{self._log_prefix} kline_daily 失败: {e}")
            result["stages"]["kline_daily"] = {"error": str(e)}
        self._emit(progress_callback, stage="kline_daily", status="done", **result["stages"].get("kline_daily", {}))

        # ---- Stage 3: 指数 ----
        if self.is_interrupted():
            return result
        self._emit(progress_callback, stage="index_daily", status="running")
        try:
            r3 = IndexDailyUpdater({}).run()
            result["stages"]["index_daily"] = r3
        except Exception as e:
            self.logger.warning(f"{self._log_prefix} index_daily 失败: {e}")
            result["stages"]["index_daily"] = {"error": str(e)}
        self._emit(progress_callback, stage="index_daily", status="done", **result["stages"].get("index_daily", {}))

        self._emit(progress_callback, stage="all", status="done")
        self.logger.info(f"{self._log_prefix} 增量同步完成: {result['stages']}")
        return result

    def _emit(self, callback, **kw):
        self._progress(callback, **kw)
