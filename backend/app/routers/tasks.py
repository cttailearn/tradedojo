"""
后台数据更新任务路由 —— 已重构为按数据类型路由。
旧 task 字符串("kline_daily" / "stock_list" / "index" / "enrich" / "daily_smart")
通过 registry.resolve_task() 自动映射到新 TaskType,无需修改前端旧调用。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import require_admin
from app.task_manager import task_manager
from updater.registry import REGISTER, resolve_task
from updater.types import TaskType

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


# ---------- 请求模型 ----------
class UpdateTaskRequest(BaseModel):
    """
    task: TaskType 值或旧别名,均自动识别
    params: 由 registry 中的 ParamModel 校验;旧字段(adjust/days/workers/limit/full_init)
            也会被各 updater 的 ParamModel 兼容接收
    """
    task: str = Field(..., description="任务类型,如 stock_list / index_daily / kline_daily / stock_enrich")
    params: dict = Field(default_factory=dict)


class ResetCheckpointRequest(BaseModel):
    task: str = Field(..., description="要重置断点的任务类型")


# ---------- 触发手动更新 ----------
@router.post("/update", dependencies=[Depends(require_admin)])
def trigger_update(req: UpdateTaskRequest):
    """手动触发一次更新任务"""
    try:
        task_type, defaults = resolve_task(req.task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if task_type not in REGISTER:
        raise HTTPException(status_code=501, detail=f"任务 {task_type.value} 未实现")

    UpdaterCls, ParamModel = REGISTER[task_type]
    # 合并默认参数 + 用户参数(用户覆盖默认)
    merged_params = {**defaults, **(req.params or {})}

    # 字段名兼容:旧字段 full_init -> 强转 full_refresh
    if task_type == TaskType.STOCK_LIST and "full_init" in merged_params:
        merged_params.setdefault("full_refresh", merged_params.pop("full_init"))

    # 用 updater 实例执行(由 task_manager 注入 progress_callback)
    name = f"{task_type.value}_{req.task}"
    try:
        updater = UpdaterCls(merged_params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"参数错误: {e}")

    task_id = task_manager.submit(name, updater.run)
    logger.info(f"提交任务: {name} ({task_id}) task_type={task_type.value}")
    return {"task_id": task_id, "task": task_type.value, "task_type": task_type.value}


# ---------- 任务状态查询 ----------
@router.get("/{task_id}", dependencies=[Depends(require_admin)])
def get_task(task_id: str):
    rec = task_manager.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在")
    return rec


@router.get("", dependencies=[Depends(require_admin)])
def list_recent_tasks(
    task_type: Optional[str] = Query(None, description="按任务类型过滤"),
    limit: int = Query(20, ge=1, le=100),
):
    """按 task_type 过滤最近任务(供前端按 Tab 分组展示)。

    优先从 update_log 表读持久化历史(进程重启不丢);
    内存中的活跃任务作为补充。
    """
    # 1) 持久化历史
    persisted = task_manager.list_persisted(limit=limit, task_name=task_type)
    # 2) 内存活跃任务(运行中/刚完成 30s 内的)
    memory_recs = task_manager.list_recent(limit=limit * 3)
    if task_type:
        memory_recs = [r for r in memory_recs if r["task_name"].startswith(f"{task_type}_")][:limit]
    else:
        memory_recs = memory_recs[:limit]

    # 合并去重(以 task_id 优先,内存中的更"新")
    by_id = {}
    for r in persisted:
        # 给持久化记录一个伪 id 用于前端去重(同 id 可能与内存重复)
        by_id[f"db_{r['id']}"] = {
            "task_id": f"db_{r['id']}",
            "task_name": r["task_name"],
            "status": r["status"],
            "affected_rows": r["affected_rows"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "message": r["message"],
            "progress": {},
            "log_tail": [],
            "source": "update_log",
        }
    for r in memory_recs:
        by_id[r["task_id"]] = {**r, "source": "memory"}
    # 排序: started_at 降序
    items = sorted(
        by_id.values(),
        key=lambda r: r.get("started_at") or "",
        reverse=True,
    )[:limit]
    return {"items": items}


# ---------- 断点重置 ----------
@router.post("/reset-checkpoint", dependencies=[Depends(require_admin)])
def reset_checkpoint(req: ResetCheckpointRequest):
    """
    重置指定任务的 checkpoint(下次更新将重新拉取全部数据)。
    主要用于 stock_list / index_daily / kline_daily。

    修复(2026-08-05): 之前 DELETE FROM checkpoint 引用不存在的表(PG 实际表名是
    checkpoint_<task>), 异常被吞导致"重置成功"但实际未清; 且 _load() 优先恢复
    JSON 快照, 不删快照文件断点永远存在。现统一走 CheckpointManager.reset()
    (删除正确表 + 本地 JSON 快照), 重置真正生效。
    """
    try:
        from updater.checkpoint import CheckpointManager

        task_type, _ = resolve_task(req.task)
        cp = CheckpointManager(task_type.value)
        cp.reset()
        return {
            "task": task_type.value,
            "deleted_rows": 0,
            "reset": True,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
