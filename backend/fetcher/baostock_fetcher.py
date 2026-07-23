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
from typing import Optional
import pandas as pd

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

    def is_available(self) -> bool:
        return _HAS_BAOSTOCK

    # ---------- 1. 股票列表 ----------
    def get_stock_list(self) -> pd.DataFrame:
        if not self._ensure_login():
            return pd.DataFrame()
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            logger.error(f"[Baostock] query_stock_basic 失败: {rs.error_msg}")
            return pd.DataFrame()

        rows = []
        while rs.next():
            row = rs.get_row_data()
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
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,change",
            start_date=start, end_date=end,
            frequency="d", adjustflag=adjustflag,
        )
        if rs.error_code != "0":
            logger.warning(f"[Baostock] {bs_code} 日K 失败: {rs.error_msg}")
            return pd.DataFrame()

        rows = []
        while rs.next():
            r = rs.get_row_data()
            date, o, h, l, c, pc, vol, amt, tr, status, pct, ch = r[:12]
            if status not in ("1",):  # 只取交易日
                continue
            rows.append({
                "code": code,
                "trade_date": date,
                "open": float(o) if o else None,
                "high": float(h) if h else None,
                "low": float(l) if l else None,
                "close": float(c) if c else None,
                "pre_close": float(pc) if pc else None,
                "change_amount": float(ch) if ch else None,
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

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date="2020-01-01", end_date="2099-12-31",
            frequency="d", adjustflag="3",
        )
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
        rs = bs.query_stock_basic(code=bs_code)
        if rs.error_code != "0":
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