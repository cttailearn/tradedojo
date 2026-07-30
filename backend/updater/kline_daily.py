"""
日 K 线 updater —— 支持两种模式:
  mode=full : 全量(按 days_back 回溯),适合首次初始化
  mode=smart: 只处理缺失/过期股票,适合日终增量
复用 ParallelKlineUpdater 的并行拉取 + Writer 单写者架构(性能已验证),
此处仅负责参数校验、模式分发、结果归一化。
"""
import logging
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import BaseUpdater
from .types import TaskType


class KlineDailyParams(BaseModel):
    mode: Literal["full", "smart"] = Field(
        "smart", description="full=全量回溯,smart=仅缺失/过期"
    )
    adjust: Literal["qfq", "hfq", ""] = Field(
        "qfq", description="复权方式"
    )
    days_back: int = Field(
        0, ge=0, le=3650,
        description="回溯天数(0=自上市以来全量,>0=按天数回溯)",
    )
    only_active: bool = Field(
        True, description="是否只处理 is_active=1 的股票"
    )
    workers: int = Field(
        6, ge=1, le=32, description="并发线程数"
    )
    codes: Optional[list[str]] = Field(
        None, description="限定到指定代码(单股/批量),None=全部"
    )
    since_list_date: bool = Field(
        False,
        description=(
            "True 时按每只股票各自的 list_date 拉取(days_back=0 时不截断)"
        ),
    )


class KlineDailyUpdater(BaseUpdater):
    task_type = TaskType.KLINE_DAILY
    ParamModel = KlineDailyParams
    display_name = "日 K 线"

    def run(self, progress_callback=None) -> dict:
        # 延迟 import,避免循环依赖
        from updater.parallel_updater import ParallelKlineUpdater

        p = self.params
        self.logger.info(
            f"{self._log_prefix} mode={p.mode} adjust={p.adjust} "
            f"days_back={p.days_back} workers={p.workers}"
        )

        u = ParallelKlineUpdater(max_workers=p.workers)

        if p.mode == "smart":
            stats = u.update_daily_smart_only(
                adjust=p.adjust or "qfq", days_back=p.days_back,
                codes=p.codes,
                since_list_date=p.since_list_date,
            )
        else:
            stats = u.update_all(
                adjust=p.adjust or "qfq",
                days_back=p.days_back,
                only_active=p.only_active,
                codes=p.codes,
                since_list_date=p.since_list_date,
            )

        result = {
            "mode": p.mode,
            "adjust": p.adjust,
            "days_back": p.days_back,
            "stats": dict(stats) if isinstance(stats, dict) else {},
        }
        self.logger.info(f"{self._log_prefix} 完成: {result}")
        return result