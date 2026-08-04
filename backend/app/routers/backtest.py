"""
回测 API
- 同步执行(回测通常较快,可阻塞等待)
- 组合回测返回汇总 DataFrame 序列化

P1-11 修复 (2026-07-31): 区分"独立回测" 与 "真组合回测"
  - /portfolio : 保留兼容, 实际是 run_independent_loop (每只股 100% 资金, 取均值)
  - /independent-loop : /portfolio 的"真名", 显式说明语义
  - /basket : 新增真组合回测 (资金均分 N 份, 加总净值)
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.deps import require_admin
from app.models import BacktestRequest, PortfolioRequest
from app.task_manager import task_manager

router = APIRouter(prefix="/api/backtest", tags=["回测"], dependencies=[Depends(require_admin)])


_STRAT_MAP = {
    "sma": "SmaCrossStrategy",
    "momentum": "MomentumStrategy",
    "buy_hold": "BuyHoldStrategy",
    "ma_alignment": "MaAlignmentStrategy",  # 2026-08-04
}


def _build_params(req: BacktestRequest) -> dict:
    if req.strategy == "sma":
        return {"fast": req.fast, "slow": req.slow}
    if req.strategy == "momentum":
        return {
            "lookback": req.lookback,
            "momentum_thresh": req.thresh,
            "stop_loss": req.stop_loss,
            "take_profit": req.take_profit,
        }
    if req.strategy == "ma_alignment":
        return {
            "fast": req.fast,
            "mid": req.mid,
            "slow": req.slow,
            "vol_period": req.vol_period,
            "vol_ratio": req.vol_ratio,
        }
    return {}


@router.post("")
def run_backtest(req: BacktestRequest):
    """同步单股回测"""
    from backtest.runner import run_backtest as _run
    from backtest.strategies import (
        SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy, MaAlignmentStrategy,
    )
    classes = {
        "sma": SmaCrossStrategy,
        "momentum": MomentumStrategy,
        "buy_hold": BuyHoldStrategy,
        "ma_alignment": MaAlignmentStrategy,
    }
    if req.strategy not in classes:
        raise HTTPException(status_code=400, detail=f"未知策略: {req.strategy}")

    try:
        result = _run(
            code=req.code, start=req.start, end=req.end,
            adjust_type=req.adjust, initial_cash=req.cash,
            strategy_class=classes[req.strategy],
            strategy_params=_build_params(req),
            plot=req.plot,
            period=req.period,
        )
        result["executed_at"] = datetime.now().isoformat(timespec="seconds")
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测失败: {e}")


@router.post("/portfolio")
def run_portfolio(req: PortfolioRequest):
    """同步"独立回测"组合 (2026-07-31 起, 实际语义改名 run_independent_loop)。

    ⚠️ 注意: 这是"每只股独立回测"取均值, 不是真组合回测!
    - 每只股都从 100% 资金 (req.cash) 开始
    - 适用于: 评估"策略在多只股上的平均表现"
    - 不适用于: 真实"一篮子资金调仓"场景

    如需真组合回测, 请调 /basket 端点。
    """
    from backtest.runner import run_independent_loop as _run_indep
    from backtest.strategies import SmaCrossStrategy, MomentumStrategy
    classes = {"sma": SmaCrossStrategy, "momentum": MomentumStrategy}
    codes = [c.strip() for c in req.codes.split(",") if c.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="codes 不能为空")
    if req.strategy not in classes:
        raise HTTPException(status_code=400, detail=f"未知策略: {req.strategy}")

    params = (
        {"fast": req.fast, "slow": req.slow}
        if req.strategy == "sma" else {"lookback": req.lookback}
    )

    try:
        df = _run_indep(
            codes=codes, start=req.start, end=req.end,
            adjust_type=req.adjust, initial_cash=req.cash,
            strategy_class=classes[req.strategy],
            strategy_params=params, plot=False,
        )
        items = df.to_dict(orient="records") if not df.empty else []
        summary = {}
        if items:
            pnl_pcts = [x.get("pnl_pct", 0) for x in items]
            summary = {
                "count": len(items),
                "avg_pnl_pct": round(sum(pnl_pcts) / len(pnl_pcts), 2),
                "median_pnl_pct": round(sorted(pnl_pcts)[len(pnl_pcts) // 2], 2),
                "win_rate": round(sum(1 for p in pnl_pcts if p > 0) / len(pnl_pcts) * 100, 1),
                "mode": "independent_loop",
            }
        return {
            "data": {
                "items": items,
                "summary": summary,
                "executed_at": datetime.now().isoformat(timespec="seconds"),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"独立回测失败: {e}")


@router.post("/independent-loop")
def run_independent_loop(req: PortfolioRequest):
    """/portfolio 的语义显式版本 (2026-07-31 新增, 行为一致)。"""
    return run_portfolio(req)


@router.post("/basket")
def run_basket(req: PortfolioRequest):
    """真组合回测 (2026-07-31 P1-11 新增) - 一篮子资金等权分仓 + 加总净值。

    与 /portfolio 区别:
      - /portfolio: 每只股 100% 资金, 取平均
      - /basket:    资金均分 N 份进 N 只股, 加总净值与收益
    """
    from backtest.runner import run_basket as _run_basket
    from backtest.strategies import SmaCrossStrategy, MomentumStrategy
    classes = {"sma": SmaCrossStrategy, "momentum": MomentumStrategy}
    codes = [c.strip() for c in req.codes.split(",") if c.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="codes 不能为空")
    if req.strategy not in classes:
        raise HTTPException(status_code=400, detail=f"未知策略: {req.strategy}")

    params = (
        {"fast": req.fast, "slow": req.slow}
        if req.strategy == "sma" else {"lookback": req.lookback}
    )

    try:
        result = _run_basket(
            codes=codes, start=req.start, end=req.end,
            adjust_type=req.adjust, initial_cash=req.cash,
            strategy_class=classes[req.strategy],
            strategy_params=params, plot=False,
        )
        result["executed_at"] = datetime.now().isoformat(timespec="seconds")
        result["mode"] = "basket"
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"真组合回测失败: {e}")


@router.post("/async")
def run_backtest_async(req: BacktestRequest):
    """异步单股回测,适合批量场景"""
    from backtest.runner import run_backtest as _run
    from backtest.strategies import (
        SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy, MaAlignmentStrategy,
    )
    classes = {
        "sma": SmaCrossStrategy,
        "momentum": MomentumStrategy,
        "buy_hold": BuyHoldStrategy,
        "ma_alignment": MaAlignmentStrategy,
    }
    if req.strategy not in classes:
        raise HTTPException(status_code=400, detail=f"未知策略: {req.strategy}")

    def _do():
        return _run(
            code=req.code, start=req.start, end=req.end,
            adjust_type=req.adjust, initial_cash=req.cash,
            strategy_class=classes[req.strategy],
            strategy_params=_build_params(req),
            plot=req.plot,
            period=req.period,
        )

    tid = task_manager.submit(f"回测-{req.code}", _do)
    return {"task_id": tid}