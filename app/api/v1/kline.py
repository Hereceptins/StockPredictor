"""K线数据 API 端点"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.api.v1.schemas.stock import KLineItem, KLineResponse
from app.api.v1.schemas.common import APIResponse
from app.services.kline_service import KLineService

router = APIRouter()


@router.get("/{code}/kline", response_model=APIResponse)
async def get_kline(
    code: str,
    period: str = Query("daily", description="daily/weekly/monthly"),
    start: str = Query(..., description="起始日期 YYYYMMDD"),
    end: str = Query(..., description="结束日期 YYYYMMDD"),
    adjust: str = Query("fwd", description="复权类型: fwd(前复权)/bwd(后复权)/none"),
    db: AsyncSession = Depends(get_db),
):
    """获取K线数据"""
    service = KLineService(db)
    items = await service.get_kline(code, period, start, end, adjust)
    return APIResponse(data={
        "code": code,
        "period": period,
        "adjust": adjust,
        "items": [KLineItem.model_validate(item).model_dump() for item in items],
    })
