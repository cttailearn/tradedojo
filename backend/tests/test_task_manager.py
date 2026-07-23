"""
测试 task_manager 的 progress_callback 注入逻辑

确保:
1. 闭包(无参数)不会被注入 progress_callback
2. 接受 progress_callback 的函数会被注入
3. **kwargs 函数也会被注入
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.task_manager import _func_accepts_progress_callback


def test_no_args_closure():
    """无参数闭包 - 不应接受 progress_callback"""
    def runner():
        return "ok"

    assert _func_accepts_progress_callback(runner) is False
    print("  [OK] 无参数闭包 → False")


def test_explicit_progress_callback():
    """显式声明 progress_callback - 应接受"""
    def runner(progress_callback=None):
        progress_callback({"step": 1})
        return "ok"

    assert _func_accepts_progress_callback(runner) is True
    print("  [OK] 显式 progress_callback → True")


def test_kwargs_acceptor():
    """**kwargs 函数 - 应接受(可以吸收任意 kwarg)"""
    def runner(**kwargs):
        return kwargs

    assert _func_accepts_progress_callback(runner) is True
    print("  [OK] **kwargs 函数 → True")


def test_other_kwargs_not_match():
    """只接受其他参数 - 不应接受"""
    def runner(days=365, adjust="qfq"):
        return "ok"

    assert _func_accepts_progress_callback(runner) is False
    print("  [OK] 只接受其他参数 → False")


def test_normal_args():
    """普通位置参数 - 不应接受"""
    def runner(code, start, end):
        return "ok"

    assert _func_accepts_progress_callback(runner) is False
    print("  [OK] 普通位置参数 → False")


def test_lambda():
    """lambda(无参数) - 不应接受"""
    runner = lambda: "ok"
    assert _func_accepts_progress_callback(runner) is False
    print("  [OK] lambda → False")


# ----- 集成测试: 实际运行 task_manager.submit() -----
def test_submit_closure_works():
    """集成测试: 提交无参数闭包,不应抛 TypeError"""
    import time
    from app.task_manager import task_manager

    def runner():  # 无参数
        return {"ok": True}

    task_id = task_manager.submit("test_no_args", runner)
    # 等任务完成
    for _ in range(50):
        rec = task_manager.get(task_id)
        if rec and rec["status"] in ("success", "failed"):
            break
        time.sleep(0.1)

    rec = task_manager.get(task_id)
    assert rec["status"] == "success", f"任务失败: {rec}"
    assert rec["progress"].get("result") == {"ok": True}
    print(f"  [OK] 集成测试: 无参数闭包任务成功 ({rec['status']})")


def test_submit_with_progress_callback():
    """集成测试: 接受 progress_callback 的函数,应正常回调"""
    import time
    from app.task_manager import task_manager

    progress_seen = []

    def runner(progress_callback=None):
        progress_callback({"step": "started"})
        time.sleep(0.2)
        progress_callback({"step": "middle"})
        progress_callback({"step": "done"})
        return {"final": True}

    task_id = task_manager.submit("test_with_progress", runner)
    for _ in range(50):
        rec = task_manager.get(task_id)
        if rec and rec["status"] in ("success", "failed"):
            break
        time.sleep(0.1)

    rec = task_manager.get(task_id)
    assert rec["status"] == "success"
    assert rec["progress"].get("step") == "done", f"progress 未更新: {rec['progress']}"
    assert rec["progress"].get("result") == {"final": True}
    print(f"  [OK] 集成测试: progress_callback 任务成功 ({rec['status']})")


if __name__ == "__main__":
    print("=" * 60)
    print("task_manager 单元测试")
    print("=" * 60)

    print("\n[1] _func_accepts_progress_callback 检测逻辑:")
    test_no_args_closure()
    test_explicit_progress_callback()
    test_kwargs_acceptor()
    test_other_kwargs_not_match()
    test_normal_args()
    test_lambda()

    print("\n[2] 集成测试:")
    test_submit_closure_works()
    test_submit_with_progress_callback()

    print("\n" + "=" * 60)
    print("全部通过!")
    print("=" * 60)