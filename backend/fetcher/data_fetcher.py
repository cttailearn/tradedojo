"""
AKShare 数据获取封装
- 自动重试 + 指数退避(带抖动)
- 统一字段命名
- 请求间隔限流(进程级全局,多 worker 共享)

继承 BaseFetcher 以纳入多数据源架构
"""
import random
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import akshare as ak

from config import FetchConfig
from fetcher.base import BaseFetcher

logger = logging.getLogger(__name__)


# 瞬时错误关键字(检测到就重试)
_TRANSIENT_KEYWORDS = (
    "RemoteDisconnected",
    "Connection aborted",
    "Connection reset",
    "Timeout",
    "Read timed out",
    "ChunkedEncodingError",
    "BadStatusLine",
)


def _is_transient_error(exc: Exception) -> bool:
    """判断是否为瞬时网络错误(可重试)"""
    name = type(exc).__name__
    msg = str(exc)
    if name in ("RemoteDisconnected", "ConnectionError", "TimeoutError",
                "ConnectionResetError", "ChunkedEncodingError"):
        return True
    return any(kw in msg for kw in _TRANSIENT_KEYWORDS)


# ============================================================
# 进程级全局速率限制器
# 多个 AKShareFetcher 实例共享同一个时间戳 + 锁,
# 即便并行 updater 起 4 个 worker,全局节奏也强制 ≥ REQUEST_INTERVAL。
# ============================================================
class _GlobalRateLimiter:
    """进程内全局速率限制器(线程安全)。"""
    _lock = threading.Lock()
    _last_request_at = 0.0

    @classmethod
    def wait(cls, min_interval: float):
        if min_interval <= 0:
            return
        with cls._lock:
            now = time.time()
            elapsed = now - cls._last_request_at
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            cls._last_request_at = time.time()


# ============================================================
# AKShare 默认 UA 伪装(避免被识别为脚本)
# ============================================================
def _patch_akshare_headers():
    """给 akshare 内部 requests.Session 注入浏览器 UA。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    try:
        # akshare 新版本把 session 暴露在 akshare 模块
        for attr in ("_session", "session", "sess"):
            sess = getattr(ak, attr, None)
            if sess is not None and hasattr(sess, "headers"):
                sess.headers.update(headers)
                logger.debug(f"[Fetcher] 已设置 akshare.{attr} UA")
                return True
        # 备用:遍历模块子模块,找含 session 的
        import akshare as _ak
        for mod_name in dir(_ak):
            obj = getattr(_ak, mod_name, None)
            sess = getattr(obj, "session", None) if obj else None
            if sess and hasattr(sess, "headers"):
                sess.headers.update(headers)
        return True
    except Exception as e:
        logger.debug(f"[Fetcher] 设置 UA 失败(非致命): {e}")
        return False


# 模块加载时执行一次
_patch_akshare_headers()


def _normalize_market(code: str) -> str:
    """根据代码判断市场前缀"""
    if code.startswith(("60", "68", "90", "11", "13")):
        return "sh"
    if code.startswith(("00", "30", "20", "12", "15")):
        return "sz"
    if code.startswith(("43", "83", "87", "92")):
        return "bj"
    return ""


class AKShareFetcher(BaseFetcher):
    """AKShare 数据源统一封装"""

    def __init__(self, max_retry: int = None, sleep_base: float = None,
                 request_interval: float = None):
        self.max_retry = max_retry or FetchConfig.RETRY_TIMES
        self.sleep_base = sleep_base or FetchConfig.RETRY_BACKOFF
        self.jitter = FetchConfig.BACKOFF_JITTER
        self.request_interval = (
            request_interval
            if request_interval is not None
            else FetchConfig.REQUEST_INTERVAL
        )

    @property
    def source_name(self) -> str:
        return "akshare"

    @property
    def requires_token(self) -> bool:
        return False

    def is_available(self) -> bool:
        try:
            import akshare  # noqa
            return True
        except ImportError:
            return False

    # ---------- 内部工具 ----------
    def _throttle(self):
        """请求间隔限流:走进程级全局限流器,多实例/多 worker 共享节奏。"""
        _GlobalRateLimiter.wait(self.request_interval)

    def _retry(self, func, *args, **kwargs):
        """
        带重试的函数调用
        - 指数退避 + 抖动
        - 区分瞬时错误(重试) vs 永久错误(立即失败)
        - 每次重试前节流
        """
        last_exc = None
        for i in range(self.max_retry):
            # 重试前先节流(全局限流器会自动记录时间戳)
            if i > 0:
                self._throttle()
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                last_exc = e
                # 永久错误(如参数错)立即失败
                if not _is_transient_error(e):
                    logger.error(f"[Fetch] 永久错误(不重试): {e}")
                    raise

                wait = self.sleep_base * (i + 1)
                # 加 ±jitter 的随机抖动,避免雷鸣群
                if self.jitter > 0:
                    wait = wait * (1 + random.uniform(-self.jitter, self.jitter))
                    wait = max(0.1, wait)

                logger.warning(
                    f"[Fetch] 第{i+1}/{self.max_retry}次失败 "
                    f"(瞬时): {type(e).__name__}: {str(e)[:80]}, "
                    f"{wait:.1f}s后重试"
                )
                time.sleep(wait)

        raise RuntimeError(f"重试{self.max_retry}次后仍失败: {last_exc}")

    @staticmethod
    def _safe_int(v) -> Optional[int]:
        """安全转 int"""
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return int(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(v) -> Optional[float]:
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return float(v)
        except (ValueError, TypeError):
            return None

    # ---------- 1. 股票列表 ----------
    def get_stock_list(self) -> pd.DataFrame:
        """获取 A 股全市场股票列表"""
        def _fetch():
            df = ak.stock_info_a_code_name()
            return df

        df = self._retry(_fetch)
        # 字段标准化
        df = df.rename(columns={"code": "code", "code_name": "name"})
        df["full_code"] = df["code"].apply(lambda c: _normalize_market(c) + c)
        df["market"] = df["full_code"].str[:2]
        df["is_active"] = 1
        return df[["code", "name", "full_code", "market", "is_active"]]

    # ---------- 2. 日K线 ----------
    def get_daily_kline(
        self,
        code: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> pd.DataFrame:
        """
        获取日K线
        :param code: 股票代码,如 "000001"
        :param start_date: 开始日期 "YYYY-MM-DD"
        :param end_date: 结束日期 "YYYY-MM-DD"
        :param adjust: 复权方式 qfq(前复权)/hfq(后复权)/'' (不复权)
        """
        def _fetch():
            return ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust,
            )

        df = self._retry(_fetch)
        if df is None or df.empty:
            return pd.DataFrame()

        # 字段映射(AKShare 字段名可能变化,做兼容)
        col_map = {
            "日期": "trade_date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "昨收": "pre_close",
            "涨跌额": "change_amount", "涨跌幅": "pct_change",
            "成交量": "volume", "成交额": "amount", "换手率": "turnover_rate",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # 补充字段
        df["code"] = code
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        df["adjust_type"] = adjust if adjust else "none"

        # 安全类型转换
        for col in ["open", "high", "low", "close",
                    "change_amount", "pct_change",
                    "amount", "turnover_rate"]:
            if col in df.columns:
                df[col] = df[col].apply(self._safe_float)
        if "volume" in df.columns:
            df["volume"] = df["volume"].apply(self._safe_int)

        # 处理 pre_close: 优先用 API 返回的"昨收",否则用上日收盘价推算
        if "pre_close" not in df.columns or df["pre_close"].isna().all():
            df = df.sort_values("trade_date").reset_index(drop=True)
            df["pre_close"] = df["close"].shift(1)
        else:
            df["pre_close"] = df["pre_close"].apply(self._safe_float)

        # 保证列齐全
        for col, default in [("pre_close", None), ("change_amount", None),
                             ("pct_change", None), ("turnover_rate", None)]:
            if col not in df.columns:
                df[col] = default

        return df[[
            "code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change_amount", "pct_change", "volume",
            "amount", "turnover_rate", "adjust_type"
        ]]

    # ---------- 3. 分钟K线 ----------
    def get_minute_kline(
        self,
        code: str,
        period: int = 5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取分钟K线
        :param period: 1/5/15/30/60
        :param start_date: 开始日期 "YYYY-MM-DD", None=近1个月
        :param end_date: 结束日期 "YYYY-MM-DD", None=今天
        """
        # 默认值处理
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        def _fetch():
            return ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=str(period),
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )

        df = self._retry(_fetch)
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {
            "时间": "trade_time", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "成交额": "amount",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["code"] = code
        df["period"] = period
        df["trade_time"] = pd.to_datetime(df["trade_time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        df["volume"] = df["volume"].apply(self._safe_int)
        for c in ["open", "high", "low", "close", "amount"]:
            if c in df.columns:
                df[c] = df[c].apply(self._safe_float)

        return df[["code", "trade_time", "period", "open", "high",
                   "low", "close", "volume", "amount"]]

    # ---------- 4. 指数K线 ----------
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        """获取指数日线(默认上证指数)"""
        def _fetch():
            return ak.stock_zh_index_daily(symbol=code)

        df = self._retry(_fetch)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df["trade_date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["code"] = code
        df["volume"] = df["volume"].apply(self._safe_int)
        return df.rename(columns={"close": "close"})[
            ["code", "trade_date", "open", "high", "low",
             "close", "volume", "amount"]
        ] if "amount" in df.columns else df[
            ["code", "trade_date", "open", "high", "low", "close", "volume"]
        ]


    # ---------- 5. 股票信息丰富(行业+上市日期) ----------
    def get_industry_map(self) -> dict:
        """
        从行业板块批量构建 {code: industry_name} 映射
        通过遍历所有申万行业板块获取成分股
        :return: dict, key=股票代码, value=行业名称
        """
        logger.info("[Industry] 开始构建行业映射...")
        try:
            boards_df = self._retry(lambda: ak.stock_board_industry_name_em())
        except Exception as e:
            logger.warning(f"[Industry] 获取行业板块列表失败: {e}")
            return {}

        board_names = boards_df["板块名称"].tolist()
        logger.info(f"[Industry] 共 {len(board_names)} 个行业板块, 开始遍历...")

        industry_map = {}
        fail_count = 0
        for i, board_name in enumerate(board_names):
            try:
                cons_df = self._retry(
                    lambda bn=board_name: ak.stock_board_industry_cons_em(symbol=bn)
                )
                for row in cons_df.itertuples(index=False):
                    code = getattr(row, "代码", "")
                    if code:
                        industry_map[code] = board_name
            except Exception:
                fail_count += 1

            if (i + 1) % 50 == 0:
                logger.info(
                    f"[Industry] 进度 {i+1}/{len(board_names)}, "
                    f"已映射 {len(industry_map)} 只股票, 失败 {fail_count}"
                )

        logger.info(
            f"[Industry] 完成! 映射 {len(industry_map)} 只股票 -> {len(board_names)} 个行业"
        )
        return industry_map

    def get_stock_profile(self, code: str) -> Optional[dict]:
        """
        获取单只股票的详细信息(行业 + 上市日期)
        使用巨潮资讯 profile API
        :return: dict with keys: industry, list_date, company_name 或 None
        """
        try:
            df = self._retry(lambda: ak.stock_profile_cninfo(symbol=code))
            if df is None or df.empty:
                return None
            row = df.iloc[0]
            list_date = row.get("上市日期", None)
            # 标准化日期格式: 可能为 "19910403" 或 "1991-04-03"
            if list_date and isinstance(list_date, str):
                list_date = list_date.replace("-", "")
                if len(list_date) == 8:
                    list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
            return {
                "industry": row.get("所属行业", None),
                "list_date": list_date,
                "company_name": row.get("公司名称", None),
            }
        except Exception as e:
            logger.debug(f"[Profile] {code} 获取失败: {e}")
            return None


# ---------- 单元测试 ----------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    f = AKShareFetcher()
    print("=== 测试股票列表(前 5) ===")
    sl = f.get_stock_list()
    print(sl.head())

    print("\n=== 测试日K线 (000001 平安银行, 最近 30 天) ===")
    end = datetime.now().strftime("%Y-%m-%d")
    from datetime import timedelta
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    k = f.get_daily_kline("000001", start, end, "qfq")
    print(k.tail())
    print(f"共 {len(k)} 条")
