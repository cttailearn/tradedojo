"""
Baostock 数据源实现

特点:
- 免费,无需注册/token
- 专注 A 股,数据准确度高
- 底层 baostock.com(证券宝)
- 注意:Baostock 没有行业板块批量接口(只能单股查 industry)

API 速查:
- bs.login() / bs.logout()
- bs.query_stock_basic()        -> 股票基本信息(含 industry, list_date)
- bs.query_history_k_data_plus() -> 日 K 线
- adjustflag: 1=后复权, 2=前复权, 3=不复权
"""
import logging
import time
import threading
from typing import Optional

import pandas as pd
try:
    from config import FetchConfig
except Exception:  # 兜底, 避免非标准运行环境下导入失败
    class FetchConfig:
        RETRY_TIMES = 5
        RETRY_BACKOFF = 3.0

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# 延迟导入(允许 baostock 未安装时其他源仍可工作)
try:
    import baostock as bs
    _HAS_BAOSTOCK = True
    _BS_LOGGED_IN = False  # 模块级登录状态
except ImportError:
    bs = None
    _HAS_BAOSTOCK = False
    _BS_LOGGED_IN = False
    logger.warning("[Baostock] 包未安装,此数据源不可用")


# 串行化 baostock 的全部网络调用。
# 原因: baostock 公共会话基于单条长连接, 不支持多线程并发查询;
# 多个线程同时 bs.query_* 会互相打断 socket 读取, 触发"网络接收错误"。
# 用全局可重入锁保证同一时刻只有一个线程访问 baostock 会话。
_BS_LOCK = threading.RLock()
_BS_LAST_QUERY_TS = 0.0
_BS_MIN_INTERVAL = 0.12  # 两次请求最小间隔(秒), 规避服务端限流


def _is_network_error(msg: str) -> bool:
    """判断 baostock 错误是否为网络/连接类(需重置会话重试)"""
    if not msg:
        return False
    m = msg.lower()
    return any(k in m for k in (
        "网络", "network", "连接", "connection",
        "超时", "timeout", "recv", "socket", "断开", "reset",
    ))


# 复权方式映射
_ADJUST_FLAG = {
    "qfq": "2",   # 前复权
    "hfq": "1",   # 后复权
    "":    "3",   # 不复权
    "none": "3",
}

# 指数代码映射(baostock 指数代码格式)
_INDEX_CODE_MAP = {
    "sh000001": "sh.000001",
    "sh000300": "sh.000300",
    "sh000016": "sh.000016",
    "sz399001": "sz.399001",
    "sz399006": "sz.399006",
}


class BaostockFetcher(BaseFetcher):
    """Baostock 数据源"""

    def __init__(self):
        self._logged_in = False

    @property
    def source_name(self) -> str:
        return "baostock"

    @property
    def requires_token(self) -> bool:
        return False

    def _ensure_login(self) -> bool:
        """确保 baostock 已登录"""
        global _BS_LOGGED_IN  # 函数内有赋值,需声明为模块级,否则报 UnboundLocalError
        if not _HAS_BAOSTOCK:
            return False
        if _BS_LOGGED_IN and self._logged_in:
            return True
        try:
            lg = bs.login()
            if lg.error_code == "0":
                _BS_LOGGED_IN = True
                self._logged_in = True
                logger.info("[Baostock] 登录成功")
                return True
            logger.error(f"[Baostock] 登录失败: {lg.error_msg}")
            return False
        except Exception as e:
            logger.error(f"[Baostock] 登录异常: {e}")
            return False

    def _reset_login(self) -> None:
        """使登录态失效(会话断开/网络错误后调用, 下次查询会重新登录)"""
        global _BS_LOGGED_IN
        with _BS_LOCK:
            if _BS_LOGGED_IN and _HAS_BAOSTOCK:
                try:
                    bs.logout()
                except Exception:
                    pass
            _BS_LOGGED_IN = False
            self._logged_in = False

    def _run_query(self, query_fn):
        """执行 baostock 查询: 串行化 + 限流 + 失败自动重登录重试。

        query_fn: 无参 callable, 返回 baostock ResultData。
        返回: ResultData(成功或业务错误); 重试耗尽仍失败返回 None。
        """
        global _BS_LAST_QUERY_TS
        last_err = ""
        for attempt in range(FetchConfig.RETRY_TIMES):
            rs = None
            need_retry = False
            with _BS_LOCK:
                # 限流: 两次请求间最小间隔, 规避服务端限流
                wait = _BS_MIN_INTERVAL - (time.monotonic() - _BS_LAST_QUERY_TS)
                if wait > 0:
                    time.sleep(wait)
                if not self._ensure_login():
                    logger.warning(f"[Baostock] 第 {attempt+1} 次登录失败, 退避重试")
                    need_retry = True
                else:
                    try:
                        rs = query_fn()
                    except Exception as e:
                        last_err = f"异常: {e}"
                        logger.warning(f"[Baostock] 查询异常(第 {attempt+1} 次): {e}")
                        self._reset_login()
                        need_retry = True
                    else:
                        _BS_LAST_QUERY_TS = time.monotonic()
                        if rs.error_code != "0":
                            last_err = rs.error_msg
                            if _is_network_error(rs.error_msg):
                                logger.warning(
                                    f"[Baostock] 网络错误(第 {attempt+1} 次): "
                                    f"{rs.error_msg}, 重置会话后重试"
                                )
                                self._reset_login()
                                need_retry = True
                            # 业务错误 -> 直接返回, 不重试
            if not need_retry:
                return rs
            time.sleep(FetchConfig.RETRY_BACKOFF * (attempt + 1))
        logger.error(f"[Baostock] 查询重试 {FetchConfig.RETRY_TIMES} 次后仍失败: {last_err}")
        return None

    def is_available(self) -> bool:
        return _HAS_BAOSTOCK

    # ---------- 1. 股票列表 ----------
    def get_stock_list(self) -> pd.DataFrame:
        if not _HAS_BAOSTOCK:
            return pd.DataFrame()
        with _BS_LOCK:
            if not self._ensure_login():
                return pd.DataFrame()
            rs = bs.query_stock_basic()
            if rs.error_code != "0":
                logger.error(f"[Baostock] query_stock_basic 失败: {rs.error_msg}")
                return pd.DataFrame()
            raw_rows = []
            while rs.next():
                raw_rows.append(rs.get_row_data())

        rows = []
        for row in raw_rows:
            # 字段: code, code_name, ipoDate, outDate, type, status
            code, name, ipo_date, out_date, stock_type, status = row[:6]
            if status != "1":  # 1=在市
                continue
            if stock_type not in ("1", "2"):  # 1=股票, 2=指数
                continue
            # code 格式: sh.600000 -> 取数字部分
            code_num = code.split(".")[-1]
            market = code.split(".")[0]
            rows.append({
                "code": code_num,
                "name": name,
                "market": market,
                "full_code": code,
                "is_active": 1,
                "industry": "",  # 留空,enrich 阶段填充
                "list_date": ipo_date.replace("-", "") if ipo_date else "",
            })
        df = pd.DataFrame(rows)
        logger.info(f"[Baostock] 获取股票列表 {len(df)} 只")
        return df

    # ---------- 2. 日 K 线 ----------
    def get_daily_kline(
        self,
        code: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        if not self._ensure_login():
            return pd.DataFrame()

        # code 转 baostock 格式: 000001 -> sh.000001 或 sz.000001
        if "." not in code:
            if code.startswith(("60", "68", "90", "11", "13")):
                bs_code = f"sh.{code}"
            elif code.startswith(("00", "30", "20", "12", "15")):
                bs_code = f"sz.{code}"
            elif code.startswith(("43", "83", "87", "92")):
                bs_code = f"bj.{code}"
            else:
                bs_code = f"sh.{code}"
        else:
            bs_code = code

        adjustflag = _ADJUST_FLAG.get(adjust, "2")
        # baostock 要求 YYYY-MM-DD 格式(带横线),旧代码误去横线导致"日期格式不正确"
        start = start_date
        end = end_date

        rs = self._run_query(lambda: bs.query_history_k_data_plus(
            bs_code,
            # baostock 没有 change 字段,用 close - preclose 现场算
            "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg",
            start_date=start, end_date=end,
            frequency="d", adjustflag=adjustflag,
        ))
        if rs is None:
            logger.warning(f"[Baostock] {bs_code} 日K 获取失败(重试耗尽)")
            return pd.DataFrame()
        if rs.error_code != "0":
            logger.warning(f"[Baostock] {bs_code} 日K 失败: {rs.error_msg}")
            return pd.DataFrame()

        rows = []
        while rs.next():
            r = rs.get_row_data()
            date, o, h, l, c, pc, vol, amt, tr, status, pct = r[:11]
            if status not in ("1",):  # 只取交易日
                continue
            close_f = float(c) if c else None
            pre_close_f = float(pc) if pc else None
            change_amt = (
                (close_f - pre_close_f) if (close_f is not None and pre_close_f is not None) else None
            )
            rows.append({
                "code": code,
                "trade_date": date,
                "open": float(o) if o else None,
                "high": float(h) if h else None,
                "low": float(l) if l else None,
                "close": close_f,
                "pre_close": pre_close_f,
                "change_amount": change_amt,
                "pct_change": float(pct) if pct else None,
                "volume": int(float(vol)) if vol else 0,
                "amount": float(amt) if amt else None,
                "turnover_rate": float(tr) if tr else None,
                "adjust_type": adjust if adjust else "none",
            })
        return pd.DataFrame(rows)

    # ---------- 3. 指数 ----------
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        if not self._ensure_login():
            return pd.DataFrame()
        bs_code = _INDEX_CODE_MAP.get(code, code.replace("000001", ".000001"))
        if "." not in bs_code:
            bs_code = bs_code[:2] + "." + bs_code[2:]

        rs = self._run_query(lambda: bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date="2020-01-01", end_date="2099-12-31",
            frequency="d", adjustflag="3",
        ))
        if rs is None:
            return pd.DataFrame()
        if rs.error_code != "0":
            return pd.DataFrame()

        rows = []
        while rs.next():
            r = rs.get_row_data()
            date, o, h, l, c, vol, amt = r[:7]
            rows.append({
                "code": code,
                "trade_date": date,
                "open": float(o) if o else None,
                "high": float(h) if h else None,
                "low": float(l) if l else None,
                "close": float(c) if c else None,
                "volume": int(float(vol)) if vol else 0,
                "amount": float(amt) if amt else None,
            })
        return pd.DataFrame(rows)

    # ---------- 4. 个股信息(含行业/上市日期) ----------
    def get_stock_profile(self, code: str) -> Optional[dict]:
        """从 stock_basic 直接拿,免去单股 API 调用"""
        if not self._ensure_login():
            return None
        # code 转 baostock 格式
        if "." not in code:
            if code.startswith(("60", "68", "90", "11", "13")):
                bs_code = f"sh.{code}"
            elif code.startswith(("00", "30", "20", "12", "15")):
                bs_code = f"sz.{code}"
            else:
                bs_code = f"bj.{code}"
        else:
            bs_code = code
        rs = self._run_query(lambda: bs.query_stock_basic(code=bs_code))
        if rs is None or rs.error_code != "0":
            return None
        if rs.next():
            r = rs.get_row_data()
            code_full, name, ipo_date, out_date, stock_type, status = r[:6]
            return {
                "industry": "",  # baostock 不直接给行业
                "list_date": ipo_date,
                "company_name": name,
            }
        return None