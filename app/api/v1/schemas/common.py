"""通用Pydantic响应模型"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """统一API响应格式"""
    code: int = 0
    message: str = "success"
    data: Any = None
    timestamp: int | None = None
    disclaimer: str = "本数据仅供研究参考，不构成投资建议"


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class DateRangeParams(BaseModel):
    """日期范围"""
    start: str = Field(..., description="起始日期 YYYYMMDD")
    end: str = Field(..., description="结束日期 YYYYMMDD")
