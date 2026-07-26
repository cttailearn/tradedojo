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
        f"""SELECT code, name, industry, market, list_date, is_active,
                   last_enriched_at
            FROM stock_list {where_sql}
            ORDER BY code ASC LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    # 批量查 K 线汇总(一次 SQL,避免 N+1)
    codes = [r[0] for r in rows]
    kline_map = {}
    if codes:
        placeholders = ",".join(["?"] * len(codes))
        for kr in query_all(
            f"SELECT code, COUNT(*), MAX(trade_date) "
            f"FROM kline_daily WHERE code IN ({placeholders}) GROUP BY code",
            codes,
        ):
            kline_map[kr[0]] = {"count": kr[1], "last_date": kr[2]}

    items = []
    for r in rows:
        code, name, industry, market, list_date, is_active, last_enriched_at = r
        k = kline_map.get(code, {"count": 0, "last_date": None})
        # 计算完整度打分(0~4):4 个维度是否就绪
        score = 0
        score += 1 if (industry and str(industry).strip()) else 0
        score += 1 if list_date else 0
        score += 1 if k["count"] > 0 else 0
        score += 1 if last_enriched_at else 0
        items.append({
            "code": code, "name": name, "industry": industry,
            "market": market, "list_date": list_date, "is_active": is_active,
            # 完整度字段
            "kline_count": k["count"],
            "kline_last_date": k["last_date"],
            "has_industry": bool(industry and str(industry).strip()),
            "has_list_date": bool(list_date),
            "has_kline": k["count"] > 0,
            "last_enriched_at": last_enriched_at,
            "integrity_score": score,    # 0=缺 1=缺基础 2=基础齐 3=含 K线 4=全
        })
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