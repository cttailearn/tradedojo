"""
数据源管理 API
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from fetcher import fetcher_manager
from db.database import get_conn

logger = logging.getLogger("app.sources")

router = APIRouter(prefix="/api/sources", tags=["数据源"], dependencies=[Depends(require_admin)])


class SwitchRequest(BaseModel):
    name: str
    # 是否重置该数据源已有的 checkpoint(2026-07-31 P1-14 修复)
    reset_checkpoint: bool = True


@router.get("")
def list_sources():
    """列出所有数据源及其状态"""
    return {
        "primary": fetcher_manager.get_primary(),
        "sources": fetcher_manager.list_sources(),
    }


@router.post("/switch")
def switch_source(req: SwitchRequest):
    """切换主源。

    2026-07-31 P1-14 修复: 切到不同的数据源时, 默认清掉所有 checkpoint,
    避免"老源完成 + 新源跳过"的 silent 错误。管理员可传 reset_checkpoint=False 关闭此行为。
    """
    old_primary = fetcher_manager.get_primary()
    if not fetcher_manager.set_primary(req.name):
        raise HTTPException(status_code=400, detail=f"未知数据源: {req.name}")

    reset_info = None
    if req.reset_checkpoint and old_primary != req.name:
        try:
            with get_conn() as conn:
                # 删除所有 checkpoint_* 表的完成记录(失败的重试也清)
                cur = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name LIKE 'checkpoint_%'"
                )
                tables = [r[0] for r in cur.fetchall()]
                total_deleted = 0
                for t in tables:
                    cur2 = conn.execute(f"DELETE FROM {t}")
                    total_deleted += cur2.rowcount
            reset_info = {
                "reset_tables": len(tables),
                "deleted_rows": total_deleted,
            }
            logger.warning(
                f"[Sources] 主源 {old_primary} → {req.name},清掉 {len(tables)} 个 "
                f"checkpoint 表共 {total_deleted} 行记录,下次更新将全量重拉"
            )
        except Exception as e:
            logger.error(f"[Sources] 清 checkpoint 失败: {e}")
            reset_info = {"error": str(e)}

    return {
        "primary": fetcher_manager.get_primary(),
        "old_primary": old_primary,
        "message": f"已切换到 {req.name}",
        "checkpoint_reset": reset_info,
    }


@router.post("/test/{name}")
def test_source(name: str):
    """测试某个源(轻量级,只拉股票列表)"""
    return fetcher_manager.test_source(name)


@router.post("/test-all")
def test_all_sources():
    """测试所有源"""
    sources = fetcher_manager.list_sources()
    results = []
    for s in sources:
        results.append(fetcher_manager.test_source(s["name"]))
    return {"results": results}