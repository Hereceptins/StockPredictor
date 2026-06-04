"""涨跌停复盘 + 龙虎榜 API"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.api.v1.schemas.common import APIResponse
from app.services.board_service import BoardService

router = APIRouter()


@router.get("/limit-up-down", response_model=APIResponse)
async def get_limit_up_down(
    date: str = Query(..., description="日期 YYYYMMDD"),
    db: AsyncSession = Depends(get_db),
):
    """获取某日涨跌停列表"""
    service = BoardService(db)
    result = await service.get_limit_up_down(date)
    return APIResponse(data=result)


@router.get("/limit-up-down/{code}", response_model=APIResponse)
async def get_stock_limit_history(
    code: str,
    start: str = Query(..., description="起始日期"),
    end: str = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
):
    """获取个股涨跌停历史"""
    service = BoardService(db)
    result = await service.get_stock_limit_history(code, start, end)
    return APIResponse(data=result)


@router.get("/dragon-tiger", response_model=APIResponse)
async def get_dragon_tiger(
    date: str = Query(..., description="日期 YYYYMMDD"),
    db: AsyncSession = Depends(get_db),
):
    """获取某日龙虎榜"""
    service = BoardService(db)
    result = await service.get_dragon_tiger(date)
    return APIResponse(data=result)


@router.get("/dragon-tiger/{code}", response_model=APIResponse)
async def get_stock_dragon_tiger(
    code: str,
    start: str = Query(..., description="起始日期"),
    end: str = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
):
    """获取个股龙虎榜历史"""
    service = BoardService(db)
    result = await service.get_stock_dragon_tiger(code, start, end)
    return APIResponse(data=result)
