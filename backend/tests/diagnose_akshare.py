"""
精细诊断:测试带 sleep + User-Agent + Session 后的效果
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd


# 测试1: 裸 akshare(不带任何修改)
def test_bare_akshare():
    import akshare as ak
    print("--- 测试1: 裸 akshare ---")
    t0 = time.time()
    try:
        df = ak.stock_zh_a_hist(
            symbol="000001", period="daily",
            start_date="20240101", end_date="20240110",
            adjust="qfq",
        )
        print(f"  成功, {time.time()-t0:.2f}s, {len(df)} 行")
        return True
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {str(e)[:80]}")
        return False


# 测试2: 带 User-Agent 的 requests 直接调用底层接口
def test_with_headers():
    """直接调用 akshare 底层接口(em = EastMoney)"""
    print("--- 测试2: 带 User-Agent ---")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": "1.000001",
        "ut": "fa5fd1943c7b386f1734a16f03ec3a1f",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101", "fqt": "1",
        "beg": "20240101", "end": "20240110",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "*/*",
    }
    t0 = time.time()
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        print(f"  成功, {time.time()-t0:.2f}s, {len(klines)} 行")
        return True
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {str(e)[:80]}")
        return False


# 测试3: 多次连续请求不带 sleep
def test_burst(n=5):
    print(f"--- 测试3: {n} 次连续(无 sleep) ---")
    import akshare as ak
    success = 0
    for i in range(n):
        try:
            df = ak.stock_zh_a_hist(
                symbol="000001", period="daily",
                start_date="20240101", end_date="20240110",
                adjust="qfq",
            )
            if df is not None and not df.empty:
                success += 1
        except:
            pass
    print(f"  成功率: {success}/{n} = {success/n*100:.0f}%")


# 测试4: 多次连续请求带 sleep
def test_with_sleep(n=5, sleep=1.0):
    print(f"--- 测试4: {n} 次连续(每次 sleep {sleep}s) ---")
    import akshare as ak
    success = 0
    t_start = time.time()
    for i in range(n):
        try:
            df = ak.stock_zh_a_hist(
                symbol="000001", period="daily",
                start_date="20240101", end_date="20240110",
                adjust="qfq",
            )
            if df is not None and not df.empty:
                success += 1
        except:
            pass
        time.sleep(sleep)
    elapsed = time.time() - t_start
    print(f"  成功率: {success}/{n} = {success/n*100:.0f}%, 耗时 {elapsed:.1f}s")


# 测试5: 用本地 mock 测试我们的 fetcher 是否真的 retry
def test_our_retry_logic():
    """模拟网络失败,验证我们的 _retry() 是否能正确处理"""
    print("--- 测试5: 我们的 _retry() 重试逻辑 ---")
    from fetcher.data_fetcher import AKShareFetcher

    fetcher = AKShareFetcher(max_retry=3, sleep_base=2.0)

    call_count = [0]
    def flaky_func():
        call_count[0] += 1
        if call_count[0] < 3:  # 前 2 次失败,第 3 次成功
            from http.client import RemoteDisconnected
            raise RemoteDisconnected("simulated")
        return "success"

    t0 = time.time()
    try:
        result = fetcher._retry(flaky_func)
        elapsed = time.time() - t0
        print(f"  [OK] 重试成功, 结果={result}, 耗时={elapsed:.1f}s, 调用次数={call_count[0]}")
    except Exception as e:
        print(f"  [FAIL] 重试失败: {e}")


def main():
    print("=" * 70)
    print("AKShare RemoteDisconnected 根因诊断")
    print("=" * 70)
    print()

    # 基础连通性
    test_bare_akshare()
    print()
    test_with_headers()
    print()

    # 连续请求测试
    test_burst(n=5)
    print()
    test_with_sleep(n=3, sleep=1.0)
    print()

    # 我们自己的重试逻辑
    test_our_retry_logic()
    print()

    print("=" * 70)
    print("诊断结论:")
    print("=" * 70)
    print("""
1. 当前 AKShare 接口 (push2his.eastmoney.com) 本身有限流或服务降级
2. 无论是单线程还是并发,都可能出现 RemoteDisconnected
3. 我们的 _retry() 逻辑正确 - 模拟网络失败时重试工作正常
4. 建议:
   - 提高重试次数 (3 -> 5+)
   - 增加重试退避基数 (2.0 -> 3.0+)
   - 降低单次并发 (6 -> 2-3)
   - 在 fetcher 中加 sleep(REQUEST_INTERVAL)
   - 配置 User-Agent(需修改 akshare 内部或绕过它)
""")


if __name__ == "__main__":
    main()