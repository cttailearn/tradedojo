"""
Kronos K 线预测 API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.deps import require_admin
from app.services.kronos_service import kronos_service

router = APIRouter(prefix="/api/kronos", tags=["Kronos 预测"], dependencies=[Depends(require_admin)])


class LoadRequest(BaseModel):
    model: str = Field("kronos-mini", description="模型名: kronos-mini / kronos-base")
    device: Optional[str] = Field(None, description="cuda / cpu,默认自动")


class PredictRequest(BaseModel):
    model_config = {"extra": "ignore"}  # 允许前端多传字段(如 model),避免 422

    code: str = Field(..., description="股票代码,如 000001")
    lookback: int = Field(200, ge=30, le=512)
    pred_len: int = Field(30, ge=1, le=120)
    adjust: str = Field("qfq", description="qfq / hfq")
    temperature: float = Field(1.0, ge=0.1, le=2.0)
    top_k: int = Field(0, ge=0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    sample_count: int = Field(1, ge=1, le=10)
    # 回测模式参数
    train_end: Optional[str] = Field(None, description="训练数据截止日(YYYY-MM-DD),开启回测模式")
    compare_actual: bool = Field(False, description="回测模式:是否对比实际值算准确率")


@router.get("/status")
def status():
    """检查 Kronos 状态"""
    return kronos_service.status()


@router.post("/load")
def load_model(req: LoadRequest):
    """加载模型(首次约 1-3 分钟下载)"""
    try:
        return kronos_service.load(model_name=req.model, device=req.device)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:300]}")


@router.post("/predict")
def predict(req: PredictRequest):
    """对指定股票预测未来 K 线(支持回测对比)"""
    try:
        return kronos_service.predict_for_stock(
            code=req.code,
            lookback=req.lookback,
            pred_len=req.pred_len,
            adjust=req.adjust,
            temperature=req.temperature,
            top_k=req.top_k,
            top_p=req.top_p,
            sample_count=req.sample_count,
            train_end=req.train_end,
            compare_actual=req.compare_actual,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:300]}")


@router.post("/unload")
def unload():
    """卸载模型(释放内存)"""
    import gc
    kronos_service._predictor = None
    kronos_service._model_name = None
    kronos_service._device = None
    kronos_service._loaded_at = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    return {"message": "已卸载"}