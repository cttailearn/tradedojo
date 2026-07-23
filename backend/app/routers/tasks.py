"""
数据更新任务 API
- 提交后台任务(更新股票列表 / K线 / 指数 / 全量)
- 查询任务状态 + 实时日志尾部
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_admin
from app.models import UpdateTaskRequest
from app.task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["数据更新"], dependencies=[Depends(require_admin)])


@router.post("/update")
def trigger_update(req: UpdateTaskRequest, progress_callback=None):
    """触发一个后台更新任务"""
    task = req.task
    adjust = req.adjust
    days = req.days
    workers = req.workers
    full_init = req.full_init
    limit = req.limit

    def _run_kline_daily():
        from updater.parallel_updater import ParallelKlineUpdater
        u = ParallelKlineUpdater(max_workers=workers)
        return u.update_all(adjust=adjust, days_back=days, only_active=True)

    def _run_stock_list():
        from updater.parallel_updater import ParallelKlineUpdater
        u = ParallelKlineUpdater()
        return u.update_stock_list()

    def _run_index():
        from updater.parallel_updater import ParallelKlineUpdater
        u = ParallelKlineUpdater()
        return u.update_index()

    def _run_enrich():
        from updater.parallel_updater import ParallelKlineUpdater
        u = ParallelKlineUpdater()
        return u.enrich_stock_info(enrich_workers=workers, profile_limit=limit)

    def _run_daily_smart():
        from updater.parallel_updater import ParallelKlineUpdater
        u = ParallelKlineUpdater(max_workers=workers)
        return u.update_daily_smart_only(adjust=adjust, days_back=days)

    runners = {
        "kline_daily": ("K线(日)", _run_kline_daily),
        "stock_list": ("股票列表", _run_stock_list),
        "index": ("主要指数", _run_index),
        "enrich": ("信息丰富", _run_enrich),
        "daily_smart": ("智能增量", _run_daily_smart),
    }
    if task not in runners:
        raise HTTPException(status_code=400, detail=f"未知任务: {task},可选 {list(runners)}")

    name, runner = runners[task]
    task_id = task_manager.submit(name, runner)
    return {"task_id": task_id, "task_name": name, "status": "pending"}


@router.get("/{task_id}")
def get_task(task_id: str):
    rec = task_manager.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在")
    return rec


@router.get("")
def list_tasks(limit: int = Query(20, ge=1, le=100)):
    return {"items": task_manager.list_recent(limit=limit)}


@router.post("/reset-checkpoint")
def reset_checkpoint(payload: dict, _user=Depends(require_admin)):
    """重置某个任务的断点(慎用!)"""
    from updater.checkpoint import CheckpointManager
    task_name = payload.get("task")
    if not task_name:
        raise HTTPException(status_code=400, detail="缺少参数 task")
    cp = CheckpointManager(task_name)
    cp.reset()
    return {"message": f"已重置断点: {task_name}"}