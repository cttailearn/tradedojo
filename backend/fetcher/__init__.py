"""
Fetcher 包入口 —— 暴露统一的管理器和基类
"""
from .base import BaseFetcher
from .manager import fetcher_manager, FetcherManager

# 兼容旧代码:from fetcher.data_fetcher import AKShareFetcher
from .data_fetcher import AKShareFetcher

__all__ = [
    "BaseFetcher",
    "fetcher_manager",
    "FetcherManager",
    "AKShareFetcher",
]