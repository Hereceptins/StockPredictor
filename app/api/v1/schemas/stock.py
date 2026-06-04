"""股票相关 Pydantic schemas"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# 股票搜索
# ============================================================================

class StockSearchResult(BaseModel):
    code: str = Field(..., description="Tushare代码 e.g. 000001.SZ")
    name: str = Field(..., description="股票名称")
    market: str = Field(..., description="SH/SZ/BJ")
    industry: str | None = Field(None, description="申万一级行业")
    list_date: str | None = Field(None, description="上市日期")


class StockSearchResponse(BaseModel):
    items: list[StockSearchResult]
    total: int
    page: int
    size: int


# ============================================================================
# 股票详情
# ============================================================================

class StockDetail(BaseModel):
    code: str
    name: str
    market: str
    industry: str | None
    list_date: str | None
    latest_price: float | None
    latest_change: float | None
    latest_change_pct: float | None
    market_cap: float | None = Field(None, description="总市值（亿元）")
    pe: float | None = Field(None, description="市盈率")
    pb: float | None = Field(None, description="市净率")
    total_shares: float | None = Field(None, description="总股本（万股）")
    circulating_shares: float | None = Field(None, description="流通股本（万股）")


# ============================================================================
# K线数据
# ============================================================================

class KLineItem(BaseModel):
    date: str = Field(..., description="交易日期 YYYYMMDD")
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None
    turnover_rate: float | None = Field(None, description="换手率%")
    pct_change: float | None = Field(None, description="涨跌幅%")


class KLineResponse(BaseModel):
    code: str
    period: str
    adjust: str
    items: list[KLineItem]


# ============================================================================
# 批量行情
# ============================================================================

class BatchQuoteRequest(BaseModel):
    codes: list[str] = Field(..., min_length=1, max_length=100)


class QuoteItem(BaseModel):
    code: str
    name: str
    latest_price: float | None
    change: float | None
    change_pct: float | None
    volume: float | None
    amount: float | None
