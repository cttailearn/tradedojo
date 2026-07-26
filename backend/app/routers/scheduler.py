"""
定时调度 API —— 已扩展为按数据类型操作
- 兼容旧端点:/status /start /stop /trigger /config /history
- 新端点:  /jobs  /jobs/{task}  /jobs/{task}/trigger
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import require_admin
from app.scheduler import scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["定时调度"])


class _StartCfg(BaseModel):
    time: Optional[str] = None
    tasks: Optional[List[str]] = None
    adjust: Optional[str] = None
    days: Optional[int] = None
    workers: Optional[int] = None


class _JobUpdate(BaseModel):
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    params: Optional[dict] = None


# ----- 旧端点(保留语义) -----
@router.get("/status", dependencies=[Depends(require_admin)])
def get_status():
    return scheduler_service.get_status()


@router.post("/start", dependencies=[Depends(require_admin)])
def start(cfg: Optional[_StartCfg] = None):
    try:
        return scheduler_service.start(cfg.model_dump(exclude_none=True) if cfg else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop", dependencies=[Depends(require_admin)])
def stop():
    return scheduler_service.stop()


@router.post("/trigger", dependencies=[Depends(require_admin)])
def trigger(task: Optional[str] = None):
    """task 为空时触发所有 enabled jobs;传 task 时只触发单个"""
    return scheduler_service.trigger_now(task)


@router.put("/config", dependencies=[Depends(require_admin)])
def update_config(cfg: dict):
    """旧批量配置:支持 time / tasks / adjust / days / workers"""
    try:
        return scheduler_service.update_config(cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history", dependencies=[Depends(require_admin)])
def history(limit: int = Query(10, ge=1, le=50)):
    return {"items": scheduler_service.history[:limit]}


# ----- 新端点 -----
@router.get("/jobs", dependencies=[Depends(require_admin)])
def list_jobs():
    """按数据类型列出所有 jobs(含 cron / enabled / params / last_run)"""
    return scheduler_service.get_status().get("jobs", [])


@router.put("/jobs/{task}", dependencies=[Depends(require_admin)])
def update_job(task: str, body: _JobUpdate):
    """更新单类任务的 cron / 启用 / 参数,即时热生效"""
    try:
        return scheduler_service.update_job(
            task,
            cron=body.cron,
            enabled=body.enabled,
            params=body.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{task}/trigger", dependencies=[Depends(require_admin)])
def trigger_job(task: str):
    r = scheduler_service._trigger_one(task)
    if not r.get("triggered"):
        raise HTTPException(status_code=400, detail=r.get("error"))
    return r
