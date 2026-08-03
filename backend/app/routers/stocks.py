"""
股票列表 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from db.database import execute, query_all, query_one
from app.deps import require_admin

router = APIRouter(prefix="/api/stocks", tags=["股票"], dependencies=[Depends(require_admin)])


@router.get("")
def list_stocks(
    keyword: Optional[str] = Query(None, description="按代码或名称模糊查询"),
    market: Optional[str] = Query(None, description="SH / SZ / BJ"),
    industry: Optional[str] = Query(None, description="行业"),
    is_active: Optional[int] = Query(1, description="1=在市 0=退市"),
    min_integrity: Optional[int] = Query(
        None,
        description="最低数据完整度(0~4):仅返回完整度 >= 此值的股票",
    ),
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

    # 完整度筛选:用子查询算出 4 维度分数(避免每个条件单独 CASE WHEN)
    if min_integrity is not None:
        score_expr = (
            "(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 ELSE 0 END) + "
            "(CASE WHEN list_date IS NOT NULL AND list_date != '' THEN 1 ELSE 0 END) + "
            "(CASE WHEN EXISTS(SELECT 1 FROM kline_daily k WHERE k.code = stock_list.code) "
            "THEN 1 ELSE 0 END) + "
            "(CASE WHEN name IS NOT NULL AND name != '' AND market IS NOT NULL "
            "THEN 1 ELSE 0 END)"
        )
        where.append(f"({score_expr}) >= ?")
        params.append(min_integrity)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = query_one(f"SELECT COUNT(*) FROM stock_list {where_sql}", params)[0]
    offset = (page - 1) * page_size
    rows = query_all(
        f"""SELECT code, name, industry, industry_detail, market, list_date, is_active
            FROM stock_list {where_sql}
            ORDER BY code ASC LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )

    # 批量查 K 线汇总(含成交量、换手率是否有值)
    codes = [r[0] for r in rows]
    kline_map = {}
    if codes:
        placeholders = ",".join(["?"] * len(codes))
        for kr in query_all(
            f"""SELECT code, COUNT(*), MAX(trade_date),
                       SUM(CASE WHEN volume IS NOT NULL AND volume > 0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN turnover_rate IS NOT NULL THEN 1 ELSE 0 END)
                FROM kline_daily
                WHERE code IN ({placeholders}) AND adjust_type = 'qfq'
                GROUP BY code""",
            codes,
        ):
            kline_map[kr[0]] = {
                "count": kr[1], "last_date": kr[2],
                "rows_with_volume": kr[3] or 0,
                "rows_with_turnover": kr[4] or 0,
            }

    items = []
    for r in rows:
        code, name, industry, industry_detail, market, list_date, is_active = r
        k = kline_map.get(code, {
            "count": 0, "last_date": None,
            "rows_with_volume": 0, "rows_with_turnover": 0,
        })

        # 4 个数据维度完整度(0~4,各 1 分)
        has_basic = bool(name and market)               # 基础信息(代码+名称+市场)
        has_industry = bool(industry and str(industry).strip())
        has_list_date = bool(list_date and str(list_date).strip())
        has_kline = k["count"] > 0
        # K线字段完整度(子项)
        kline_volume_ok = k["count"] > 0 and k["rows_with_volume"] >= k["count"] * 0.9
        kline_turnover_ok = k["count"] > 0 and k["rows_with_turnover"] >= k["count"] * 0.9
        # 总分:4 个维度,各 1 分
        integrity_score = sum([has_basic, has_industry, has_list_date, has_kline])

        items.append({
            "code": code, "name": name,
            "industry": industry,
            "industry_detail": industry_detail,
            "market": market, "list_date": list_date, "is_active": is_active,
            # K线汇总
            "kline_count": k["count"],
            "kline_last_date": k["last_date"],
            # 4 维度完整度
            "has_basic": has_basic,
            "has_industry": has_industry,
            "has_list_date": has_list_date,
            "has_kline": has_kline,
            # K 线字段子项(在弹窗内进一步提示)
            "kline_volume_ok": kline_volume_ok,
            "kline_turnover_ok": kline_turnover_ok,
            "integrity_score": integrity_score,  # 0~4
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
        "GROUP BY industry ORDER BY 2 DESC"
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
    # 直接执行 UPDATE 用 rowcount 取受影响行数,兼容 SQLite/PostgreSQL(旧写法用 changes())
    affected = execute(
        "UPDATE stock_list SET is_active=0 WHERE code=?",
        (code,),
    )
    if not affected or affected == 0:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")
    return {"message": f"已标记 {code} 为退市"}