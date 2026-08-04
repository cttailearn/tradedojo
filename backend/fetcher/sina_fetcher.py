"""
新浪行情数据源封装
- 仅提供分钟K线(30/60)与不复权日K线
- 无股票列表 / 指数日线接口,相关方法直接抛 NotImplementedError
- 继承 BaseFetcher 以纳入多数据源 failover 链

接口:CN_MarketData.getKLineData
  http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
  参数: symbol=sh600519 / sz000001, scale=30/60/240, ma=no, datalen=N(最大3000,无日期范围参数)
  返回 JSON 数组:
    [{"day":"2026-08-04 15:00:00","open":"11.600","high":"11.630",
      "low":"11.580","close":"11.620","volume":"24537222"}, ...]
  注意: scale=240(日线) 时 day 为 "YYYY-MM-DD";scale=30/60 时 day 为 "YYYY-MM-DD HH:MM:SS"
"""
import logging
from typing import Optional

import pandas as pd
import requests

from fetcher.base import BaseFetcher
from fetcher.data_fetcher import _normalize_market

logger = logging.getLogger(__name__)

# 新浪K线接口
_SINA_KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/"
    "api/json_v2.php/CN_MarketData.getKLineData"
)
_SINA_DATALEN = 3000  # 最大条数,足够覆盖 30-60 天分钟线 / 多年日线
_REQUEST_TIMEOUT = 15

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "http://finance.sina.com.cn/",
    "Accept": "text/javascript, application/javascript, application/ecmascript, */*",
    "Accept-Language": "zh-CN,zh;q=0.8,en;q=0.8",
}


class SinaFetcher(BaseFetcher):
    """新浪免费行情数据源"""

    @property
    def source_name(self) -> str:
        return "sina"

    @property
    def requires_token(self) -> bool:
        return False

    def is_available(self) -> bool:
        """仅需 requests/urllib,无需额外包与 token。"""
        try:
            import requests  # noqa
            return True
        except ImportError:
            return False

    # ---------- 内部工具 ----------
    @staticmethod
    def _build_symbol(code: str) -> str:
        """把纯 6 位代码加上市场前缀(sh/sz/bj),用于新浪 symbol 参数。"""
        prefix = _normalize_market(code) or "sh"
        return f"{prefix}{code}"

    def _request_kline(self, symbol: str, scale: int) -> pd.DataFrame:
        """请求新浪K线接口并返回按时间升序的 DataFrame(原始列 day/open/high/low/close/volume)。"""
        params = {
            "symbol": symbol,
            "scale": scale,
            "ma": "no",
            "datalen": _SINA_DATALEN,
        }
        resp = requests.get(
            _SINA_KLINE_URL, params=params, headers=_HEADERS, timeout=_REQUEST_TIMEOUT
        )
        resp.raise_for_status()

        data = resp.json()
        if not isinstance(data, list) or not data:
            return pd.DataFrame()

        raw = pd.DataFrame(data)
        # 字段均为字符串,先做数值转换
        for col in ("open", "high", "low", "close"):
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
        # volume 新浪返回"股",需 ÷100 转成"手"
        raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce") // 100
        raw = raw.sort_values("day").reset_index(drop=True)
        return raw

    # ---------- 1. 股票列表(不可用,抛错让 failover 跳过) ----------
    def get_stock_list(self) -> pd.DataFrame:
        raise NotImplementedError("新浪仅提供K线行情,无股票列表接口")

    # ---------- 2. 分钟K线 ----------
    def get_minute_kline(
        self,
        code: str,
        period: int = 5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取分钟K线
        :param period: 30/60(direct scale);5/15 新浪不支持 → NotImplementedError
        :param start_date: 开始日期 "YYYY-MM-DD", None=不过滤
        :param end_date: 结束日期 "YYYY-MM-DD", None=不过滤
        """
        scale = {30: 30, 60: 60}.get(period)
        if scale is None:
            raise NotImplementedError(f"新浪不提供 {period} 分钟K线(仅支持 30/60)")

        raw = self._request_kline(self._build_symbol(code), scale)

        # 统一标准化
        raw["trade_time"] = pd.to_datetime(raw["day"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        raw["code"] = code
        raw["period"] = period
        raw["amount"] = None  # 新浪不返回成交额

        df = raw[["code", "trade_time", "period", "open", "high",
                  "low", "close", "volume", "amount"]]

        if start_date or end_date:
            mask = pd.Series(True, index=df.index)
            t = pd.to_datetime(df["trade_time"])
            if start_date:
                mask &= t >= pd.to_datetime(start_date)
            if end_date:
                mask &= t <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            df = df[mask].reset_index(drop=True)

        return df

    # ---------- 3. 日K线(仅不复权) ----------
    def get_daily_kline(
        self,
        code: str,
        start_date: Optional[str] = None,  # YYYY-MM-DD
        end_date: Optional[str] = None,    # YYYY-MM-DD
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取日K线
        新浪仅提供不复权数据:adjust 为 qfq/hfq 时抛 NotImplementedError;
        adjust='' 或 'none' 时正常返回。
        """
        if adjust in ("qfq", "hfq", "qfur", "hfur"):
            raise NotImplementedError(
                "新浪仅提供不复权日线,不支持复权(fadj/qfq/hfq)"
            )

        raw = self._request_kline(self._build_symbol(code), scale=240)
        if raw.empty:
            return raw

        raw["trade_date"] = pd.to_datetime(raw["day"]).dt.strftime("%Y-%m-%d")
        raw = raw.sort_values("trade_date").reset_index(drop=True)

        # pre_close = 上一日 close
        raw["pre_close"] = raw["close"].shift(1)
        raw["code"] = code
        raw["change_amount"] = None
        raw["pct_change"] = None
        raw["amount"] = None
        raw["turnover_rate"] = None
        raw["adjust_type"] = adjust if adjust else "none"

        df = raw[["code", "trade_date", "open", "high", "low", "close",
                  "pre_close", "change_amount", "pct_change", "volume",
                  "amount", "turnover_rate", "adjust_type"]]

        if start_date or end_date:
            d = pd.to_datetime(df["trade_date"]).dt.date
            if start_date:
                df = df[d >= pd.to_datetime(start_date).date()].reset_index(drop=True)
                d = pd.to_datetime(df["trade_date"]).dt.date
            if end_date:
                df = df[d <= pd.to_datetime(end_date).date()].reset_index(drop=True)

        return df

    # ---------- 4. 指数日线(不可用,抛错让 failover 跳过) ----------
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        raise NotImplementedError("新浪不提供指数日线接口")

    # ---------- 可选成员 ----------
    def get_industry_map(self) -> dict:
        return {}

    def get_stock_profile(self, code: str) -> Optional[dict]:
        return None


# ---------- 单元测试 ----------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    f = SinaFetcher()
    k = f.get_minute_kline("000001", period=60)
    print(f"=== 分钟K线(000001, 60min) 共 {len(k)} 条 ===")
    print(k.head())
    print(k.tail())
    d = f.get_daily_kline("600519", adjust="none")
    print(f"\n=== 日K线(600519, 不复权) 共 {len(d)} 条 ===")
    print(d.head())
    print(d.tail())