"""股票相关 API 端点"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.api.v1.schemas.stock import (
    StockSearchResult, StockSearchResponse, StockDetail, QuoteItem, BatchQuoteRequest,
)
from app.api.v1.schemas.common import APIResponse
from app.services.stock_service import StockService

router = APIRouter()


@router.get("/search", response_model=APIResponse)
async def search_stocks(
    q: str = Query(..., min_length=1, description="搜索关键词（代码或名称）"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """搜索股票代码或名称"""
    service = StockService(db)
    items, total = await service.search(q, page, size)
    return APIResponse(data={
        "items": [StockSearchResult.model_validate(i).model_dump() for i in items],
        "total": total,
        "page": page,
        "size": size,
    })


@router.get("/{code}", response_model=APIResponse)
async def get_stock_detail(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取股票详情"""
    service = StockService(db)
    detail = await service.get_detail(code)
    if detail is None:
        return APIResponse(code=404, message=f"股票 {code} 未找到")
    return APIResponse(data=StockDetail.model_validate(detail).model_dump())


@router.get("/{code}/indicators", response_model=APIResponse)
async def get_technical_indicators(
    code: str,
    types: str = Query("macd,kdj,rsi,boll", description="技术指标类型，逗号分隔"),
    period: str = Query("daily", description="周期 daily/weekly/monthly"),
    db: AsyncSession = Depends(get_db),
):
    """获取技术指标"""
    service = StockService(db)
    indicators = await service.get_indicators(code, types.split(","), period)
    return APIResponse(data=indicators)


@router.post("/batch", response_model=APIResponse)
async def batch_quotes(
    req: BatchQuoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量获取实时行情"""
    service = StockService(db)
    quotes = await service.batch_quotes(req.codes)
    return APIResponse(data=[QuoteItem.model_validate(q).model_dump() for q in quotes])
