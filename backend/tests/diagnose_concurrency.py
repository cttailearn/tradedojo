"""
诊断脚本:测试 AKShare 接口在不同并发度下的成功率

目的:验证"RemoteDisconnected"错误是否由并发过高导致
方法:对同一接口 (stock_zh_a_hist) 用不同并发数各拉 50 次,记录成功率/平均耗时
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak


def fetch_one(code: str) -> tuple[bool, float, str]:
    """单次拉取"""
    t0 = time.time()
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20240101", end_date="20240110",
            adjust="qfq",
        )
        elapsed = time.time() - t0
        if df is None or df.empty:
            return (False, elapsed, "empty")
        return (True, elapsed, "ok")
    except Exception as e:
        return (False, time.time() - t0, f"{type(e).__name__}: {str(e)[:60]}")


def run_benchmark(concurrency: int, codes: list[str]) -> dict:
    """在指定并发下跑测试"""
    results = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch_one, c): c for c in codes}
        for fut in as_completed(futures):
            results.append(fut.result())
    total = time.time() - t_start

    success = sum(1 for r in results if r[2] == "ok")
    failed = len(results) - success
    errors = {}
    for r in results:
        if r[2] != "ok":
            errors[r[2]] = errors.get(r[2], 0) + 1
    avg_time = sum(r[1] for r in results) / len(results) if results else 0

    return {
        "concurrency": concurrency,
        "total": len(results),
        "success": success,
        "failed": failed,
        "success_rate": success / len(results) * 100,
        "total_time": total,
        "avg_request_time": avg_time,
        "errors": errors,
    }


def main():
    # 准备测试股票代码(A 股前 100 只,降低对方服务器压力)
    codes = []
    for i in range(1, 100):
        codes.append(f"{i:06d}")

    print("=" * 70)
    print("AKShare 接口并发基准测试")
    print(f"  测试接口: ak.stock_zh_a_hist (stock_zh_a_hist)")
    print(f"  测试代码: {len(codes)} 只股票")
    print(f"  日期范围: 2024-01-01 ~ 2024-01-10")
    print("=" * 70)
    print()

    # 测试不同并发度
    test_concurrencies = [1, 2, 4, 6, 8, 12]

    summary = []
    for c in test_concurrencies:
        print(f"--- 并发度 = {c} ---")
        result = run_benchmark(c, codes)
        print(f"  成功: {result['success']}/{result['total']} ({result['success_rate']:.1f}%)")
        print(f"  失败: {result['failed']}")
        print(f"  总耗时: {result['total_time']:.1f}s")
        print(f"  平均单请求: {result['avg_request_time']:.2f}s")
        if result['errors']:
            print(f"  错误类型:")
            for err, cnt in result['errors'].items():
                print(f"    {err}: {cnt} 次")
        summary.append(result)
        print()
        # 让对方服务器喘口气
        time.sleep(3)

    print("=" * 70)
    print("汇总对比:")
    print("=" * 70)
    print(f"{'并发':<6} {'成功率':<10} {'总耗时':<10} {'平均请求':<10} {'失败次数':<10}")
    print("-" * 70)
    for r in summary:
        print(
            f"{r['concurrency']:<6} "
            f"{r['success_rate']:.1f}%      "
            f"{r['total_time']:.1f}s       "
            f"{r['avg_request_time']:.2f}s      "
            f"{r['failed']:<10}"
        )

    # 给出建议
    print()
    print("=" * 70)
    print("建议:")
    best = max(summary, key=lambda r: r['success_rate'] * 100 - r['failed'] * 10)
    print(f"  推荐并发度: {best['concurrency']} (成功率 {best['success_rate']:.1f}%)")
    print(f"  当前配置: MAX_CONCURRENT_FETCH = 6 (来自 config.py)")
    if best['concurrency'] < 6:
        print(f"  ⚠️ 当前配置过高,建议降低到 {best['concurrency']}")
    print("=" * 70)


if __name__ == "__main__":
    main()