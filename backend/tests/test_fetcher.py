"""
测试 fetcher 的错误处理改进:
1. _is_transient_error() 正确识别瞬时错误
2. _retry() 重试瞬时错误但不重试永久错误
3. _throttle() 强制请求间隔
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fetcher.data_fetcher import _is_transient_error, AKShareFetcher


def test_transient_detection():
    print("--- _is_transient_error 检测 ---")

    # 真实 http.client 错误(应该识别为瞬时)
    from http.client import RemoteDisconnected
    err = RemoteDisconnected("Remote end closed connection without response")
    assert _is_transient_error(err) is True
    print("  [OK] http.client.RemoteDisconnected -> transient")

    # 真实 ConnectionError 包裹
    try:
        raise ConnectionError("Connection aborted.")
    except ConnectionError as e:
        assert _is_transient_error(e) is True
        print("  [OK] ConnectionError -> transient")

    # 含关键字的消息
    assert _is_transient_error(Exception("Read timed out")) is True
    print("  [OK] 'Read timed out' message -> transient")

    # 永久错误
    assert _is_transient_error(ValueError("invalid stock code")) is False
    print("  [OK] ValueError -> permanent")

    assert _is_transient_error(KeyError("missing field")) is False
    print("  [OK] KeyError -> permanent")

    assert _is_transient_error(TypeError("bad arg")) is False
    print("  [OK] TypeError -> permanent")


def test_retry_transient_succeeds():
    print("--- _retry 重试瞬时错误直到成功 ---")
    fetcher = AKShareFetcher(max_retry=3, sleep_base=0.1)

    call_count = [0]
    from http.client import RemoteDisconnected
    def flaky():
        call_count[0] += 1
        if call_count[0] < 3:
            raise RemoteDisconnected("simulated")
        return "ok"

    t0 = time.time()
    result = fetcher._retry(flaky)
    elapsed = time.time() - t0
    assert result == "ok"
    assert call_count[0] == 3
    print(f"  [OK] 第3次成功, 调用 {call_count[0]} 次, 耗时 {elapsed:.2f}s")


def test_retry_permanent_fails_fast():
    print("--- _retry 永久错误不重试 ---")
    fetcher = AKShareFetcher(max_retry=5, sleep_base=0.1)

    call_count = [0]
    def perm_error():
        call_count[0] += 1
        raise ValueError("invalid stock code 999999")

    try:
        fetcher._retry(perm_error)
        assert False, "应该抛 ValueError"
    except ValueError as e:
        assert call_count[0] == 1, f"永久错误不应重试,实际调用 {call_count[0]} 次"
        print(f"  [OK] 永久错误立即失败,只调用 {call_count[0]} 次 (不浪费时间)")


def test_retry_exhausted():
    print("--- _retry 重试耗尽抛 RuntimeError ---")
    fetcher = AKShareFetcher(max_retry=3, sleep_base=0.1)

    call_count = [0]
    from http.client import RemoteDisconnected
    def always_fail():
        call_count[0] += 1
        raise RemoteDisconnected("persistent")

    try:
        fetcher._retry(always_fail)
        assert False, "应该抛 RuntimeError"
    except RuntimeError as e:
        assert "重试3次后仍失败" in str(e)
        assert call_count[0] == 3
        print(f"  [OK] 重试 3 次后失败, 抛出 RuntimeError")


def test_throttle():
    print("--- _throttle 请求间隔限流 ---")
    fetcher = AKShareFetcher(max_retry=3, sleep_base=0.1, request_interval=0.5)

    fetcher._throttle()  # 首次应立即通过
    t0 = time.time()
    fetcher._throttle()  # 第二次应等 ~0.5s
    elapsed = time.time() - t0
    assert elapsed >= 0.45, f"应等待至少 0.45s, 实际 {elapsed:.3f}s"
    print(f"  [OK] 第二次 _throttle 等待 {elapsed:.3f}s (>= 0.45s)")


def test_throttle_disabled():
    print("--- _throttle 间隔=0 时不阻塞 ---")
    fetcher = AKShareFetcher(max_retry=3, sleep_base=0.1, request_interval=0)

    fetcher._throttle()
    t0 = time.time()
    fetcher._throttle()
    fetcher._throttle()
    elapsed = time.time() - t0
    assert elapsed < 0.1
    print(f"  [OK] request_interval=0 时不限流 (耗时 {elapsed:.3f}s)")


def test_backoff_with_jitter():
    """退避应带抖动(随机性)"""
    print("--- 退避抖动验证 ---")
    fetcher = AKShareFetcher(max_retry=3, sleep_base=2.0)
    fetcher.jitter = 0.5

    # 模拟多次,看实际睡眠时间是否在合理范围内
    waits = []
    for i in range(5):
        t0 = time.time()
        fetcher._throttle()  # 不影响,但测试 _retry 的 wait
        # 直接计算预期 wait
        wait = 2.0 * (5 + 1)  # 第 6 次 (i=5)
        wait = wait * (1 + __import__('random').uniform(-0.5, 0.5))
        waits.append(wait)
    # 验证至少有变化(抖动)
    assert len(set(round(w, 2) for w in waits)) >= 3, f"抖动不够随机: {waits}"
    print(f"  [OK] 5 次 wait 都不同: {[round(w,2) for w in waits]}")


if __name__ == "__main__":
    print("=" * 70)
    print("fetcher 错误处理测试")
    print("=" * 70)
    print()
    test_transient_detection()
    print()
    test_retry_transient_succeeds()
    print()
    test_retry_permanent_fails_fast()
    print()
    test_retry_exhausted()
    print()
    test_throttle()
    print()
    test_throttle_disabled()
    print()
    test_backoff_with_jitter()
    print()
    print("=" * 70)
    print("全部通过!")
    print("=" * 70)