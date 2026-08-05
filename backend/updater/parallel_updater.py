"""
多线程并行 K线 更新器

架构:
- 1 个 Writer 线程(单写者,避免 SQLite 锁竞争)
- N 个 Worker 线程(并发拉取,信号量限流)
- 写入采用批处理(事务 + 批量 INSERT)
"""
import time
import queue
import logging
import threading
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from config import FetchConfig
from db.database import get_conn, executemany
from fetcher.manager import fetcher_manager
from updater.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


@dataclass
class KlineRecord:
    """单条 K线记录(内存表示)"""
    code: str
    trade_date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    pre_close: Optional[float]
    change_amount: Optional[float]
    pct_change: Optional[float]
    volume: Optional[int]
    amount: Optional[float]
    turnover_rate: Optional[float]
    adjust_type: str


class ParallelKlineUpdater:
    """多线程 K线 更新器(支持断点续传)"""

    def __init__(self, max_workers: int = None):
        # 用 fetcher_manager(支持 akshare→baostock→tushare 自动 failover)
        self.fetcher = fetcher_manager.get_fetcher()
        self.max_workers = max_workers or FetchConfig.MAX_WORKERS
        self.fetch_sem = threading.Semaphore(FetchConfig.MAX_CONCURRENT_FETCH)

        self.write_queue: queue.Queue = queue.Queue(maxsize=10000)
        self.stats_lock = threading.Lock()
        self.stats = {
            "success": 0, "failed": 0, "skipped": 0,
            "empty": 0, "rows": 0
        }
        self.stop_flag = threading.Event()
        self.interrupted = False

        # 断点续传
        self.checkpoint = CheckpointManager("daily_kline")

        # 注册信号处理
        import signal
        try:
            signal.signal(signal.SIGINT, self._on_signal)
            signal.signal(signal.SIGTERM, self._on_signal)
        except ValueError:
            # Windows 子线程里会抛,忽略
            pass

    def _on_signal(self, signum, frame):
        """优雅退出"""
        logger.warning(f"\n[中断] 收到信号 {signum},保存快照...")
        self.interrupted = True
        self.stop_flag.set()
        self.checkpoint.save_snapshot()

    # ---------- Writer 线程 ----------
    def _writer_loop(self):
        """单写者线程:批量入队 → 批量写库"""
        buffer: List[KlineRecord] = []
        last_write = time.time()

        def flush():
            nonlocal buffer, last_write
            if not buffer:
                return
            sql = """
            -- ON CONFLICT 语法,兼容 SQLite/PostgreSQL
            INSERT INTO kline_daily
            (code, trade_date, open, high, low, close, pre_close,
             change_amount, pct_change, volume, amount,
             turnover_rate, adjust_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (code, trade_date, adjust_type) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                pre_close=excluded.pre_close,
                change_amount=excluded.change_amount,
                pct_change=excluded.pct_change,
                volume=excluded.volume,
                amount=excluded.amount,
                turnover_rate=excluded.turnover_rate,
                updated_at=excluded.updated_at
            """
            rows = [
                (r.code, r.trade_date, r.open, r.high, r.low, r.close,
                 r.pre_close, r.change_amount, r.pct_change, r.volume,
                 r.amount, r.turnover_rate, r.adjust_type,
                 datetime.now().isoformat())
                for r in buffer
            ]
            try:
                executemany(sql, rows)
                with self.stats_lock:
                    self.stats["rows"] += len(rows)
                logger.debug(f"[Writer] 写入 {len(rows)} 行")
            except Exception as e:
                logger.error(f"[Writer] 写入失败: {e}")
            buffer = []
            last_write = time.time()

        while not (self.stop_flag.is_set() and self.write_queue.empty()):
            try:
                item = self.write_queue.get(timeout=0.5)
                if item is None:  # 哨兵
                    break
                buffer.append(item)
            except queue.Empty:
                pass

            # 触发刷新条件
            if (len(buffer) >= FetchConfig.BATCH_SIZE or
                (buffer and time.time() - last_write > FetchConfig.WRITE_INTERVAL)):
                flush()

        flush()  # 收尾

    # ---------- Worker 任务 ----------
    def _worker_task(
        self, code: str, name: str,
        start: str, end: str, adjust: str
    ) -> int:
        """处理单只股票:拉取 → 入队 → 更新断点"""
        # 1. 跳过已完成
        if self.checkpoint.is_done(code):
            with self.stats_lock:
                self.stats["skipped"] += 1
            return 0

        if self.interrupted:
            return 0

        # 2. 拉取数据(信号量限流)
        with self.fetch_sem:
            if self.interrupted:
                return 0
            try:
                df = self.fetcher.get_daily_kline(code, start, end, adjust)
            except Exception as e:
                self.checkpoint.mark_failed(code, str(e))
                with self.stats_lock:
                    self.stats["failed"] += 1
                logger.warning(f"[{code} {name}] 拉取失败: {e}")
                return 0

        # 3. 空数据(可能停牌/退市)
        if df is None or df.empty:
            self.checkpoint.mark_success(code, 0)
            with self.stats_lock:
                self.stats["empty"] += 1
            return 0

        # 4. 转 record 并入队
        count = 0
        try:
            for row in df.itertuples(index=False):
                rec = KlineRecord(
                    code=row.code, trade_date=row.trade_date,
                    open=row.open, high=row.high, low=row.low,
                    close=row.close, pre_close=row.pre_close,
                    change_amount=row.change_amount,
                    pct_change=row.pct_change,
                    volume=row.volume, amount=row.amount,
                    turnover_rate=row.turnover_rate,
                    adjust_type=row.adjust_type
                )
                self.write_queue.put(rec)
                count += 1

            self.checkpoint.mark_success(code, count)
            with self.stats_lock:
                self.stats["success"] += 1
        except Exception as e:
            self.checkpoint.mark_failed(code, str(e))
            with self.stats_lock:
                self.stats["failed"] += 1
            logger.warning(f"[{code} {name}] 入队失败: {e}")

        return count

    # ---------- 主入口 ----------
    def update_all(
        self,
        adjust: str = "qfq",
        only_active: bool = True,
        days_back: int = None,
        codes: list = None,
        since_list_date: bool = False,
        progress_callback=None,
    ) -> dict:
        """
        并行更新所有股票 K线
        :param codes: 指定仅更新这些代码;为 None 时处理全部
        :param since_list_date: True 时按每只股票各自的 list_date 决定起始日(忽略 days_back)
        :param progress_callback: 可选回调,按真实完成股票数上报进度:
            progress_callback({total, completed, success, failed, empty, rows})
        :return: 统计字典
        """
        # days_back=0 保持原样(0 表示全量自上市以来),仅在 None 时回退默认值
        if days_back is None:
            days_back = FetchConfig.DEFAULT_DAYS_BACK

        # 1. 获取股票列表
        with get_conn() as conn:
            if codes:
                # 限定到指定代码(单股/批量)
                placeholders = ",".join(["?"] * len(codes))
                sql = (
                    f"SELECT code, name, list_date "
                    f"FROM stock_list WHERE code IN ({placeholders})"
                )
                if only_active:
                    sql += " AND is_active = 1"
                all_stocks = conn.execute(sql, list(codes)).fetchall()
            else:
                sql = "SELECT code, name, list_date FROM stock_list"
                if only_active:
                    sql += " WHERE is_active = 1"
                all_stocks = conn.execute(sql).fetchall()
        logger.info(
            f"[目标] {len(all_stocks)} 只股票,复权={adjust},回溯 {days_back} 天"
            f"{' (限定 codes)' if codes else ''}"
            f"{' · 自上市起' if since_list_date else ''}"
        )

        # 2. 过滤待处理
        todo = [(c, n, ld) for c, n, ld in all_stocks if self.checkpoint.need_retry(c)]
        skipped = len(all_stocks) - len(todo)
        logger.info(
            f"[计划] 待处理 {len(todo)} 只,跳过 {skipped} 只已完成"
        )
        if not todo:
            logger.info("[OK] 全部完成,无需处理")
            return self.stats

        # 3. 启动 Writer
        writer_t = threading.Thread(
            target=self._writer_loop, daemon=True, name="Writer"
        )
        writer_t.start()

        # 4. 并行拉取
        end = datetime.now().strftime("%Y-%m-%d")
        today = datetime.now()

        def _resolve_start(list_date_raw: str, fallback_days: int) -> str:
            """根据 list_date 推导每只股的拉取起点;若 list_date 不可用则回退到 days_back。"""
            if list_date_raw and len(list_date_raw) >= 10:
                ld_str = list_date_raw[:10]
                try:
                    ld = datetime.strptime(ld_str, "%Y-%m-%d")
                    # 上限:不超过 today;下限:fallback_days=0 表示不截断(全量自上市以来)
                    delta_days = (today - ld).days
                    if delta_days < 0:
                        return end
                    if fallback_days and delta_days > fallback_days:
                        return (today - timedelta(days=fallback_days)).strftime("%Y-%m-%d")
                    return ld_str
                except ValueError:
                    pass
            if fallback_days:
                return (today - timedelta(days=fallback_days)).strftime("%Y-%m-%d")
            return end  # 全量(0):没有 list_date 时退到今天(即不拉)

        try:
            with ThreadPoolExecutor(
                max_workers=self.max_workers, thread_name_prefix="Worker"
            ) as pool:
                futures = {}
                for code, name, list_date in todo:
                    per_start = (
                        _resolve_start(list_date, days_back)
                        if since_list_date else start
                    )
                    futures[pool.submit(
                        self._worker_task, code, name, per_start, end, adjust
                    )] = (code, name)
                done = 0
                for fut in as_completed(futures):
                    if self.interrupted:
                        logger.warning("收到中断,停止派发新任务")
                        break
                    done += 1
                    try:
                        fut.result()
                    except Exception as e:
                        logger.error(f"Worker 异常: {e}")
                    if done % 100 == 0 or done == len(todo):
                        with self.stats_lock:
                            s = dict(self.stats)
                        logger.info(
                            f"  进度 {done}/{len(todo)} | "
                            f"成功 {s['success']} 失败 {s['failed']} "
                            f"空 {s['empty']} 写入 {s['rows']} 行"
                        )
                    # 真实股票数进度上报(前端进度条依赖)
                    if progress_callback and (done % 10 == 0 or done == len(todo)):
                        with self.stats_lock:
                            s = dict(self.stats)
                        try:
                            progress_callback({
                                "total": len(todo),
                                "completed": done,
                                "success": s["success"],
                                "failed": s["failed"],
                                "empty": s["empty"],
                                "rows": s["rows"],
                            })
                        except Exception as e:
                            logger.debug(f"progress callback error: {e}")
        finally:
            # 5. 通知 Writer 结束
            self.stop_flag.set()
            self.write_queue.put(None)
            writer_t.join(timeout=60)
            self.checkpoint.save_snapshot()

        logger.info(f"[完成] {self.stats}")
        return self.stats

    # ---------- 股票信息丰富(行业+上市日期) ----------
    def enrich_stock_info(
        self,
        enrich_workers: int = 4,
        profile_limit: int = None,
    ) -> dict:
        """
        批量补充 stock_list 的 industry 和 list_date
        分两阶段:
          Phase 1 - 行业板块批量映射(快速,~500次API调用)
          Phase 2 - 上市日期并行获取(较慢,~5000次API调用,可选)
        :param enrich_workers: Phase 2 并行数,0 表示跳过 Phase 2
        :param profile_limit: 仅处理前 N 只(测试用)
        :return: 统计字典
        """
        from db.database import get_conn

        result = {
            "industry_from_board": 0,
            "list_date_from_profile": 0,
            "list_date_from_kline": 0,
            "profile_failed": 0,
        }

        # ====== Phase 1: 行业板块映射 ======
        print("\n[Phase 1/2] 批量构建行业映射...")
        industry_map = self.fetcher.get_industry_map()
        if industry_map:
            with get_conn() as conn:
                # 批量更新
                updates = [
                    (industry, code)
                    for code, industry in industry_map.items()
                ]
                conn.executemany(
                    "UPDATE stock_list SET industry=? WHERE code=?",
                    updates,
                )
            result["industry_from_board"] = len(industry_map)
            print(f"  [OK] 已更新 {len(industry_map)} 只股票的行业信息")
        else:
            print("  [WARN] 行业映射为空,跳过")

        # ====== Phase 2: 上市日期(并行) ======
        if enrich_workers <= 0:
            print("\n[Phase 2/2] 跳过上市日期获取(workers=0)")
            # 用K线最早日期近似
            self._fill_list_date_from_kline()
            result["list_date_from_kline"] = self._count_filled_list_date()
            print(f"  [OK] 从K线补充 {result['list_date_from_kline']} 只股票上市日期")
            return result

        print(f"\n[Phase 2/2] 并行获取上市日期 (workers={enrich_workers})...")
        with get_conn() as conn:
            # 优先处理 list_date 为空且 is_active 的股票
            rows = conn.execute(
                "SELECT code FROM stock_list "
                "WHERE (list_date IS NULL OR list_date = '') AND is_active = 1"
            ).fetchall()
        todo_codes = [r[0] for r in rows]
        if profile_limit:
            todo_codes = todo_codes[:profile_limit]

        print(f"  待获取: {len(todo_codes)} 只 (list_date 为空且在市)")

        if not todo_codes:
            print("  [OK] 无需处理,所有股票已有上市日期")
            return result

        # 并行获取
        profile_ok = 0
        profile_fail = 0
        done = 0

        with ThreadPoolExecutor(
            max_workers=enrich_workers, thread_name_prefix="Profile"
        ) as pool:
            futures = {
                pool.submit(self.fetcher.get_stock_profile, code): code
                for code in todo_codes
            }
            for fut in as_completed(futures):
                code = futures[fut]
                done += 1
                try:
                    profile = fut.result()
                    if profile and profile.get("list_date"):
                        # 更新数据库
                        with get_conn() as conn:
                            updates = []
                            params = []
                            if profile.get("list_date"):
                                updates.append("list_date=?")
                                params.append(profile["list_date"])
                            # 如果 industry 还为空且 profile 里有,也补上
                            if profile.get("industry"):
                                updates.append("industry=?")
                                params.append(profile["industry"])
                            if updates:
                                params.append(code)
                                conn.execute(
                                    f"UPDATE stock_list SET {', '.join(updates)} WHERE code=?",
                                    params,
                                )
                        profile_ok += 1
                    else:
                        profile_fail += 1
                except Exception:
                    profile_fail += 1

                if done % 200 == 0 or done == len(todo_codes):
                    print(
                        f"  进度 {done}/{len(todo_codes)} | "
                        f"成功 {profile_ok} 失败 {profile_fail}"
                    )

        result["list_date_from_profile"] = profile_ok
        result["profile_failed"] = profile_fail

        # Fallback: 对 API 获取失败的,用 K线 最早日期补充
        remaining = self._fill_list_date_from_kline()
        result["list_date_from_kline"] = remaining
        if remaining:
            print(f"  [OK] 从K线补充 {remaining} 只(API未获取到的)")

        print(
            f"\n[完成] industry={result['industry_from_board']}, "
            f"list_date(profile)={profile_ok}, "
            f"list_date(kline)={result['list_date_from_kline']}, "
            f"failed={profile_fail}"
        )
        return result

    def _fill_list_date_from_kline(self) -> int:
        """从 K线 最早日期补充 list_date(当 profile API 不可用时)"""
        from db.database import get_conn
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

    def _count_filled_list_date(self) -> int:
        """统计已补充 list_date 的股票数"""
        from db.database import query_one
        row = query_one(
            "SELECT COUNT(*) FROM stock_list "
            "WHERE list_date IS NOT NULL AND list_date != ''"
        )
        return row[0] if row else 0

    # ---------- 分钟K线智能更新 ----------
    def update_minute_smart(
        self,
        period: int = 5,
        days_back: int = 30,
        workers: int = 4,
        limit: int = None,
    ) -> dict:
        """
        智能分钟K线更新 - 跳过已有当日数据的股票
        :param period: 1/5/15/30/60
        :param days_back: 回溯天数(建议 30-60 天)
        :param workers: 并发数
        :param limit: 测试用,限制只数
        """
        from db.database import get_conn, query_all
        from updater.checkpoint import CheckpointManager

        today = datetime.now().strftime("%Y-%m-%d")
        cp = CheckpointManager(f"minute_kline_{period}min")

        # 获取需要更新的股票(今日无数据或数据不足的)
        with get_conn() as conn:
            # 优先: 完全没有分钟数据的股票
            rows_missing = query_all("""
                SELECT s.code, s.name FROM stock_list s
                LEFT JOIN kline_minute k ON s.code = k.code
                WHERE k.code IS NULL AND s.is_active = 1
            """)
            # 其次: 分钟数据落后于最近交易日的股票
            rows_outdated = query_all("""
                SELECT s.code, s.name, MAX(k.trade_time) as last_time
                FROM stock_list s
                JOIN kline_minute k ON s.code = k.code
                WHERE s.is_active = 1
                GROUP BY s.code, s.name
                -- HAVING 不能引用 SELECT 列别名,重复聚合表达式,兼容 SQLite/PostgreSQL
                HAVING MAX(k.trade_time) < ?
            """, (today,))

        all_todo = list(rows_missing) + [(r[0], r[1]) for r in rows_outdated]
        # 去重
        seen = set()
        todo = []
        for item in all_todo:
            code = item[0]
            if code not in seen:
                seen.add(code)
                todo.append(item)

        if limit:
            todo = todo[:limit]

        print(f"\n[分钟K线] 共需更新 {len(todo)} 只")
        print(f"  完全缺失: {len(rows_missing)} 只")
        print(f"  数据过期: {len(rows_outdated)} 只")
        if not todo:
            print("  [OK] 分钟K线完整,无需更新")
            return self.stats

        # 重置这些股票的断点
        for code, _ in todo:
            cp_key = f"{code}_{period}"
            cp.completed.discard(cp_key)
        with get_conn() as conn:
            for code, _ in todo:
                conn.execute(
                    f"DELETE FROM {cp.table_name} WHERE code = ?",
                    (f"{code}_{period}",)
                )
        cp.save_snapshot()

        # 调用批量更新(传入具体代码列表)
        original_workers = self.max_workers
        self.max_workers = workers
        target_codes = [c for c, _ in todo]
        result = self.update_minute_all(
            period=period,
            days_back=days_back,
            only_active=True,
            codes=target_codes,
        )
        self.max_workers = original_workers
        return result

    # ---------- 股票列表更新 ----------
    def update_stock_list(self) -> int:
        """更新股票列表(标记退市,保留已有 industry/list_date)"""
        logger.info("[任务] 更新股票列表...")
        try:
            df = self.fetcher.get_stock_list()
            now = datetime.now().isoformat()
            with get_conn() as conn:
                # 标记全部退市
                conn.execute("UPDATE stock_list SET is_active = 0")
                # UPSERT: 保留已有的 industry 和 list_date
                sql = """
                INSERT INTO stock_list
                (code, name, full_code, market, is_active, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    full_code=excluded.full_code,
                    market=excluded.market,
                    is_active=1,
                    updated_at=excluded.updated_at
                """
                rows = [
                    (r.code, r.name, r.full_code, r.market, now)
                    for r in df.itertuples()
                ]
                conn.executemany(sql, rows)
            logger.info(f"  [OK] 共 {len(df)} 只股票")
            return len(df)
        except Exception as e:
            logger.error(f"更新股票列表失败: {e}")
            raise

    # ---------- 指数更新 ----------
    def update_index(self, codes: list = None) -> int:
        """更新主要指数"""
        from updater.indices import KEY_INDEX_CODES
        codes = codes or KEY_INDEX_CODES
        count = 0
        for code in codes:
            try:
                df = self.fetcher.get_index_daily(code)
                if df.empty:
                    continue
                sql = """
                -- ON CONFLICT 语法,兼容 SQLite/PostgreSQL
                INSERT INTO index_daily
                (code, trade_date, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount
                """
                with get_conn() as conn:
                    conn.executemany(sql, [
                        (r.code, r.trade_date, r.open, r.high, r.low,
                         r.close, r.volume,
                         r.amount if hasattr(r, "amount") else None)
                        for r in df.itertuples()
                    ])
                count += 1
            except Exception as e:
                logger.warning(f"指数 {code} 更新失败: {e}")
        logger.info(f"  [OK] 指数 {count}/{len(codes)}")
        return count

    # ---------- 智能检查缺失 ----------
    def check_missing(self) -> dict:
        """
        智能检查数据库中缺失的数据
        返回报告字典,包含各项缺失统计
        """
        from db.database import query_one, query_all
        from datetime import datetime, timedelta

        report = {
            "stock_list": {"missing_count": 0, "details": []},
            "kline_daily": {"missing_stocks": [], "outdated_stocks": []},
            "kline_minute": {"missing_stocks": [], "outdated_stocks": []},
            "index_daily": {"missing": [], "outdated": []},
        }

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        # 5 个交易日前作为过期阈值
        threshold = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        with get_conn() as conn:
            # 1. 股票列表
            db_count = query_one("SELECT COUNT(*) FROM stock_list")[0]
            # 从 AKShare 实时获取市场股票数
            try:
                market_stocks = self.fetcher.get_stock_list()
                market_count = len(market_stocks)
                db_codes = set(r[0] for r in
                               query_all("SELECT code FROM stock_list"))
                market_codes = set(market_stocks['code'].tolist())

                new_stocks = market_codes - db_codes
                delisted = db_codes - market_codes
                report["stock_list"]["market_total"] = market_count
                report["stock_list"]["db_total"] = db_count
                report["stock_list"]["new_count"] = len(new_stocks)
                report["stock_list"]["delisted_count"] = len(delisted)
                report["stock_list"]["new_sample"] = list(new_stocks)[:10]
            except Exception as e:
                report["stock_list"]["error"] = str(e)

            # 2. 日K线缺失检测
            # 2.1 完全没数据的股票
            rows = query_all("""
                SELECT s.code, s.name FROM stock_list s
                LEFT JOIN kline_daily k ON s.code = k.code
                WHERE k.code IS NULL AND s.is_active = 1
            """)
            report["kline_daily"]["missing_stocks"] = [
                (r[0], r[1]) for r in rows
            ]

            # 2.2 数据过期(< 阈值日期)
            rows = query_all("""
                SELECT s.code, s.name, MAX(k.trade_date) as last_date
                FROM stock_list s
                JOIN kline_daily k ON s.code = k.code
                WHERE s.is_active = 1
                GROUP BY s.code, s.name
                -- HAVING 不能引用 SELECT 列别名,重复聚合表达式,兼容 SQLite/PostgreSQL
                HAVING MAX(k.trade_date) < ?
            """, (threshold,))
            report["kline_daily"]["outdated_stocks"] = [
                (r[0], r[1], r[2]) for r in rows
            ]

            # 3. 分时K线检测
            # 3.1 没有分时数据的股票
            rows = query_all("""
                SELECT s.code, s.name FROM stock_list s
                LEFT JOIN kline_minute k ON s.code = k.code
                WHERE k.code IS NULL AND s.is_active = 1
            """)
            report["kline_minute"]["missing_stocks"] = [
                (r[0], r[1]) for r in rows
            ]

            # 3.2 分时数据过期(无今日数据)
            rows = query_all("""
                SELECT s.code, s.name, MAX(k.trade_time) as last_time
                FROM stock_list s
                JOIN kline_minute k ON s.code = k.code
                WHERE s.is_active = 1
                GROUP BY s.code, s.name
                -- HAVING 不能引用 SELECT 列别名,重复聚合表达式,兼容 SQLite/PostgreSQL
                HAVING MAX(k.trade_time) < ?
            """, (yesterday,))
            report["kline_minute"]["outdated_stocks"] = [
                (r[0], r[1], r[2]) for r in rows
            ]

            # 4. 指数检测
            from updater.indices import KEY_INDEX_CODES
            expected_indices = KEY_INDEX_CODES
            for code in expected_indices:
                row = query_one(
                    "SELECT MAX(trade_date), COUNT(*) FROM index_daily WHERE code=?",
                    (code,)
                )
                if row[0] is None:
                    report["index_daily"]["missing"].append(code)
                elif row[0] < threshold:
                    report["index_daily"]["outdated"].append(
                        (code, row[0], row[1])
                    )

        return report

    # ---------- 一键智能更新 ----------
    def update_daily_smart(
        self,
        adjust: str = "qfq",
        minute_period: int = 5,
        minute_days: int = 5,
        daily_days_back: int = None,
        kline_workers: int = None,
        minute_workers: int = None,
        full_init: bool = False,
    ) -> dict:
        """
        一键智能更新 - 自动检查缺失并补齐
        :param adjust: 日K复权方式
        :param minute_period: 分时周期(分钟)
        :param minute_days: 分时回溯天数
        :param daily_days_back: 日K回溯天数(None=用增量)
        :param full_init: 是否全量初始化(覆盖现有)
        """
        from db.database import query_all

        kline_workers = kline_workers or self.max_workers
        minute_workers = minute_workers or max(2, self.max_workers // 2)

        result = {
            "stock_list_updated": 0,
            "index_updated": 0,
            "kline_daily": {},
            "kline_minute": {},
            "skipped": False,
        }

        print(f"\n{'='*60}")
        print(f"  一键智能更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # 1. 检查缺失
        print("\n[1/5] 智能检查数据缺失...")
        report = self.check_missing()

        print(f"  股票列表: 市场 {report['stock_list'].get('market_total', '?')} 只,"
              f"数据库 {report['stock_list'].get('db_total', 0)} 只,"
              f"新增 {report['stock_list'].get('new_count', 0)} 只,"
              f"退市 {report['stock_list'].get('delisted_count', 0)} 只")

        if report['kline_daily']['missing_stocks']:
            print(f"  日K缺失: {len(report['kline_daily']['missing_stocks'])} 只股票无数据")
        if report['kline_daily']['outdated_stocks']:
            print(f"  日K过期: {len(report['kline_daily']['outdated_stocks'])} 只股票需增量更新")
        if report['kline_minute']['missing_stocks']:
            print(f"  分时缺失: {len(report['kline_minute']['missing_stocks'])} 只股票无分时")
        if report['kline_minute']['outdated_stocks']:
            print(f"  分时过期: {len(report['kline_minute']['outdated_stocks'])} 只股票需更新分时")
        if report['index_daily']['missing']:
            print(f"  指数缺失: {report['index_daily']['missing']}")
        if report['index_daily']['outdated']:
            print(f"  指数过期: {len(report['index_daily']['outdated'])} 个")

        # 2. 更新股票列表
        print("\n[2/5] 更新股票列表...")
        result["stock_list_updated"] = self.update_stock_list()

        # 3. 更新指数
        print("\n[3/5] 更新主要指数...")
        result["index_updated"] = self.update_index()

        # 4. 更新日K
        print(f"\n[4/5] 更新日K线 (复权={adjust})...")
        if full_init:
            # 全量初始化
            days = daily_days_back or 1825
            print(f"  全量模式,回溯 {days} 天")
            original_workers = self.max_workers
            self.max_workers = kline_workers
            kline_result = self.update_all(
                adjust=adjust, days_back=days, only_active=True
            )
            self.max_workers = original_workers
        else:
            # 智能模式:只处理缺失和过期
            missing = report['kline_daily']['missing_stocks']
            outdated = report['kline_daily']['outdated_stocks']
            if not missing and not outdated:
                print("  [OK] 日K线完整,无需更新")
                kline_result = {"success": 0, "failed": 0, "rows": 0, "skipped": True}
            else:
                # 重置这些股票的断点
                cp = CheckpointManager("daily_kline")
                target_codes = set()
                for code, _ in missing:
                    target_codes.add(code)
                for code, _, _ in outdated:
                    target_codes.add(code)
                for code in target_codes:
                    cp.completed.discard(code)
                with get_conn() as conn:
                    for code in target_codes:
                        conn.execute(
                            f"DELETE FROM {cp.table_name} WHERE code = ?",
                            (code,)
                        )
                cp.save_snapshot()
                print(f"  缺失 {len(missing)} 只 + 过期 {len(outdated)} 只,"
                      f"将处理 {len(target_codes)} 只")

                # 全量回溯
                days = daily_days_back or 1825
                original_workers = self.max_workers
                self.max_workers = kline_workers
                kline_result = self.update_all(
                    adjust=adjust, days_back=days, only_active=True
                )
                self.max_workers = original_workers

        result["kline_daily"] = kline_result

        # 5. 更新分时
        print(f"\n[5/5] 更新分时K线 (周期={minute_period}min, 回溯 {minute_days} 天)...")
        self.max_workers = minute_workers
        minute_result = self.update_minute_all(
            period=minute_period,
            days_back=minute_days,
            only_active=True,
        )
        self.max_workers = original_workers
        result["kline_minute"] = minute_result

        # 总结
        print(f"\n{'='*60}")
        print(f"  [OK] 一键更新完成")
        print(f"{'='*60}")
        print(f"  股票列表:  +{result['stock_list_updated']} 只")
        print(f"  指数:      +{result['index_updated']} 个")
        print(f"  日K:       成功 {kline_result.get('success', 0)},"
              f" 失败 {kline_result.get('failed', 0)},"
              f" 写入 {kline_result.get('rows', 0)} 行")
        print(f"  分时:      成功 {minute_result.get('success', 0)},"
              f" 失败 {minute_result.get('failed', 0)},"
              f" 写入 {minute_result.get('rows', 0)} 行")

        return result

    # ---------- 分钟K线更新 ----------
    def _minute_worker(
        self, code: str, name: str,
        period: int, days_back: int
    ) -> int:
        """单只股票分时拉取"""
        # 断点:以 (code, period) 为粒度
        cp_key = f"{code}_{period}"
        if not self.minute_checkpoint.need_retry(cp_key):
            with self.stats_lock:
                self.stats["skipped"] += 1
            return 0

        if self.interrupted:
            return 0

        # 拉取
        with self.fetch_sem:
            if self.interrupted:
                return 0
            try:
                end = datetime.now().strftime("%Y-%m-%d")
                start = (datetime.now() -
                         timedelta(days=days_back)).strftime("%Y-%m-%d")
                df = fetcher_manager.get_minute_kline(
                    code, period=period,
                    start_date=start, end_date=end
                )
            except Exception as e:
                self.minute_checkpoint.mark_failed(cp_key, str(e))
                with self.stats_lock:
                    self.stats["failed"] += 1
                return 0

        if df is None or df.empty:
            self.minute_checkpoint.mark_success(cp_key, 0)
            with self.stats_lock:
                self.stats["empty"] += 1
            return 0

        # 写入
        try:
            sql = """
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
            rows = [
                (r.code, r.trade_time, period,
                 r.open, r.high, r.low, r.close,
                 r.volume, r.amount,
                 datetime.now().isoformat())
                for r in df.itertuples()
            ]
            executemany(sql, rows)
            self.minute_checkpoint.mark_success(cp_key, len(rows))
            with self.stats_lock:
                self.stats["success"] += 1
                self.stats["rows"] += len(rows)
            return len(rows)
        except Exception as e:
            self.minute_checkpoint.mark_failed(cp_key, str(e))
            with self.stats_lock:
                self.stats["failed"] += 1
            return 0

    def update_minute_all(
        self,
        period: int = 5,
        only_active: bool = True,
        days_back: int = 30,
        limit: int = None,
        codes: list = None,
    ) -> dict:
        """
        批量更新分钟 K线
        :param period: 1/5/15/30/60
        :param days_back: 拉取最近 N 天(AKShare 限制约 1-2 个月)
        :param limit: 只拉取前 N 只股票(测试用),None 表示全部
        :param codes: 指定股票代码列表,优先级高于 limit
        """
        from updater.checkpoint import CheckpointManager
        self.minute_checkpoint = CheckpointManager(
            f"minute_kline_{period}min"
        )

        if codes:
            with get_conn() as conn:
                placeholders = ",".join("?" * len(codes))
                all_stocks = conn.execute(
                    f"SELECT code, name FROM stock_list WHERE code IN ({placeholders})",
                    codes,
                ).fetchall()
            logger.info(f"[分时] 指定 {len(codes)} 只股票,实际找到 {len(all_stocks)} 只")
        else:
            with get_conn() as conn:
                sql = "SELECT code, name FROM stock_list"
                if only_active:
                    sql += " WHERE is_active = 1"
                all_stocks = conn.execute(sql).fetchall()

            if limit:
                all_stocks = all_stocks[:limit]
                logger.info(f"[分时] 测试模式,仅处理前 {limit} 只")

        logger.info(
            f"[分时] 目标 {len(all_stocks)} 只,周期 {period}min,"
            f"回溯 {days_back} 天"
        )

        # 过滤已完成
        todo = [(c, n) for c, n in all_stocks
                if self.minute_checkpoint.need_retry(f"{c}_{period}")]
        logger.info(
            f"[分时] 待处理 {len(todo)},"
            f"已完成 {len(all_stocks) - len(todo)}"
        )
        if not todo:
            logger.info("[OK] 全部完成,无需处理")
            return self.stats

        # 并行拉取
        try:
            with ThreadPoolExecutor(
                max_workers=self.max_workers, thread_name_prefix="MinWorker"
            ) as pool:
                futures = {
                    pool.submit(self._minute_worker, c, n,
                                period, days_back): (c, n)
                    for c, n in todo
                }
                done = 0
                for fut in as_completed(futures):
                    if self.interrupted:
                        break
                    done += 1
                    try:
                        fut.result()
                    except Exception as e:
                        logger.error(f"分时 Worker 异常: {e}")
                    if done % 200 == 0 or done == len(todo):
                        with self.stats_lock:
                            s = dict(self.stats)
                        logger.info(
                            f"  进度 {done}/{len(todo)} | "
                            f"成功 {s['success']} 失败 {s['failed']} "
                            f"写入 {s['rows']} 行"
                        )
        finally:
            self.minute_checkpoint.save_snapshot()

        logger.info(f"[分时完成] {self.stats}")
        return self.stats

    # ---------- 智能增量日K更新(只处理缺失和过期) ----------
    def update_daily_smart_only(
        self,
        adjust: str = "qfq",
        days_back: int = 10,
        codes: list = None,
        since_list_date: bool = False,
        progress_callback=None,
    ) -> dict:
        """仅对缺失/过期的股票更新日K线
        :param codes: 限定到这些代码;为 None 时处理所有缺失/过期
        :param since_list_date: 是否按 list_date 拉取单股历史
        :param progress_callback: 透传给 update_all 的真实进度回调
        """
        report = self.check_missing()
        missing = report['kline_daily']['missing_stocks']
        outdated = report['kline_daily']['outdated_stocks']

        # 限定到指定代码
        if codes:
            cs = set(codes)
            missing = [(c, n) for c, n in missing if c in cs]
            outdated = [(c, n, d) for c, n, d in outdated if c in cs]

        if not missing and not outdated:
            print("  [OK] 日K线完整,无需更新")
            return {"success": 0, "failed": 0, "rows": 0, "skipped": "all_done"}

        # 重置这些股票的断点(让其重新拉取)
        cp = CheckpointManager("daily_kline")
        for code, name in missing + [(c, n) for c, n, _ in outdated]:
            # 从内存和DB中移除(强制重新拉取)
            cp.completed.discard(code)
            with get_conn() as conn:
                conn.execute(
                    f"DELETE FROM {cp.table_name} WHERE code = ?", (code,)
                )
        cp.save_snapshot()
        print(f"  重置 {len(missing) + len(outdated)} 只股票断点")

        return self.update_all(
            adjust=adjust, days_back=days_back, codes=codes,
            since_list_date=since_list_date,
            progress_callback=progress_callback,
        )
