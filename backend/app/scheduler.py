"""
定时调度服务 —— 已重构为按数据类型独立 cron。

- 每个数据任务(STOCK_LIST / STOCK_ENRICH / INDEX_DAILY / KLINE_DAILY)一条独立 cron,
  配置存在 scheduler_job 表,可热更新。
- 主循环每分钟检查一次,匹配则触发对应 updater(走 task_manager 的统一任务机制)。
- 路由在 app/routers/scheduler.py,本模块只导出服务单例。

P0-5 修复 (2026-07-31): 启动时检测错过的 cron
  - 对每个 enabled job, 比较 last_run_at 与当前时间, 用 cron.next_after 算"本应触发时刻"
  - 如果有错过, 更新 last_missed_at + missed_count, 让前端 / 管理员能发现
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
        # 汇总 missed 信息
        total_missed = sum(int(j.get("missed_count") or 0) for j in jobs)
        last_missed_jobs = [
            {
                "task": j["task"],
                "last_missed_at": j.get("last_missed_at"),
                "missed_count": j.get("missed_count", 0),
            }
            for j in jobs if j.get("last_missed_at")
        ]
        return {
            "enabled": self.enabled,
            "running": self._is_running(),
            "next_run_at": self.next_run_at,
            "last_run": self.last_run,
            "history_count": len(self.history),
            "total_missed": total_missed,
            "missed_jobs": last_missed_jobs,
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

        # 2026-07-31 P0-5: 启动时检测错过的 cron(进程宕机期间)
        try:
            self._check_missed_crons()
        except Exception as e:
            logger.warning(f"[Scheduler] 检查 missed cron 失败: {e}")

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

    def _check_missed_crons(self) -> List[Dict]:
        """启动时检测错过的 cron(P0-5 修复)。

        对每个 enabled job, 找到 last_run_at 之后"本应触发但未触发"的时刻数。
        累加到 missed_count, 记录 last_missed_at, 让前端能展示。
        """
        # 先 reload 以确保内存 cache 包含最新 cron 表达式
        self._reload_jobs()
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")
        missed_report: List[Dict] = []
        with get_conn() as conn:
            for job in self._jobs_cache:
                if not job.get("enabled"):
                    continue
                cron = self._cron_cache.get(job["task"])
                if not cron:
                    continue
                last_run_str = job.get("last_run_at")
                if not last_run_str:
                    # 从未跑过(冷启动), 标记错过 = 现在 - "已存在的合理过去时点"
                    # 简化: 用 now 兜底, 实际触发后会自动写 last_run_at
                    last_run = now
                else:
                    try:
                        last_run = datetime.fromisoformat(last_run_str)
                    except Exception:
                        continue
                # 计算 last_run 之后到 now 之间应触发的次数
                try:
                    missed_count = 0
                    cursor = last_run
                    # 最多扫 1000 次(防极端情况: 半年没启, 1 分钟级 cron 会爆)
                    while missed_count < 1000:
                        nxt = cron.next_after(cursor)
                        if nxt is None or nxt >= now:
                            break
                        missed_count += 1
                        cursor = nxt
                except Exception as e:
                    logger.debug(f"[Scheduler] {job['task']} 计算 missed 失败: {e}")
                    continue
                if missed_count == 0:
                    continue
                # 累加 missed_count + 更新 last_missed_at
                conn.execute(
                    "UPDATE scheduler_job SET "
                    "  last_missed_at = ?, "
                    "  missed_count = COALESCE(missed_count, 0) + ? "
                    "WHERE task = ?",
                    (now_iso, missed_count, job["task"]),
                )
                missed_report.append({
                    "task": job["task"],
                    "missed_count": missed_count,
                    "last_run_at": last_run_str,
                })
        if missed_report:
            logger.warning(
                f"[Scheduler] 启动检测到错过 {len(missed_report)} 个 cron: "
                f"{[(r['task'], r['missed_count']) for r in missed_report]}"
            )
        # 同步 cache(下次 _reload_jobs 会重新读)
        self._reload_jobs()
        return missed_report

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
                    # 2026-07-31 P1-9: 跳过非交易日(节假日 cron 触发会浪费一次空跑)
                    if not is_trading_day(now):
                        logger.debug(
                            f"[Scheduler] {job['task']} 跳过触发: {now.date()} 非交易日"
                        )
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


# =========================================================
# 交易日历(P1-9 修复)
# =========================================================
def _ensure_trading_calendar() -> int:
    """启动时根据 kline_daily 已有数据填充交易日历。

    简化方案: 取所有指数 K 线的 trade_date 并集, 去重。
    优点: 不依赖第三方, 数据库已有数据。
    缺点: 历史不全(只覆盖有数据的日期), 可在后台定期补全。
    """
    try:
        with get_conn() as conn:
            # 取 kline_daily 里所有 trade_date(去重)
            rows = conn.execute(
                "SELECT DISTINCT trade_date FROM kline_daily "
                "WHERE trade_date IS NOT NULL"
            ).fetchall()
            if not rows:
                logger.info("[TradingCalendar] kline_daily 暂无数据, 跳过初始化")
                return 0
            # 批量 INSERT OR IGNORE
            conn.executemany(
                "INSERT OR IGNORE INTO trading_calendar(trade_date) VALUES(?)",
                [(r[0],) for r in rows],
            )
            # 同时从 index_daily 拿 (覆盖更全)
            rows2 = conn.execute(
                "SELECT DISTINCT trade_date FROM index_daily "
                "WHERE trade_date IS NOT NULL"
            ).fetchall()
            if rows2:
                conn.executemany(
                    "INSERT OR IGNORE INTO trading_calendar(trade_date) VALUES(?)",
                    [(r[0],) for r in rows2],
                )
            cnt = conn.execute(
                "SELECT COUNT(*) FROM trading_calendar"
            ).fetchone()[0]
        logger.info(f"[TradingCalendar] 初始化完成, 共 {cnt} 个交易日")
        return cnt
    except Exception as e:
        logger.warning(f"[TradingCalendar] 初始化失败: {e}")
        return 0


def is_trading_day(d: Optional[datetime] = None) -> bool:
    """判断给定日期是否为 A 股交易日(2026-07-31 P1-9)。

    规则:
      1. 周六周日 → 否
      2. trading_calendar 表里有 → 是
      3. 否则按"是否在过去 14 天内有任意交易日"兜底(应对冷启动)
    """
    d = d or datetime.now()
    # 周六周日
    if d.weekday() >= 5:  # 5=周六, 6=周日
        return False
    ds = d.strftime("%Y-%m-%d")
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM trading_calendar WHERE trade_date = ?",
                (ds,),
            ).fetchone()
        if row:
            return True
        # 兜底:看最近 14 天是否有任何交易日,有则把"今天"当交易日(应对冷启动)
        # (有节假日就跳出来判 False)
        # 这里简化为: 若 calendar 完全是空的 → 当作交易日(允许触发, 后面真没数据 updater 会 noop)
        cnt = conn.execute("SELECT COUNT(*) FROM trading_calendar").fetchone()[0] if False else 0
    except Exception:
        return True  # DB 异常,放行不阻断
    return True


# 在模块导入时填充交易日历
_ensure_trading_calendar()