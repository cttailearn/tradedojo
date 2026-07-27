"""
通用工具 - 前后端共用的训练费计算放这里,保持单一事实源.

如果以后改成 WebAssembly 调用 Python(例如 Brython / Pyodide),
可让前端 import 这个模块的 wasm 编译版;
否则前端用 JS 重写一份并保持公式一致, 由 CI 校验两端数值.
"""
from __future__ import annotations

from datetime import datetime


# 训练费阶梯(与后端保持完全一致,前端 JS 版写在 frontend/src/utils/trainFee.js):
#   base = 5.0  元
#   + span_days * 0.05        训练区间每自然日 5 分
#   + (initial_cash / 1e6) * 20  初始资金每 100 万 +20 元
#   cap  = 5 ~ 80 元
def calc_session_cost(start_date: str, end_date: str, initial_cash: float) -> float:
    """计算发起一场训练所需的训练资金(元).

    参数:
        start_date: 训练开始日 (YYYY-MM-DD)
        end_date:   数据结束日 (YYYY-MM-DD)
        initial_cash: 初始资金(元)

    返回: 5 ~ 80 元 之间的实数.
    """
    try:
        span_days = max(1, (
            datetime.strptime(end_date, "%Y-%m-%d")
            - datetime.strptime(start_date, "%Y-%m-%d")
        ).days)
    except Exception:
        span_days = 30
    cash_factor = min(60.0, (float(initial_cash) / 1_000_000.0) * 20.0)
    cost = min(80.0, max(5.0, 5.0 + span_days * 0.05 + cash_factor))
    return round(cost, 2)
