"""AI预测 API 端点"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.api.v1.schemas.prediction import (
    PredictionResult, PredictionHistory, PredictionHistoryResponse,
    MultiFactorScoreResult, PoolStock, DailyPoolResponse, ModelVersionInfo,
)
from app.api.v1.schemas.common import APIResponse
from app.services.prediction_service import PredictionService

router = APIRouter()


# ⚠️ 静态路由必须在参数化路由 `/{code}` 之前定义，否则会被吞掉

@router.get("/daily-pool", response_model=APIResponse)
async def get_daily_pool(
    db: AsyncSession = Depends(get_db),
):
    """获取每日精选池（Top 20）"""
    service = PredictionService(db)
    pool = await service.get_daily_pool()
    stocks = [PoolStock.model_validate(p).model_dump() for p in pool.get("pool", [])]
    return APIResponse(data=stocks)


@router.get("/accuracy-report", response_model=APIResponse)
async def get_accuracy_report(
    db: AsyncSession = Depends(get_db),
):
    """获取模型准确率报告"""
    service = PredictionService(db)
    report = await service.get_accuracy_report()
    return APIResponse(data=report)


# ============================================================================
# 模型版本
# ============================================================================

@router.get("/models/latest-version", response_model=APIResponse)
async def get_latest_model_version(
    db: AsyncSession = Depends(get_db),
):
    """获取最新CoreML模型版本信息"""
    service = PredictionService(db)
    info = await service.get_latest_model_version()
    return APIResponse(data=ModelVersionInfo.model_validate(info).model_dump())


@router.get("/models/download/{model_name}/{version}", response_model=APIResponse)
async def download_model(
    model_name: str,
    version: str,
    db: AsyncSession = Depends(get_db),
):
    """获取CoreML模型下载URL"""
    service = PredictionService(db)
    info = await service.get_model_download(model_name, version)
    return APIResponse(data=info)


# ---- 参数化路由（必须放在静态路由之后） ----

@router.get("/{code}", response_model=APIResponse)
async def get_prediction(
    code: str,
    days: int = Query(5, ge=1, le=30, description="预测天数"),
    db: AsyncSession = Depends(get_db),
):
    service = PredictionService(db)
    result = await service.predict(code, days)
    if result is None:
        return APIResponse(code=404, message=f"股票 {code} 暂无预测数据")
    return APIResponse(data=PredictionResult.model_validate(result).model_dump())


@router.get("/{code}/history", response_model=APIResponse)
async def get_prediction_history(
    code: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    service = PredictionService(db)
    result = await service.get_history(code, days)
    return APIResponse(data=PredictionHistoryResponse.model_validate(result).model_dump())


@router.get("/{code}/multi-factor", response_model=APIResponse)
async def get_multi_factor(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    service = PredictionService(db)
    result = await service.get_multi_factor(code)
    if result is None:
        return APIResponse(code=404, message="暂无评分数据")
    return APIResponse(data=MultiFactorScoreResult.model_validate(result).model_dump())
