"""
K线查询 API(数据库只读)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from db.database import execute, query_all, query_one
from app.deps import require_admin

router = APIRouter(prefix="/api/kline", tags=["K线"], dependencies=[Depends(require_admin)])


@router.get("")
def query_kline(
    code: str = Query(..., description="股票代码,例如 000001"),
    adjust: str = Query("qfq", description="复权方式: qfq / hfq"),
    period: int = Query(240, description="K线周期: 240=日线, 30/60=分钟, 10080=周线, 43200=月线"),
    start: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """分页查询 K线(period=240 走 kline_daily,其余走 kline_minute)"""
    if period in (30, 60, 10080, 43200):
        total = query_one(
            "SELECT COUNT(*) FROM kline_minute WHERE code = ? AND period = ?",
            (code, period),
        )[0]
        rows = query_all(
            """SELECT trade_time, open, high, low, close, volume, amount
                FROM kline_minute
                WHERE code = ? AND period = ?
                ORDER BY trade_time ASC LIMIT ? OFFSET ?""",
            (code, period, limit, offset),
        )
        items = [
            {
                "trade_date": r[0][:10], "trade_time": r[0],
                "open": r[1], "high": r[2], "low": r[3],
                "close": r[4], "volume": r[5], "amount": r[6],
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}
    if period != 240:
        raise HTTPException(400, "不支持的周期,可选 240(日) / 30 / 60(分钟) / 10080(周) / 43200(月)")

    where = ["code = ?", "adjust_type = ?"]
    params = [code, adjust]
    if start:
        where.append("trade_date >= ?"); params.append(start)
    if end:
        where.append("trade_date <= ?"); params.append(end)
    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) FROM kline_daily WHERE {where_sql}", params
    )[0]
    rows = query_all(
        f"""SELECT trade_date, open, high, low, close, pre_close,
                   change_amount, pct_change, volume, amount, turnover_rate
            FROM kline_daily WHERE {where_sql}
            ORDER BY trade_date ASC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    items = [
        {
            "trade_date": r[0], "open": r[1], "high": r[2], "low": r[3],
            "close": r[4], "pre_close": r[5], "change_amount": r[6],
            "pct_change": r[7], "volume": r[8], "amount": r[9],
            "turnover_rate": r[10],
        }
        for r in rows
    ]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/indices")
def list_index_kline(
    code: str = Query("sh000001", description="指数代码,例如 sh000001"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
):
    where = ["code = ?"]
    params = [code]
    if start:
        where.append("trade_date >= ?"); params.append(start)
    if end:
        where.append("trade_date <= ?"); params.append(end)
    rows = query_all(
        f"""SELECT trade_date, open, high, low, close, volume, amount
            FROM index_daily WHERE {' AND '.join(where)}
            ORDER BY trade_date ASC LIMIT ?""",
        params + [limit],
    )
    items = [
        {
            "trade_date": r[0], "open": r[1], "high": r[2], "low": r[3],
            "close": r[4], "volume": r[5], "amount": r[6],
        }
        for r in rows
    ]
    return {"items": items}


@router.delete("/{code}")
def delete_kline(code: str, adjust: Optional[str] = None):
    """删除某只股票全部 K线(慎用!)"""
    sql = "DELETE FROM kline_daily WHERE code = ?"
    params = [code]
    if adjust:
        sql += " AND adjust_type = ?"; params.append(adjust)
    # 直接执行 DELETE 用 rowcount 取受影响行数,兼容 SQLite/PostgreSQL(旧写法用 changes())
    deleted = execute(sql, params)
    return {"deleted": deleted}