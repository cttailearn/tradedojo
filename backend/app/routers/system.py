"""
系统状态 / 数据缺失检查 / 任务日志 API
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_admin
from db.database import query_all, query_one, table_count

router = APIRouter(prefix="/api/system", tags=["系统"], dependencies=[Depends(require_admin)])


@router.get("/status")
def status():
    """各表行数 + K线按复权类型分布 + 最近 5 条更新日志"""
    tables = ["stock_list", "kline_daily", "index_daily", "update_log", "admin_user"]
    table_info = {}
    for t in tables:
        try:
            table_info[t] = table_count(t)
        except Exception:
            table_info[t] = 0

    kline_rows = query_all(
        "SELECT adjust_type, COUNT(*), MIN(trade_date), MAX(trade_date) "
        "FROM kline_daily GROUP BY adjust_type"
    )
    kline_by_adjust = [
        {
            "adjust_type": r[0], "count": r[1],
            "first_date": r[2], "last_date": r[3],
        }
        for r in kline_rows
    ]

    # ---- 数据完整性指标(2026-08-05 新增) ----
    stock_total = table_info.get("stock_list", 0)
    stocks_with_kline = 0
    kline_latest_date = None
    kline_updated_at = None
    index_latest_date = None
    try:
        row = query_one(
            "SELECT COUNT(DISTINCT code) FROM kline_daily WHERE adjust_type = 'qfq'"
        )
        stocks_with_kline = int(row[0] or 0) if row else 0
    except Exception:
        pass
    try:
        row = query_one(
            "SELECT MAX(trade_date), MAX(updated_at) FROM kline_daily"
        )
        if row:
            kline_latest_date = row[0]
            kline_updated_at = row[1]
    except Exception:
        pass
    try:
        row = query_one("SELECT MAX(trade_date) FROM index_daily")
        index_latest_date = row[0] if row else None
    except Exception:
        pass

    logs = query_all(
        "SELECT id, task_name, status, affected_rows, start_time, end_time, message "
        "FROM update_log ORDER BY id DESC LIMIT 5"
    )
    recent_logs = [
        {
            "id": r[0], "task_name": r[1], "status": r[2],
            "affected_rows": r[3], "start_time": r[4],
            "end_time": r[5], "message": r[6],
        }
        for r in logs
    ]

    coverage = {
        "stock_total": stock_total,
        "stocks_with_kline": stocks_with_kline,
        "coverage_pct": round(stocks_with_kline * 100 / stock_total, 1)
        if stock_total else 0,
        "kline_latest_date": kline_latest_date,
        "kline_updated_at": kline_updated_at,
        "index_latest_date": index_latest_date,
        "last_success_log": next(
            (r for r in recent_logs if r["status"] == "success"), None
        ),
    }

    return {
        "tables": table_info,
        "kline_by_adjust": kline_by_adjust,
        "coverage": coverage,
        "recent_logs": recent_logs,
        "now": datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/check")
def check_missing():
    """检查数据缺失(不更新)"""
    from updater.parallel_updater import ParallelKlineUpdater
    u = ParallelKlineUpdater()
    return u.check_missing()


@router.get("/logs")
def list_log_files():
    """日志文件列表(供前端在线查看)"""
    from app.config import settings
    if not settings.LOG_DIR.exists():
        return {"items": []}
    items = []
    for f in sorted(settings.LOG_DIR.iterdir(), reverse=True):
        if f.suffix == ".log":
            items.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            })
    return {"items": items}


@router.get("/logs/{name}")
def tail_log(name: str, lines: int = Query(200, ge=10, le=2000)):
    """读取指定日志文件的最后 N 行"""
    from app.config import settings
    # 防止路径穿越
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="非法文件名")
    fp = settings.LOG_DIR / name
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    try:
        # 简单实现:大文件仅读尾部
        with open(fp, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 64 * 1024
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                read_size = min(block, size)
                size -= read_size
                f.seek(size)
                data = f.read(read_size) + data
        text = data.decode("utf-8", errors="ignore")
        tail = "\n".join(text.splitlines()[-lines:])
        return {"name": name, "lines": tail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))