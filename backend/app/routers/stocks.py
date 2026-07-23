"""
股票列表 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from db.database import query_all, query_one
from app.deps import require_admin

router = APIRouter(prefix="/api/stocks", tags=["股票"], dependencies=[Depends(require_admin)])


@router.get("")
def list_stocks(
    keyword: Optional[str] = Query(None, description="按代码或名称模糊查询"),
    market: Optional[str] = Query(None, description="SH / SZ / BJ"),
    industry: Optional[str] = Query(None, description="行业"),
    is_active: Optional[int] = Query(1, description="1=在市 0=退市"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """分页查询股票列表"""
    where = []
    params = []
    if keyword:
        where.append("(code LIKE ? OR name LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    if market:
        where.append("market = ?")
        params.append(market)
    if industry:
        where.append("industry = ?")
        params.append(industry)
    if is_active is not None:
        where.append("is_active = ?")
        params.append(is_active)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = query_one(f"SELECT COUNT(*) FROM stock_list {where_sql}", params)[0]
    offset = (page - 1) * page_size
    rows = query_all(
        f"""SELECT code, name, industry, market, list_date, is_active
            FROM stock_list {where_sql}
            ORDER BY code ASC LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    items = [
        {
            "code": r[0], "name": r[1], "industry": r[2],
            "market": r[3], "list_date": r[4], "is_active": r[5],
        }
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/markets")
def list_markets():
    rows = query_all(
        "SELECT market, COUNT(*) FROM stock_list "
        "WHERE is_active=1 GROUP BY market ORDER BY market"
    )
    return {"items": [{"market": r[0], "count": r[1]} for r in rows]}


@router.get("/industries")
def list_industries():
    rows = query_all(
        "SELECT industry, COUNT(*) FROM stock_list "
        "WHERE is_active=1 AND industry IS NOT NULL AND industry != '' "
        "GROUP BY industry ORDER BY count DESC"
    )
    return {"items": [{"industry": r[0], "count": r[1]} for r in rows]}


@router.get("/{code}")
def stock_detail(code: str):
    """股票详情 + 该股的 K线统计"""
    row = query_one(
        "SELECT code, name, full_code, industry, market, list_date, is_active "
        "FROM stock_list WHERE code = ?",
        (code,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")

    kline_count = query_one(
        "SELECT COUNT(*) FROM kline_daily WHERE code = ?", (code,)
    )[0]
    first_last = query_one(
        "SELECT MIN(trade_date), MAX(trade_date) FROM kline_daily WHERE code = ?",
        (code,),
    )

    return {
        "code": row[0], "name": row[1], "full_code": row[2],
        "industry": row[3], "market": row[4], "list_date": row[5],
        "is_active": row[6],
        "kline_count": kline_count,
        "kline_first_date": first_last[0],
        "kline_last_date": first_last[1],
    }


@router.delete("/{code}")
def deactivate_stock(code: str):
    """标记股票为退市(is_active=0),不真正删除"""
    affected = query_one(
        "SELECT changes() FROM (UPDATE stock_list SET is_active=0 WHERE code=?)",
        (code,),
    )
    if not affected or affected[0] == 0:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")
    return {"message": f"已标记 {code} 为退市"}