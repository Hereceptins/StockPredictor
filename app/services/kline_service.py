"""K线数据服务"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_models import DailyKLine


class KLineService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_kline(
        self, code: str, period: str, start: str, end: str, adjust: str
    ) -> list[dict]:
        """获取K线数据"""
        stmt = (
            select(DailyKLine)
            .where(
                DailyKLine.code == code,
                DailyKLine.trade_date >= start,
                DailyKLine.trade_date <= end,
            )
            .order_by(DailyKLine.trade_date.asc())
        )
        result = await self.db.execute(stmt)
        klines = result.scalars().all()

        return [
            {
                "date": str(k.trade_date).replace("-", ""),
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
                "amount": k.amount,
                "turnover_rate": k.turnover_rate,
                "pct_change": k.pct_change,
            }
            for k in klines
        ]
