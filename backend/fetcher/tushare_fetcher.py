"""
Tushare 数据源实现

特点:
- 数据质量最高(经过清洗和标准化)
- 需要 token(注册 tushare.pro 获得,免费用户有积分限制)
- 接口丰富:基本面/财务/资金流等

如果未配置 TUSHARE_TOKEN 环境变量,该源自动不可用。
"""
import logging
import os
from typing import Optional
import pandas as pd

from .base import BaseFetcher

logger = logging.getLogger(__name__)

try:
    import tushare as ts
    _HAS_TUSHARE = True
except ImportError:
    ts = None
    _HAS_TUSHARE = False
    logger.warning("[Tushare] 包未安装,此数据源不可用")


def _get_token() -> Optional[str]:
    return os.environ.get("TUSHARE_TOKEN") or os.environ.get("STOCK_TUSHARE_TOKEN")


class TushareFetcher(BaseFetcher):
    """Tushare 数据源(需 token)"""

    def __init__(self):
        self._pro = None
        self._token = _get_token()
        if self._token and _HAS_TUSHARE:
            try:
                ts.set_token(self._token)
                self._pro = ts.pro_api()
            except Exception as e:
                logger.error(f"[Tushare] 初始化失败: {e}")
                self._pro = None

    @property
    def source_name(self) -> str:
        return "tushare"

    @property
    def requires_token(self) -> bool:
        return True

    def is_available(self) -> bool:
        return _HAS_TUSHARE and self._pro is not None

    # ---------- 1. 股票列表 ----------
    def get_stock_list(self) -> pd.DataFrame:
        if not self.is_available():
            return pd.DataFrame()
        try:
            df = self._pro.stock_basic(
                list_status="L",  # L=上市,D=退市,P=暂停
                fields="ts_code,symbol,name,industry,list_date,exchange",
            )
        except Exception as e:
            logger.error(f"[Tushare] stock_basic 失败: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # ts_code 格式: 000001.SZ -> 取 symbol 部分
        out = pd.DataFrame({
            "code": df["symbol"].astype(str),
            "name": df["name"].astype(str),
            "full_code": df["ts_code"].astype(str),
            "industry": df["industry"].fillna("").astype(str),
            "list_date": df["list_date"].fillna("").astype(str),
            "is_active": 1,
        })
        # market 从 exchange 推断 (SSE=sh, SZSE=sz, BSE=bj)
        market_map = {"SSE": "sh", "SZSE": "sz", "BSE": "bj"}
        out["market"] = df["exchange"].map(market_map).fillna("")
        logger.info(f"[Tushare] 获取股票列表 {len(out)} 只")
        return out

    # ---------- 2. 日 K 线 ----------
    def get_daily_kline(
        self,
        code: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        if not self.is_available():
            return pd.DataFrame()
        # code 转 ts_code 格式
        if "." in code:
            ts_code = code
        else:
            if code.startswith(("60", "68", "90")):
                ts_code = f"{code}.SH"
            elif code.startswith(("00", "30", "20")):
                ts_code = f"{code}.SZ"
            elif code.startswith(("43", "83", "87", "92")):
                ts_code = f"{code}.BJ"
            else:
                ts_code = f"{code}.SH"

        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        # Tushare 的 adj 因子: qfq/hfq/none
        try:
            df = self._pro.daily(
                ts_code=ts_code, start_date=start, end_date=end,
                adj=adjust if adjust else None,
            )
        except Exception as e:
            logger.warning(f"[Tushare] {ts_code} 日K 失败: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # 补齐 turnover_rate:Tushare 的 daily 接口不含此字段,
        # 需调 daily_basic(ts_code, trade_date, turnover_rate) 一次性按日期补齐。
        turnover_map: dict = {}
        try:
            basic_df = self._pro.daily_basic(
                ts_code=ts_code, start_date=start, end_date=end,
                fields="ts_code,trade_date,turnover_rate",
            )
            if basic_df is not None and not basic_df.empty and "turnover_rate" in basic_df.columns:
                turnover_map = dict(
                    zip(
                        basic_df["trade_date"].astype(str),
                        basic_df["turnover_rate"].astype(float),
                    )
                )
        except Exception as e:
            # daily_basic 失败不影响主流程,turnover_rate 留空
            logger.debug(f"[Tushare] {ts_code} daily_basic 失败(忽略): {e}")

        # 字段: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        trade_dates = df["trade_date"].astype(str)
        out = pd.DataFrame({
            "code": code,
            "trade_date": trade_dates,
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
            "pre_close": df["pre_close"].astype(float) if "pre_close" in df.columns else None,
            "change_amount": df["change"].astype(float) if "change" in df.columns else None,
            "pct_change": df["pct_chg"].astype(float) if "pct_chg" in df.columns else None,
            "volume": df["vol"].astype(float) * 100 if "vol" in df.columns else 0,  # tushare vol 单位是手,转股
            "amount": df["amount"].astype(float) if "amount" in df.columns else None,
            "turnover_rate": trade_dates.map(turnover_map) if turnover_map else None,
            "adjust_type": adjust if adjust else "none",
        })
        return out

    # ---------- 3. 指数 ----------
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        if not self.is_available():
            return pd.DataFrame()
        if "." in code:
            ts_code = code
        else:
            ts_code = code[:2].lower() + "." + code[2:]
            ts_code = ts_code.replace("sh", "SH").replace("sz", "SZ")
        try:
            df = self._pro.index_daily(ts_code=ts_code)
        except Exception as e:
            logger.warning(f"[Tushare] {ts_code} 指数失败: {e}")
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        return pd.DataFrame({
            "code": code,
            "trade_date": df["trade_date"].astype(str),
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
            "volume": df["vol"].astype(float),
            "amount": df.get("amount", pd.Series([None] * len(df))).astype(float),
        })

    # ---------- 4. 个股信息 ----------
    def get_stock_profile(self, code: str) -> Optional[dict]:
        if not self.is_available():
            return None
        if "." in code:
            ts_code = code
        else:
            if code.startswith(("60", "68", "90")):
                ts_code = f"{code}.SH"
            elif code.startswith(("00", "30", "20")):
                ts_code = f"{code}.SZ"
            else:
                ts_code = f"{code}.BJ"
        try:
            df = self._pro.stock_basic(
                ts_code=ts_code,
                fields="ts_code,name,industry,list_date",
            )
            if df is None or df.empty:
                return None
            row = df.iloc[0]
            return {
                "industry": row.get("industry", ""),
                "list_date": str(row.get("list_date", "")),
                "company_name": row.get("name", ""),
            }
        except Exception:
            return None