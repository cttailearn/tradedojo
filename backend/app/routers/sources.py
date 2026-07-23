"""
数据源管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from fetcher import fetcher_manager

router = APIRouter(prefix="/api/sources", tags=["数据源"], dependencies=[Depends(require_admin)])


class SwitchRequest(BaseModel):
    name: str


@router.get("")
def list_sources():
    """列出所有数据源及其状态"""
    return {
        "primary": fetcher_manager.get_primary(),
        "sources": fetcher_manager.list_sources(),
    }


@router.post("/switch")
def switch_source(req: SwitchRequest):
    """切换主源"""
    if not fetcher_manager.set_primary(req.name):
        raise HTTPException(status_code=400, detail=f"未知数据源: {req.name}")
    return {
        "primary": fetcher_manager.get_primary(),
        "message": f"已切换到 {req.name}",
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