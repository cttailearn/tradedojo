"""
训练端指数日线查询.
不依赖 admin 鉴权,只用训练端 JWT 即可.
训练叠加图需要的指数对照,例如上证综指/沪深300/创业板指/深证成指.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.deps_train import get_current_train_user
from db.database import query_all
from updater.indices import KEY_INDICES


router = APIRouter(prefix="/api/train/indices", tags=["训练端-指数"])


@router.get("")
def list_indices(
    user: dict = Depends(get_current_train_user),
):
    """支持前端下拉框用的指数清单(代码 + 名称)"""
    return {"items": KEY_INDICES}


@router.get("/kline")
def kline(
    code: str = Query("sh000001", description="指数代码,例如 sh000001"),
    start: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
    user: dict = Depends(get_current_train_user),
):
    """训练端拉指数日线(只读 index_daily)"""
    where = ["code = ?"]
    params = [code]
    if start:
        where.append("trade_date >= ?"); params.append(start)
    if end:
        where.append("trade_date <= ?"); params.append(end)
    rows = query_all(
        f"""SELECT trade_date, open, high, low, close, volume, amount, pct_change
            FROM index_daily WHERE {' AND '.join(where)}
            ORDER BY trade_date ASC LIMIT ?""",
        params + [limit],
    )
    items = [{
        "trade_date":   r[0],
        "open":         r[1],
        "high":         r[2],
        "low":          r[3],
        "close":        r[4],
        "volume":       r[5],
        "amount":       r[6],
        "pct_change":   r[7],
    } for r in rows]
    return {"code": code, "items": items}
