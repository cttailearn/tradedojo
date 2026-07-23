"""
定时调度 API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_admin
from app.scheduler import scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["定时调度"], dependencies=[Depends(require_admin)])


@router.get("/status")
def get_status():
    """获取调度器当前状态"""
    return scheduler_service.get_status()


@router.post("/start")
def start(config: Optional[dict] = None):
    """
    启动调度器
    body 可选: {time, tasks, adjust, days, workers}
    """
    try:
        return scheduler_service.start(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop")
def stop():
    """停止调度器"""
    return scheduler_service.stop()


@router.put("/config")
def update_config(config: dict):
    """修改配置(支持热更新)"""
    try:
        return scheduler_service.update_config(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/trigger")
def trigger_now():
    """立即触发一次(不等定时)"""
    return scheduler_service.trigger_now()


@router.get("/history")
def history(limit: int = Query(10, ge=1, le=50)):
    """获取最近 N 次运行历史"""
    return {"items": scheduler_service.history[:limit]}