"""
定时调度服务 —— 后台线程 + schedule 库

- 启动后按配置的时间(如 16:30)每天自动执行数据更新
- 支持启停 / 配置修改 / 立即触发 / 运行历史
- 默认配置每天 16:30 执行 股票列表 + 指数 + 日K线
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import schedule

logger = logging.getLogger("scheduler")

DEFAULT_CONFIG = {
    "time": "16:30",                       # HH:MM 格式
    "tasks": ["stock_list", "index", "kline_daily"],  # 任务列表(按顺序)
    "adjust": "qfq",                       # 日K 复权方式
    "days": 365,                           # 日K 回溯天数
    "workers": 8,                          # 并发线程数
}


class SchedulerService:
    """单例调度服务"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.config: Dict = dict(DEFAULT_CONFIG)
        self.enabled: bool = False
        self.history: List[Dict] = []  # 最近 20 次运行
        self.last_run: Optional[Dict] = None
        self.next_run_at: Optional[str] = None

    # ---------- 状态 ----------
    def get_status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "running": self._is_running(),
            "config": dict(self.config),
            "next_run_at": self.next_run_at,
            "last_run": self.last_run,
            "history_count": len(self.history),
        }

    def _is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- 控制 ----------
    def start(self, config: Optional[Dict] = None) -> Dict:
        """启动调度"""
        with self._lock:
            if config:
                self._validate_config(config)
                self.config.update(config)
            self.enabled = True
            self._stop_event.clear()

        # 重新计算下次运行时间
        self._update_next_run()

        if self._is_running():
            logger.info("[Scheduler] 已在运行中,仅更新配置")
            return self.get_status()

        self._thread = threading.Thread(
            target=self._loop, name="SchedulerLoop", daemon=True,
        )
        self._thread.start()
        logger.info(f"[Scheduler] 已启动: time={self.config['time']} tasks={self.config['tasks']}")
        return self.get_status()

    def stop(self) -> Dict:
        """停止调度"""
        with self._lock:
            self.enabled = False
            self._stop_event.set()
        logger.info("[Scheduler] 已停止")
        # 等线程退出
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self.next_run_at = None
        return self.get_status()

    def trigger_now(self) -> Dict:
        """立即触发一次(不等定时)"""
        logger.info("[Scheduler] 手动触发")
        record = self._run_jobs()
        # 同步更新 last_run,保持状态一致
        self.last_run = record
        return {"triggered": True, "record": record}

    def update_config(self, config: Dict) -> Dict:
        """仅修改配置,不立即重启(下次启动生效或热重启)"""
        with self._lock:
            self._validate_config(config)
            old = dict(self.config)
            self.config.update(config)
            changed = old != self.config

        if changed and self._is_running():
            # 热重启:清空 schedule 任务,下一轮自动按新配置生效
            schedule.clear()
            self._register_schedule()
            logger.info(f"[Scheduler] 配置已更新并热应用: {self.config}")

        self._update_next_run()
        return self.get_status()

    # ---------- 内部 ----------
    def _validate_config(self, cfg: Dict):
        """校验配置"""
        if "time" in cfg:
            try:
                datetime.strptime(cfg["time"], "%H:%M")
            except ValueError:
                raise ValueError(f"time 格式错误,应为 HH:MM: {cfg['time']}")
        if "tasks" in cfg:
            valid = {"stock_list", "index", "kline_daily", "enrich", "daily_smart"}
            invalid = set(cfg["tasks"]) - valid
            if invalid:
                raise ValueError(f"未知任务: {invalid}, 可选 {valid}")
        if "adjust" in cfg and cfg["adjust"] not in {"qfq", "hfq", ""}:
            raise ValueError(f"adjust 必须是 qfq/hfq/: {cfg['adjust']}")

    def _update_next_run(self):
        """计算下次运行时间"""
        try:
            now = datetime.now()
            hh, mm = self.config["time"].split(":")
            target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            self.next_run_at = target.isoformat(timespec="seconds")
        except Exception as e:
            logger.warning(f"[Scheduler] 计算下次运行时间失败: {e}")
            self.next_run_at = None

    def _register_schedule(self):
        """注册 schedule 任务(每次配置变更后调用)"""
        schedule.clear()
        schedule.every().day.at(self.config["time"]).do(self._run_jobs_with_record)

    def _loop(self):
        """调度主循环"""
        self._register_schedule()
        self._update_next_run()
        logger.info(f"[Scheduler] 循环已启动,下次运行: {self.next_run_at}")
        while not self._stop_event.is_set():
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error(f"[Scheduler] run_pending 异常: {e}")
            # 30 秒一次,同时支持快速响应 stop
            if self._stop_event.wait(timeout=30):
                break
        logger.info("[Scheduler] 循环退出")

    def _run_jobs_with_record(self):
        """schedule 触发的入口(包一层用于记录)"""
        self.last_run = self._run_jobs()

    def _run_jobs(self) -> Dict:
        """执行配置中的所有任务"""
        record = {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "tasks": [],
            "success": True,
            "error": None,
        }
        logger.info(f"[Scheduler] 开始执行计划任务: {self.config['tasks']}")
        try:
            from updater.parallel_updater import ParallelKlineUpdater

            for task_name in self.config["tasks"]:
                t0 = datetime.now()
                t_record = {
                    "task": task_name,
                    "started_at": t0.isoformat(timespec="seconds"),
                    "status": "running",
                    "result": None,
                    "error": None,
                }
                try:
                    if task_name == "stock_list":
                        u = ParallelKlineUpdater()
                        result = u.update_stock_list()
                        t_record["result"] = {"updated": result}
                    elif task_name == "index":
                        u = ParallelKlineUpdater()
                        result = u.update_index()
                        t_record["result"] = {"updated": result}
                    elif task_name == "kline_daily":
                        u = ParallelKlineUpdater(max_workers=self.config.get("workers", 8))
                        stats = u.update_all(
                            adjust=self.config.get("adjust", "qfq"),
                            days_back=self.config.get("days", 365),
                            only_active=True,
                        )
                        t_record["result"] = stats
                    elif task_name == "enrich":
                        u = ParallelKlineUpdater()
                        stats = u.enrich_stock_info(
                            enrich_workers=self.config.get("workers", 4),
                        )
                        t_record["result"] = stats
                    elif task_name == "daily_smart":
                        u = ParallelKlineUpdater(max_workers=self.config.get("workers", 8))
                        stats = u.update_daily_smart_only(
                            adjust=self.config.get("adjust", "qfq"),
                            days_back=self.config.get("days", 365),
                        )
                        t_record["result"] = stats
                    t_record["status"] = "success"
                except Exception as e:
                    t_record["status"] = "failed"
                    t_record["error"] = str(e)[:200]
                    record["success"] = False
                    logger.exception(f"[Scheduler] 任务 {task_name} 失败: {e}")

                t_record["ended_at"] = datetime.now().isoformat(timespec="seconds")
                record["tasks"].append(t_record)
        except Exception as e:
            record["success"] = False
            record["error"] = str(e)[:200]
            logger.exception(f"[Scheduler] 整体执行失败: {e}")

        record["ended_at"] = datetime.now().isoformat(timespec="seconds")
        # 记录历史
        with self._lock:
            self.history.insert(0, record)
            self.history = self.history[:20]  # 只保留最近 20 次
        logger.info(f"[Scheduler] 计划任务完成: success={record['success']} "
                     f"耗时={self._duration(record)}")
        return record

    @staticmethod
    def _duration(record: Dict) -> str:
        try:
            s = datetime.fromisoformat(record["started_at"])
            e = datetime.fromisoformat(record["ended_at"])
            return f"{(e - s).total_seconds():.1f}s"
        except Exception:
            return "-"


# 全局单例
scheduler_service = SchedulerService()