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
from concurrent.futures import ThreadPoolExecutor
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

# 单次 baostock 查询/读取的超时(秒)。
# baostock 是同步阻塞客户端, 网络异常时 recv 可能永久挂起;
# 通过"独立线程执行 + 限时等待"兜底, 避免整个任务被卡死。
_BS_QUERY_TIMEOUT = 30.0

# 供超时执行复用的线程池(单工作线程, 配合 _BS_LOCK 天然串行)
_BS_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="BaostockIO")


def _is_network_error(msg: str) -> bool:
    """判断 baostock 错误是否为网络/连接类(需重置会话重试)"""
    if not msg:
        return False
    m = msg.lower()
    return any(k in m for k in (
        "网络", "network", "连接", "connection",
        "超时", "timeout", "recv", "socket", "断开", "reset",
        # 2026-08-05: baostock 海外访问常见 zlib 解压错误(数据包损坏)
        "decompress", "解压", "接收数据异常", "invalid distance", "error -3",
    ))


def _iter_rows(rs):
    """安全遍历 baostock ResultData(zlib 解压错误会在此抛出, 由 read_fn 捕获)"""
    while rs.next():
        yield rs.get_row_data()


def _result_empty(result) -> bool:
    """判断 read_fn 结果为"空"(可能因 baostock 连接异常静默返回)。"""
    try:
        if result is None:
            return True
        if hasattr(result, "__len__"):
            return len(result) == 0
        if hasattr(result, "empty"):  # DataFrame
            return bool(result.empty)
    except Exception:
        pass
    return False


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
    "sh000905": "sh.000905",
    "sh000688": "sh.000688",
    "sh000016": "sh.000016",
    "sz399001": "sz.399001",
    "sz399006": "sz.399006",
}


class BaostockFetcher(BaseFetcher):
    """Baostock 数据源"""

    def __init__(self):
        self._logged_in = False
        self._last_login_attempt = 0.0  # 登录冷却时间戳(monotonic)

    @property
    def source_name(self) -> str:
        return "baostock"

    @property
    def requires_token(self) -> bool:
        return False

    # 登录失败冷却(秒): baostock 不可达时避免每次查询都尝试重连
    _LOGIN_COOLDOWN = 60.0

    def _ensure_login(self) -> bool:
        """确保 baostock 已登录。

        2026-08-12 加固:
        - login 走 _BS_EXECUTOR 限时等待(socket 默认无超时, connect 到
          不可达 IP 会挂很久; 库 send_msg 已加 recv 超时, 这里再兜底)。
        - 失败后进入 60s 冷却, 避免查询风暴; 冷却期内直接返回 False,
          让 FetcherManager 快速 failover 到其他数据源。
        """
        global _BS_LOGGED_IN  # 函数内有赋值,需声明为模块级,否则报 UnboundLocalError
        if not _HAS_BAOSTOCK:
            return False
        if _BS_LOGGED_IN and self._logged_in:
            return True
        # 冷却检查
        now = time.monotonic()
        if now - self._last_login_attempt < self._LOGIN_COOLDOWN:
            return False
        self._last_login_attempt = now
        try:
            # login 限时: 超过 _BS_QUERY_TIMEOUT 视为失败(含 connect/recv 挂起)
            fut = _BS_EXECUTOR.submit(bs.login)
            lg = fut.result(timeout=_BS_QUERY_TIMEOUT)
            if lg.error_code == "0":
                _BS_LOGGED_IN = True
                self._logged_in = True
                logger.info("[Baostock] 登录成功")
                return True
            logger.error(f"[Baostock] 登录失败: {lg.error_msg}")
            return False
        except Exception as e:
            logger.warning(f"[Baostock] 登录异常/超时: {e}; 冷却 {self._LOGIN_COOLDOWN:.0f}s")
            self._reset_login()
            return False

    def _reset_login(self) -> None:
        """使登录态失效(会话断开/网络错误后调用, 下次查询会重新登录)。

        2026-08-12: 不再调用 bs.logout()。
        logout 内部先 send_msg 再关 socket; baostock 服务器不可达时,
        send_msg 即使有超时也占用 _BS_LOCK 数秒, 阻塞所有查询线程。
        改为直接关闭底层 socket + 重置状态, 由下次 _ensure_login 重新建连。
        """
        global _BS_LOGGED_IN
        with _BS_LOCK:
            if _HAS_BAOSTOCK:
                try:
                    import baostock.common.context as _bs_ctx
                    sock = getattr(_bs_ctx, "default_socket", None)
                    if sock is not None:
                        try:
                            sock.close()
                        except Exception:
                            pass
                        setattr(_bs_ctx, "default_socket", None)
                except Exception:
                    pass
            _BS_LOGGED_IN = False
            self._logged_in = False

    def _run_query(self, query_fn, read_fn=None, timeout: float = _BS_QUERY_TIMEOUT):
        """执行 baostock 查询: 串行化 + 限流 + 超时兜底 + 失败自动重登录重试。

        query_fn: 无参 callable, 返回 baostock ResultData。
        read_fn:  可选; 在查询成功后于同一执行线程内消费 ResultData
                  (rs.next()/get_row_data() 循环), 返回业务结果。
                  baostock 的 zlib 解压错误发生在读取阶段, 必须纳入超时保护。
        返回: read_fn 结果; 未提供 read_fn 时返回 ResultData(或业务错误);
              重试耗尽仍失败返回 None。
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
                        # 独立线程执行, 主线程限时等待:
                        # baostock 同步客户端在 socket 异常时可能永久阻塞,
                        # 超时后重置会话, 避免全局锁被挂起线程长期占用。
                        fut = _BS_EXECUTOR.submit(self._query_with_read, query_fn, read_fn)
                        result = fut.result(timeout=timeout)
                    except Exception as e:
                        last_err = f"超时/异常: {e}"
                        logger.warning(
                            f"[Baostock] 查询超时或异常(第 {attempt+1} 次, "
                            f"{timeout:.0f}s): {e}; 重置会话后重试"
                        )
                        self._reset_login()
                        need_retry = True
                    else:
                        _BS_LAST_QUERY_TS = time.monotonic()
                        if isinstance(result, Exception):
                            # query/read 阶段抛出的异常(含 zlib 解压错误)
                            last_err = f"异常: {result}"
                            logger.warning(
                                f"[Baostock] 查询/读取异常(第 {attempt+1} 次): {result}; "
                                f"重置会话后重试"
                            )
                            self._reset_login()
                            need_retry = True
                        elif result is not None and getattr(result, "error_code", "0") != "0":
                            last_err = result.error_msg
                            if _is_network_error(result.error_msg):
                                logger.warning(
                                    f"[Baostock] 网络错误(第 {attempt+1} 次): "
                                    f"{result.error_msg}, 重置会话后重试"
                                )
                                self._reset_login()
                                need_retry = True
                            # 业务错误 -> 直接返回, 不重试
                        else:
                            # read_fn 结果为空时, 视为网络异常静默(baostock send_msg
                            # 失败只打印并返回 None, rs.next() 返回 False, 不抛异常)。
                            # 仅在首次尝试时重试一次(避免把停牌/真无数据当异常反复重试)
                            if (read_fn is not None and attempt == 0
                                    and _result_empty(result)):
                                last_err = "空结果(疑似连接异常静默)"
                                logger.warning(
                                    "[Baostock] 首次查询空结果: 疑似连接异常, "
                                    "重置会话后重试"
                                )
                                self._reset_login()
                                need_retry = True
                            else:
                                return result
            if not need_retry:
                return rs
            time.sleep(FetchConfig.RETRY_BACKOFF * (attempt + 1))
        logger.error(f"[Baostock] 查询重试 {FetchConfig.RETRY_TIMES} 次后仍失败: {last_err}")
        return None

    @staticmethod
    def _query_with_read(query_fn, read_fn):
        """在 baostock 执行线程内运行: query_fn 后可选 read_fn 消费结果。

        read_fn 抛出的任何异常(zlib 解压错误等)原样返回, 由 _run_query 统一重试。
        """
        try:
            rs = query_fn()
        except Exception as e:
            return e
        if read_fn is not None:
            try:
                return read_fn(rs)
            except Exception as e:
                return e
        return rs

    def is_available(self) -> bool:
        return _HAS_BAOSTOCK

    # ---------- 1. 股票列表 ----------
    def get_stock_list(self) -> pd.DataFrame:
        if not _HAS_BAOSTOCK:
            return pd.DataFrame()
        with _BS_LOCK:
            if not self._ensure_login():
                return pd.DataFrame()

            def _read(rs):
                rows = list(_iter_rows(rs))
                # 网络损坏时可能返回残缺行, 过滤列数不足的
                return [r for r in rows if r is not None and len(r) >= 6]

            result = self._run_query(
                lambda: bs.query_stock_basic(),
                read_fn=_read,
            )
            if result is None or isinstance(result, Exception):
                logger.warning(f"[Baostock] query_stock_basic 失败: {result}")
                return pd.DataFrame()
            if getattr(result, "error_code", "0") != "0":
                logger.error(f"[Baostock] query_stock_basic 失败: {result.error_msg}")
                return pd.DataFrame()
            raw_rows = result

        rows = []
        for row in raw_rows:
            # 字段: code, code_name, ipoDate, outDate, type, status
            code, name, ipo_date, out_date, stock_type, status = row[:6]
            if status != "1":  # 1=在市
                continue
            # 只保留个股(stock_type=1),过滤指数/债券/基金(stock_type=2/3/4)
            if stock_type != "1":
                continue
            # code 格式: sh.600000 -> 取数字部分
            code_num = code.split(".")[-1]
            market = code.split(".")[0]
            # list_date baostock 返回 YYYY-MM-DD, 改为 YYYYMMDD 与 AKShare 对齐
            ld = ""
            if ipo_date and "-" in ipo_date:
                ld = ipo_date.replace("-", "")
            elif ipo_date and len(ipo_date) == 8:
                ld = ipo_date
            rows.append({
                "code": code_num,
                "name": name,
                "market": market,
                "full_code": code,
                "is_active": 1,
                "industry": "",  # baostock 不返回行业,留空待 enrich
                "list_date": ld,
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

        def _read(rs):
            rows = []
            while rs.next():
                r = rs.get_row_data()
                # 网络损坏时 baostock 可能返回列数不足的残缺行, 防御性跳过
                if r is None or len(r) < 11:
                    raise ValueError(f"残缺行(列数 {0 if r is None else len(r)} < 11)")
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

        result = self._run_query(
            lambda: bs.query_history_k_data_plus(
                bs_code,
                # baostock 没有 change 字段,用 close - preclose 现场算
                "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg",
                start_date=start, end_date=end,
                frequency="d", adjustflag=adjustflag,
            ),
            read_fn=_read,
        )
        if result is None:
            logger.warning(f"[Baostock] {bs_code} 日K 获取失败(重试耗尽)")
            return pd.DataFrame()
        if isinstance(result, Exception):
            logger.warning(f"[Baostock] {bs_code} 日K 读取失败: {result}")
            return pd.DataFrame()
        if getattr(result, "error_code", "0") != "0":
            logger.warning(f"[Baostock] {bs_code} 日K 失败: {result.error_msg}")
            return pd.DataFrame()
        return result

    # ---------- 3. 指数 ----------
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        if not self._ensure_login():
            return pd.DataFrame()
        bs_code = _INDEX_CODE_MAP.get(code, code.replace("000001", ".000001"))
        if "." not in bs_code:
            bs_code = bs_code[:2] + "." + bs_code[2:]

        def _read(rs):
            rows = []
            while rs.next():
                r = rs.get_row_data()
                if r is None or len(r) < 7:
                    raise ValueError(f"残缺行(列数 {0 if r is None else len(r)} < 7)")
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

        result = self._run_query(
            lambda: bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date="2020-01-01", end_date="2099-12-31",
                frequency="d", adjustflag="3",
            ),
            read_fn=_read,
        )
        if result is None or isinstance(result, Exception):
            return pd.DataFrame()
        if getattr(result, "error_code", "0") != "0":
            return pd.DataFrame()
        return result

    # ---------- 4. 个股信息(含行业/上市日期) ----------
    def get_stock_profile(self, code: str) -> Optional[dict]:
        """从 stock_basic + stock_industry 合并拿行业和上市日期"""
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

        # 1) 基础信息
        rs = self._run_query(lambda: bs.query_stock_basic(code=bs_code))
        if rs is None or isinstance(rs, Exception):
            return None
        if rs.error_code != "0":
            return None
        if not rs.next():
            return None
        r = rs.get_row_data()
        code_full, name, ipo_date, out_date, stock_type, status = r[:6]

        # 2) 行业(证监会分类,baostock 提供)
        industry = ""
        rs_ind = self._run_query(
            lambda: bs.query_stock_industry(code=bs_code),
            read_fn=lambda rsi: [
                row for row in _iter_rows(rsi)
                if row is not None and len(row) >= 4
            ] if rsi.error_code == "0" else [],
        )
        if rs_ind and not isinstance(rs_ind, Exception):
            for ind_row in rs_ind:
                if len(ind_row) >= 4 and ind_row[1] == bs_code:
                    industry = ind_row[3]
                    break

        return {
            "industry": industry,
            "list_date": ipo_date,
            "company_name": name,
        }