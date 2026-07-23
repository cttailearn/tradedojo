"""
测试 FetcherManager 的 failover 行为

不需要真实网络 - 用 mock fetcher 模拟
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from fetcher.base import BaseFetcher


# ---- Mock 数据源 ----
class MockOKFetcher(BaseFetcher):
    """总是成功的 mock"""

    def __init__(self, name="mock_ok"):
        self._name = name

    @property
    def source_name(self): return self._name

    @property
    def requires_token(self): return False

    def is_available(self): return True

    def get_stock_list(self):
        return pd.DataFrame({"code": ["000001"], "name": ["测试"], "market": ["sz"]})

    def get_daily_kline(self, code, start_date, end_date, adjust="qfq"):
        return pd.DataFrame({"code": [code], "trade_date": ["2024-01-01"], "close": [10.0]})

    def get_index_daily(self, code="sh000001"):
        return pd.DataFrame({"code": [code], "close": [3000.0]})


class MockFailFetcher(BaseFetcher):
    """总是失败的 mock"""

    def __init__(self, name="mock_fail", error=None):
        self._name = name
        self._error = error or RuntimeError("mock failure")

    @property
    def source_name(self): return self._name

    @property
    def requires_token(self): return False

    def is_available(self): return True

    def get_stock_list(self):
        raise self._error

    def get_daily_kline(self, code, start_date, end_date, adjust="qfq"):
        raise self._error

    def get_index_daily(self, code="sh000001"):
        raise self._error


# ---- 测试 ----
def test_primary_succeeds():
    """主源成功 → 用主源,不 failover"""
    from fetcher.manager import FetcherManager

    primary = MockOKFetcher("primary")
    backup = MockOKFetcher("backup")
    mgr = FetcherManager()
    mgr._fetchers = {"primary": primary, "backup": backup}
    mgr._primary = "primary"
    # mock 注册时也要初始化 stats
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    df = mgr.get_stock_list()
    assert len(df) == 1
    # 统计:primary 成功 +1,backup 不动
    assert mgr._stats["primary"]["success"] == 1
    assert mgr._stats["backup"]["success"] == 0
    assert mgr._stats["backup"]["failed"] == 0
    print("[OK] 主源成功 → 不 failover")


def test_failover_to_backup():
    """主源失败 → 自动 failover 到备源"""
    from fetcher.manager import FetcherManager

    primary = MockFailFetcher("primary")
    backup = MockOKFetcher("backup")
    mgr = FetcherManager()
    mgr._fetchers = {"primary": primary, "backup": backup}
    mgr._primary = "primary"
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    df = mgr.get_stock_list()
    assert len(df) == 1
    assert mgr._stats["primary"]["failed"] == 1
    assert mgr._stats["backup"]["success"] == 1
    print("[OK] 主源失败 → 自动 failover 到 backup")


def test_all_fail_raises():
    """所有源都失败 → 抛 RuntimeError"""
    from fetcher.manager import FetcherManager

    a = MockFailFetcher("a", error=ConnectionError("a down"))
    b = MockFailFetcher("b", error=ConnectionError("b down"))
    mgr = FetcherManager()
    mgr._fetchers = {"a": a, "b": b}
    mgr._primary = "a"
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    try:
        mgr.get_stock_list()
        assert False, "应该抛 RuntimeError"
    except RuntimeError as e:
        assert "所有数据源" in str(e)
        assert mgr._stats["a"]["failed"] == 1
        assert mgr._stats["b"]["failed"] == 1
        print(f"[OK] 全部失败 → 抛 RuntimeError: {str(e)[:60]}")


def test_set_primary():
    """切换主源"""
    from fetcher.manager import FetcherManager

    a = MockOKFetcher("a")
    b = MockOKFetcher("b")
    mgr = FetcherManager()
    mgr._fetchers = {"a": a, "b": b}
    mgr._primary = "a"
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    assert mgr.get_primary() == "a"
    assert mgr.set_primary("b") is True
    assert mgr.get_primary() == "b"
    assert mgr.set_primary("nonexistent") is False
    print("[OK] 切换主源成功")


def test_test_source():
    """test_source() 报告每个源的状态"""
    from fetcher.manager import FetcherManager

    ok = MockOKFetcher("ok")
    fail = MockFailFetcher("fail")
    mgr = FetcherManager()
    mgr._fetchers = {"ok": ok, "fail": fail}
    mgr._primary = "ok"
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    r1 = mgr.test_source("ok")
    assert r1["available"] is True
    assert r1["rows"] == 1

    r2 = mgr.test_source("fail")
    assert r2["available"] is False
    assert r2["error"]

    r3 = mgr.test_source("unknown")
    assert r3["available"] is False
    print(f"[OK] test_source: ok=[available={r1['available']}], "
          f"fail=[error={r2['error'][:30]}]")


def test_list_sources():
    """list_sources 返回所有源的状态"""
    from fetcher.manager import FetcherManager

    a = MockOKFetcher("a")
    b = MockFailFetcher("b")
    mgr = FetcherManager()
    mgr._fetchers = {"a": a, "b": b}
    mgr._primary = "a"
    for n in mgr._fetchers:
        mgr._stats[n] = {"success": 0, "failed": 0,
                         "last_used": None, "last_error": None}

    sources = mgr.list_sources()
    names = [s["name"] for s in sources]
    assert "a" in names and "b" in names
    assert any(s["is_primary"] for s in sources if s["name"] == "a")
    assert not any(s["is_primary"] for s in sources if s["name"] == "b")
    print(f"[OK] list_sources 返回 {len(sources)} 个源")


def test_real_akshare_initialization():
    """真实 AKShare 注册检查(不需要网络)"""
    from fetcher import fetcher_manager

    sources = fetcher_manager.list_sources()
    names = [s["name"] for s in sources]
    # 至少应该有 akshare(无 token 也可用)
    assert "akshare" in names, "AKShare 应该自动注册"
    # 主源应是 akshare
    assert fetcher_manager.get_primary() in names
    print(f"[OK] 真实管理器注册了: {names}")


if __name__ == "__main__":
    print("=" * 70)
    print("FetcherManager failover 测试")
    print("=" * 70)
    print()
    test_primary_succeeds()
    print()
    test_failover_to_backup()
    print()
    test_all_fail_raises()
    print()
    test_set_primary()
    print()
    test_test_source()
    print()
    test_list_sources()
    print()
    test_real_akshare_initialization()
    print()
    print("=" * 70)
    print("全部通过!")
    print("=" * 70)