"""
定时调度服务 —— 已重构为按数据类型独立 cron。

- 每个数据任务(STOCK_LIST / STOCK_ENRICH / INDEX_DAILY / KLINE_DAILY)一条独立 cron,
  配置存在 scheduler_job 表,可热更新。
- 主循环每分钟检查一次,匹配则触发对应 updater(走 task_manager 的统一任务机制)。
- 路由在 app/routers/scheduler.py,本模块只导出服务单例。
"""
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

from app.cron import CronExpr
from db.database import get_conn
from updater.registry import REGISTER, resolve_task
from updater.types import DEFAULT_JOBS

logger = logging.getLogger("scheduler")


# ---------- DB 读写 ----------
# 已被新组合任务(fetch_all / sync_latest)替代的旧任务,启动时自动清理
_LEGACY_SCHEDULER_TASKS = (
    "stock_list", "index_daily", "kline_daily", "stock_enrich",
)


def _ensure_jobs_seeded():
    """首次启动时把 DEFAULT_JOBS 写入 scheduler_job 表(已存在则跳过)。

    同时清理已被 fetch_all / sync_latest 替代的旧 4 类任务。
    """
    with get_conn() as conn:
        # 1) 清掉旧任务(无论 enabled 与否)
        cur = conn.execute(
            f"DELETE FROM scheduler_job WHERE task IN ({','.join('?' * len(_LEGACY_SCHEDULER_TASKS))})",
            _LEGACY_SCHEDULER_TASKS,
        )
        if cur.rowcount:
            logger.info(f"[Scheduler] 已清理 {cur.rowcount} 个旧任务")

        # 2) Seed 新任务(DEFAULT_JOBS),已存在则跳过
        existing = {r[0] for r in conn.execute("SELECT task FROM scheduler_job").fetchall()}
        for task, cron, enabled, params in DEFAULT_JOBS:
            if task not in existing:
                conn.execute(
                    "INSERT INTO scheduler_job(task, cron, enabled, params_json) VALUES (?,?,?,?)",
                    (task, cron, 1 if enabled else 0, json.dumps(params, ensure_ascii=False)),
                )


def _load_jobs() -> List[Dict]:
    """从 DB 加载所有任务配置"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT task, cron, enabled, params_json, last_run_at, last_status "
            "FROM scheduler_job ORDER BY task"
        ).fetchall()
    return [
        {
            "task": r[0],
            "cron": r[1],
            "enabled": bool(r[2]),
            "params": json.loads(r[3] or "{}"),
            "last_run_at": r[4],
            "last_status": r[5],
        }
        for r in rows
    ]


def _update_last_run(task: str, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduler_job SET last_run_at = ?, last_status = ? WHERE task = ?",
            (datetime.now().isoformat(timespec="seconds"), status, task),
        )


# ---------- 主调度器 ----------
class SchedulerService:
    """单例调度服务"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.enabled: bool = False
        self.history: List[Dict] = []
        self.last_run: Optional[Dict] = None
        self.next_run_at: Optional[str] = None
        self._jobs_cache: List[Dict] = []
        self._cron_cache: Dict[str, CronExpr] = {}

    # ---------- 状态 ----------
    def get_status(self) -> Dict:
        try:
            jobs = _load_jobs()
        except Exception as e:
            logger.warning(f"[Scheduler] 加载 jobs 失败: {e}")
            jobs = []
        return {
            "enabled": self.enabled,
            "running": self._is_running(),
            "next_run_at": self.next_run_at,
            "last_run": self.last_run,
            "history_count": len(self.history),
            "jobs": jobs,
        }

    def _is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- 控制 ----------
    def start(self, config: Optional[Dict] = None) -> Dict:
        with self._lock:
            self.enabled = True
            self._stop_event.clear()
        _ensure_jobs_seeded()

        if self._is_running():
            self._reload_jobs()
            logger.info("[Scheduler] 已在运行,刷新 jobs")
        else:
            self._thread = threading.Thread(
                target=self._loop, name="SchedulerLoop", daemon=True,
            )
            self._thread.start()
            logger.info("[Scheduler] 已启动(按任务 cron)")
        return self.get_status()

    def stop(self) -> Dict:
        with self._lock:
            self.enabled = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self.next_run_at = None
        logger.info("[Scheduler] 已停止")
        return self.get_status()

    def trigger_now(self, task: Optional[str] = None) -> Dict:
        """立即触发:
           task=None  → 触发所有 enabled jobs(旧 trigger 行为)
           task="xxx" → 触发单个任务
        """
        if task:
            return self._trigger_one(task)

        logger.info("[Scheduler] 手动触发全部 jobs")
        triggered = []
        for job in _load_jobs():
            if not job["enabled"]:
                continue
            try:
                self._dispatch(job)
                triggered.append(job["task"])
            except Exception as e:
                logger.error(f"[Scheduler] {job['task']} 触发失败: {e}")
        return {"triggered": triggered, "count": len(triggered)}

    def _trigger_one(self, task: str) -> Dict:
        try:
            from updater.types import TaskType
            try:
                task_type = TaskType(task)
            except ValueError:
                # 旧别名也接受
                from updater.registry import LEGACY_TASK_ALIAS
                if task in LEGACY_TASK_ALIAS:
                    task_type, _ = LEGACY_TASK_ALIAS[task]
                else:
                    return {"triggered": False, "error": f"未知 task: {task}"}
        except Exception as e:
            return {"triggered": False, "error": str(e)}

        jobs = _load_jobs()
        job = next((j for j in jobs if j["task"] == task_type.value), None)
        if not job:
            return {"triggered": False, "error": "job 未注册"}
        try:
            self._dispatch(job)
            return {"triggered": True, "task": task_type.value}
        except Exception as e:
            return {"triggered": False, "error": str(e)}

    def update_job(self, task: str, cron: Optional[str] = None,
                   enabled: Optional[bool] = None, params: Optional[dict] = None) -> Dict:
        """更新单个 job 配置,即时热生效"""
        from updater.types import TaskType
        try:
            task_type = TaskType(task)
        except ValueError:
            from updater.registry import LEGACY_TASK_ALIAS
            if task not in LEGACY_TASK_ALIAS:
                raise ValueError(f"未知 task: {task}")
            task_type, _ = LEGACY_TASK_ALIAS[task]

        if cron is not None:
            CronExpr(cron)  # 校验
        with get_conn() as conn:
            if not conn.execute(
                "SELECT 1 FROM scheduler_job WHERE task=?", (task_type.value,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO scheduler_job(task, cron, enabled, params_json) VALUES (?,?,?,?)",
                    (task_type.value, cron or "0 0 * * *", 0,
                     json.dumps(params or {}, ensure_ascii=False)),
                )
            else:
                sets, vals = [], []
                if cron is not None:
                    sets.append("cron = ?"); vals.append(cron)
                if enabled is not None:
                    sets.append("enabled = ?"); vals.append(1 if enabled else 0)
                if params is not None:
                    sets.append("params_json = ?"); vals.append(
                        json.dumps(params, ensure_ascii=False)
                    )
                sets.append("updated_at = ?"); vals.append(
                    datetime.now().isoformat(timespec="seconds")
                )
                vals.append(task_type.value)
                conn.execute(
                    f"UPDATE scheduler_job SET {', '.join(sets)} WHERE task = ?", vals
                )
        if self._is_running():
            self._reload_jobs()
        return {"task": task_type.value, "updated": True}

    def reload_jobs(self):
        self._reload_jobs()

    # ---------- 兼容旧端点 ----------
    def update_config(self, config: Dict) -> Dict:
        """兼容旧 update_config:
           time = HH:MM         -> 合并到所有 enabled jobs 的 cron
           tasks = [list]       -> 仅启用列出的任务
           adjust/days/workers  -> 写入 KLINE_DAILY params
        """
        _ensure_jobs_seeded()
        if "tasks" in config:
            wanted = set()
            for t in config["tasks"]:
                try:
                    tt, _ = resolve_task(t)
                    wanted.add(tt.value)
                except ValueError:
                    raise ValueError(f"未知 task: {t}")
            with get_conn() as conn:
                conn.execute("UPDATE scheduler_job SET enabled = 0")
                for w in wanted:
                    conn.execute(
                        "UPDATE scheduler_job SET enabled = 1 WHERE task = ?", (w,)
                    )
        if "time" in config:
            try:
                hh, mm = config["time"].split(":")
                cron = f"{int(mm)} {int(hh)} * * *"
                with get_conn() as conn:
                    conn.execute("UPDATE scheduler_job SET cron = ?", (cron,))
            except Exception as e:
                raise ValueError(f"time 格式错误: {e}")
        kparams = {}
        for k in ("adjust", "days", "workers"):
            if k in config:
                kparams[k] = config[k]
        if kparams:
            if "days" in kparams:
                kparams["days_back"] = kparams.pop("days")
            with get_conn() as conn:
                cur = conn.execute(
                    "SELECT params_json FROM scheduler_job WHERE task='kline_daily'"
                ).fetchone()
                if cur:
                    p = json.loads(cur[0] or "{}")
                    p.update(kparams)
                    conn.execute(
                        "UPDATE scheduler_job SET params_json = ? WHERE task='kline_daily'",
                        (json.dumps(p, ensure_ascii=False),)
                    )
        if self._is_running():
            self._reload_jobs()
        return self.get_status()

    # ---------- 内部 ----------
    def _reload_jobs(self):
        """重载 jobs 缓存(线程安全)"""
        try:
            self._jobs_cache = _load_jobs()
            self._cron_cache = {
                j["task"]: CronExpr(j["cron"]) for j in self._jobs_cache
            }
        except Exception as e:
            logger.warning(f"[Scheduler] 重载 jobs 失败: {e}")

    def _loop(self):
        """主循环:每分钟检查每条 job 的 cron 是否触发"""
        self._reload_jobs()
        logger.info(f"[Scheduler] 循环已启动,监控 {len(self._jobs_cache)} 条 jobs")

        last_minute = -1
        while not self._stop_event.is_set():
            now = datetime.now()
            cur_minute = (now.year, now.month, now.day, now.hour, now.minute)
            if cur_minute != last_minute:
                last_minute = cur_minute
                for job in list(self._jobs_cache):
                    if not job["enabled"]:
                        continue
                    cron = self._cron_cache.get(job["task"])
                    if not cron or not cron.matches(now):
                        continue
                    try:
                        self._dispatch(job)
                    except Exception as e:
                        logger.error(f"[Scheduler] {job['task']} 调度执行失败: {e}")
                self._update_next_run_preview()

            if self._stop_event.wait(timeout=30):
                break

        logger.info("[Scheduler] 循环退出")

    def _update_next_run_preview(self):
        try:
            now = datetime.now()
            candidates = []
            for job in self._jobs_cache:
                if not job["enabled"]:
                    continue
                cron = self._cron_cache.get(job["task"])
                if cron:
                    candidates.append(cron.next_after(now))
            self.next_run_at = (
                min(candidates).isoformat(timespec="seconds") if candidates else None
            )
        except Exception:
            self.next_run_at = None

    def _dispatch(self, job: Dict):
        """根据 job 配置实例化对应 updater 并提交到 task_manager"""
        from app.task_manager import task_manager

        try:
            task_type, defaults = resolve_task(job["task"])
        except ValueError:
            logger.warning(f"[Scheduler] 未知 task: {job['task']}")
            return

        UpdaterCls, ParamModel = REGISTER.get(task_type, (None, None))
        if UpdaterCls is None:
            logger.warning(f"[Scheduler] {task_type} 未注册 updater")
            return

        merged = {**defaults, **(job.get("params") or {})}
        try:
            updater = UpdaterCls(merged)
        except Exception as e:
            logger.warning(f"[Scheduler] {job['task']} 参数校验失败: {e}")
            return

        name = f"{task_type.value}_cron"
        task_id = task_manager.submit(name, updater.run)
        logger.info(f"[Scheduler] 调度执行 {task_type.value} -> task_id={task_id}")
        _update_last_run(task_type.value, "dispatched")

        record = {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "task": task_type.value,
            "task_id": task_id,
            "trigger": "scheduler",
        }
        with self._lock:
            self.history.insert(0, record)
            self.history = self.history[:30]
            self.last_run = record


# 全局单例
scheduler_service = SchedulerService()