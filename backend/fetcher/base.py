"""
数据源抽象基类 —— 所有 fetcher 必须实现这些接口

设计目标:
- 统一方法签名,便于切换数据源
- 每个 fetcher 自己处理重试/限流
- FetcherManager 可以 failover 到其他源
"""
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class BaseFetcher(ABC):
    """所有数据源的统一接口"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源标识: 'akshare' / 'baostock' / 'tushare'"""

    @property
    @abstractmethod
    def requires_token(self) -> bool:
        """是否需要外部 token"""

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查当前是否可用(包已装 + token 已配置 + 网络可达)
        不要真的发请求,只做轻量检测
        """

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全市场股票列表
        返回 DataFrame 必须包含列: code, name, market
        """

    @abstractmethod
    def get_daily_kline(
        self,
        code: str,
        start_date: str,  # YYYY-MM-DD
        end_date: str,    # YYYY-MM-DD
        adjust: str = "qfq",  # qfq / hfq / none
    ) -> pd.DataFrame:
        """
        获取日 K 线
        返回 DataFrame 必须包含列: code, trade_date, open, high, low, close,
        pre_close, change_amount, pct_change, volume, amount, turnover_rate, adjust_type
        """

    @abstractmethod
    def get_index_daily(self, code: str = "sh000001") -> pd.DataFrame:
        """
        获取指数日线
        返回 DataFrame 包含: code, trade_date, open, high, low, close, volume
        """

    # ---------- 可选方法(子类可重写) ----------
    def get_industry_map(self) -> dict:
        """获取行业映射 {code: industry},不可用时返回 {}"""
        return {}

    def get_stock_profile(self, code: str) -> Optional[dict]:
        """获取个股信息(上市日期/全称),不可用时返回 None"""
        return None