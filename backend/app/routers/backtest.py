"""
回测 API
- 同步执行(回测通常较快,可阻塞等待)
- 组合回测返回汇总 DataFrame 序列化
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
    return {}


@router.post("")
def run_backtest(req: BacktestRequest):
    """同步单股回测"""
    from backtest.runner import run_backtest as _run
    from backtest.strategies import (
        SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy,
    )
    classes = {
        "sma": SmaCrossStrategy,
        "momentum": MomentumStrategy,
        "buy_hold": BuyHoldStrategy,
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
        )
        result["executed_at"] = datetime.now().isoformat(timespec="seconds")
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测失败: {e}")


@router.post("/portfolio")
def run_portfolio(req: PortfolioRequest):
    """同步组合回测"""
    from backtest.runner import run_portfolio as _run_p
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
        df = _run_p(
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
            }
        return {
            "data": {
                "items": items,
                "summary": summary,
                "executed_at": datetime.now().isoformat(timespec="seconds"),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组合回测失败: {e}")


@router.post("/async")
def run_backtest_async(req: BacktestRequest):
    """异步单股回测,适合批量场景"""
    from backtest.runner import run_backtest as _run
    from backtest.strategies import (
        SmaCrossStrategy, MomentumStrategy, BuyHoldStrategy,
    )
    classes = {
        "sma": SmaCrossStrategy,
        "momentum": MomentumStrategy,
        "buy_hold": BuyHoldStrategy,
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
        )

    tid = task_manager.submit(f"回测-{req.code}", _do)
    return {"task_id": tid}