"""
通用工具 - 前后端共用的训练费计算放这里,保持单一事实源.

如果以后改成 WebAssembly 调用 Python(例如 Brython / Pyodide),
可让前端 import 这个模块的 wasm 编译版;
否则前端用 JS 重写一份并保持公式一致, 由 CI 校验两端数值.
"""
from __future__ import annotations


# 训练费:已取消(2026-07-31 起),发起训练不再从余额扣任何固定费用。
# 仅保留函数签名供历史接口调用,实际返回 0;后续版本可删除该字段。
TRAIN_SESSION_COST = 0.0


def calc_session_cost(start_date: str = "", end_date: str = "", initial_cash: float = 0.0) -> float:
    """计算发起一场训练所需的训练资金(元).

    当前为 0:不再收取固定训练费,钱包余额全部可用于交易。

    参数:
        start_date: 训练开始日 (YYYY-MM-DD) — 已不再使用,保留签名兼容
        end_date:   数据结束日 (YYYY-MM-DD) — 已不再使用,保留签名兼容
        initial_cash: 初始资金(元)         — 已不再使用,保留签名兼容

    返回: 固定 0.0
    """
    return round(TRAIN_SESSION_COST, 2)
