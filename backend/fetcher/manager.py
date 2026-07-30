"""
FetcherManager —— 统一入口,自动 failover + 自动切换主源

设计:
- 主源 + 备选源列表
- 调用时先试主源,失败按顺序 failover
- 记录每个源的可用状态(连续失败次数 / 累计成功次数)
- 连续失败 ≥ 阈值 → 自动切换主源(避免反复浪费时间重试)
- 主源恢复后 → 累计成功 ≥ 阈值 → 自动切回
"""
import logging
import threading
import time
from typing import Optional, List, Dict

import pandas as pd

from .base import BaseFetcher

logger = logging.getLogger("fetcher.manager")

# 自动切换主源的阈值
_AUTO_SWITCH_FAIL_THRESHOLD = 3      # 连续失败 N 次 → 切到备选
_AUTO_SWITCH_RECOVER_THRESHOLD = 5  # 累计成功 N 次 → 切回主源


class FetcherManager:
    """多数据源管理器(单例)"""

    def __init__(self):
        self._lock = threading.Lock()
        self._primary: Optional[str] = None
        self._preferred: Optional[str] = None  # 用户配置的"理想主源",用于自动切回
        self._fetchers: Dict[str, BaseFetcher] = {}
        self._stats: Dict[str, Dict] = {}  # source -> {success, failed, last_used, last_error, consecutive_fail}
        self._init_fetchers()

    def _init_fetchers(self):
        """初始化所有可用的 fetcher"""
        from fetcher.data_fetcher import AKShareFetcher
        from fetcher.baostock_fetcher import BaostockFetcher
        from fetcher.tushare_fetcher import TushareFetcher

        candidates = [
            ("akshare", AKShareFetcher()),
            ("baostock", BaostockFetcher()),
            ("tushare", TushareFetcher()),
        ]

        for name, fetcher in candidates:
            if fetcher.is_available():
                self._fetchers[name] = fetcher
                self._stats[name] = {
                    "success": 0, "failed": 0,
                    "consecutive_fail": 0,
                    "last_used": None, "last_error": None,
                }
                logger.info(f"[FetcherManager] 注册数据源: {name}")
            else:
                reason = "包未安装" if name != "tushare" else "未配置 TUSHARE_TOKEN"
                logger.info(f"[FetcherManager] 跳过 {name}: {reason}")

        # 默认主源:baostock > akshare > tushare
        # 优先 baostock:免注册、稳定、不限速、含换手率。
        # akshare 作为 fallback(东方财富限流时切过来)。
        for name in ("baostock", "akshare", "tushare"):
            if name in self._fetchers:
                self._preferred = name
                self._primary = name
                break

    # ---------- 状态查询 ----------
    def list_sources(self) -> List[dict]:
        """列出所有数据源及其状态"""
        result = []
        for name, fetcher in self._fetchers.items():
            stats = self._stats[name]
            result.append({
                "name": name,
                "is_primary": name == self._primary,
                "is_preferred": name == self._preferred,
                "requires_token": fetcher.requires_token,
                "success": stats["success"],
                "failed": stats["failed"],
                "consecutive_fail": stats["consecutive_fail"],
                "last_used": stats["last_used"],
                "last_error": stats["last_error"],
            })
        return result

    def get_primary(self) -> str:
        return self._primary

    def set_primary(self, name: str) -> bool:
        """切换主源(同时更新 preferred,以便自动切回)"""
        with self._lock:
            if name not in self._fetchers:
                logger.error(f"[FetcherManager] 未知数据源: {name}")
                return False
            self._primary = name
            self._preferred = name
            self._reset_consecutive_fail(name)
            logger.info(f"[FetcherManager] 主源切换为: {name}")
            return True

    def get_fetcher(self, name: Optional[str] = None) -> Optional[BaseFetcher]:
        """获取指定(或主)数据源实例"""
        return self._fetchers.get(name or self._primary)

    # ---------- 自动主源切换 ----------
    def _reset_consecutive_fail(self, name: str):
        with self._lock:
            if name in self._stats:
                self._stats[name]["consecutive_fail"] = 0

    def _on_success(self, name: str):
        """记录成功,可能触发自动切回 preferred"""
        with self._lock:
            s = self._stats[name]
            s["success"] += 1
            s["last_used"] = time.time()
            s["last_error"] = None
            s["consecutive_fail"] = 0

        # 当前不是 preferred,且本源连续成功 >= 阈值 → 切回
        if (self._primary != self._preferred
                and name == self._preferred
                and self._stats[name]["success"] >= _AUTO_SWITCH_RECOVER_THRESHOLD
                and self._stats[name]["success"] % _AUTO_SWITCH_RECOVER_THRESHOLD == 0):
            logger.info(
                f"[FetcherManager] 自动切回主源 {self._preferred} "
                f"(连续成功 {self._stats[name]['success']} 次)"
            )
            with self._lock:
                self._primary = self._preferred

    def _on_failure(self, name: str, err: str) -> bool:
        """记录失败。返回 True 表示已自动切换主源。"""
        with self._lock:
            s = self._stats[name]
            s["failed"] += 1
            s["last_used"] = time.time()
            s["last_error"] = err
            s["consecutive_fail"] += 1
            cf = s["consecutive_fail"]

        # 当前主源连续失败 >= 阈值,且有备选源 → 切走
        if (name == self._primary
                and cf >= _AUTO_SWITCH_FAIL_THRESHOLD
                and name == self._primary):  # 双保险
            backup = next(
                (n for n in self._fetchers if n != name),
                None,
            )
            if backup:
                logger.warning(
                    f"[FetcherManager] 主源 {name} 连续失败 {cf} 次, "
                    f"自动切换到 {backup}"
                )
                with self._lock:
                    self._primary = backup
                return True
        return False

    # ---------- 测试连通性 ----------
    def test_source(self, name: str) -> dict:
        """测试某个源的连通性(轻量)"""
        fetcher = self._fetchers.get(name)
        if not fetcher:
            return {"name": name, "available": False, "error": "数据源未注册"}

        t0 = time.time()
        try:
            df = fetcher.get_stock_list()
            elapsed = time.time() - t0
            ok = df is not None and not df.empty
            return {
                "name": name,
                "available": ok,
                "rows": len(df) if df is not None else 0,
                "elapsed_ms": round(elapsed * 1000),
                "error": None if ok else "返回空数据",
            }
        except Exception as e:
            elapsed = time.time() - t0
            return {
                "name": name,
                "available": False,
                "elapsed_ms": round(elapsed * 1000),
                "error": f"{type(e).__name__}: {str(e)[:100]}",
            }

    # ---------- 统一入口(带 failover) ----------
    def _call_with_failover(self, method_name: str, *args, **kwargs):
        """按顺序尝试主源 + 所有备选源,直到成功。

        主源失败会即时切换到备选源(不等重试耗尽),
        单只股票请求级别就生效,避免浪费时间在已挂的主源上。
        """
        # 优先顺序:主源 -> 其他源
        ordered = [self._primary]
        ordered.extend(n for n in self._fetchers if n != self._primary)
        ordered = [n for n in ordered if n in self._fetchers]  # 过滤

        last_error = None
        for idx, name in enumerate(ordered):
            fetcher = self._fetchers[name]
            t0 = time.time()
            try:
                method = getattr(fetcher, method_name)
                result = method(*args, **kwargs)
                self._on_success(name)
                if idx > 0 or name != self._preferred:
                    logger.info(f"[FetcherManager] 调用 {method_name} 由 {name} 完成")
                return result
            except Exception as e:
                last_error = e
                err = f"{type(e).__name__}: {str(e)[:80]}"
                self._on_failure(name, err)
                logger.warning(
                    f"[FetcherManager] {name}.{method_name} 失败, "
                    f"尝试下一个源。错误: {e}"
                )

        raise RuntimeError(
            f"所有数据源调用 {method_name} 均失败。最后错误: {last_error}"
        )

    def get_stock_list(self) -> pd.DataFrame:
        return self._call_with_failover("get_stock_list")

    def get_daily_kline(
        self, code: str, start_date: str, end_date: str, adjust: str = "qfq"
    ) -> pd.DataFrame:
        return self._call_with_failover(
            "get_daily_kline", code, start_date, end_date, adjust
        )

    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        return self._call_with_failover("get_index_daily", code)

    def get_stock_profile(self, code: str) -> Optional[dict]:
        return self._call_with_failover("get_stock_profile", code)

    def get_industry_map(self) -> dict:
        return self._call_with_failover("get_industry_map")


# 全局单例
fetcher_manager = FetcherManager()