"""新闻情绪 API"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.api.v1.schemas.stock import KLineItem
from app.api.v1.schemas.common import APIResponse
from app.services.sentiment_service import SentimentService

router = APIRouter()


@router.get("/{code}", response_model=APIResponse)
async def get_stock_sentiment(
    code: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取个股相关新闻情绪"""
    service = SentimentService(db)
    items, total = await service.get_stock_news(code, page, size)
    return APIResponse(data={"items": items, "total": total, "page": page})


@router.get("/market-overview", response_model=APIResponse)
async def get_market_sentiment(
    db: AsyncSession = Depends(get_db),
):
    """获取市场整体情绪指数"""
    service = SentimentService(db)
    overview = await service.get_market_overview()
    return APIResponse(data=overview)


@router.get("/hot-news", response_model=APIResponse)
async def get_hot_news(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取热门财经新闻"""
    service = SentimentService(db)
    items, total = await service.get_hot_news(page, size)
    return APIResponse(data={"items": items, "total": total, "page": page})
