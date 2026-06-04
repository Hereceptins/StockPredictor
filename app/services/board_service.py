"""复盘服务 —— 涨跌停 + 龙虎榜"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_models import LimitUpDown, DragonTiger


class BoardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_limit_up_down(self, date_str: str) -> dict:
        """获取某日涨跌停列表"""
        stmt = select(LimitUpDown).where(LimitUpDown.trade_date == date_str)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        limit_up = []
        limit_down = []
        for item in items:
            data = {
                "code": item.code,
                "limit_time": item.limit_time,
                "open_limit": item.open_limit,
                "consecutive_days": item.consecutive_days,
            }
            if item.limit_type == "up":
                limit_up.append(data)
            else:
                limit_down.append(data)

        return {
            "date": date_str,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "total_up": len(limit_up),
            "total_down": len(limit_down),
        }

    async def get_stock_limit_history(self, code: str, start: str, end: str) -> dict:
        stmt = (
            select(LimitUpDown)
            .where(
                LimitUpDown.code == code,
                LimitUpDown.trade_date >= start,
                LimitUpDown.trade_date <= end,
            )
            .order_by(LimitUpDown.trade_date.asc())
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        return {
            "code": code,
            "history": [
                {
                    "date": str(i.trade_date),
                    "type": i.limit_type,
                    "time": i.limit_time,
                    "open_limit": i.open_limit,
                    "consecutive_days": i.consecutive_days,
                }
                for i in items
            ],
        }

    async def get_dragon_tiger(self, date_str: str) -> dict:
        """获取某日龙虎榜"""
        stmt = select(DragonTiger).where(DragonTiger.trade_date == date_str)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        import json
        entries = []
        for item in items:
            seats = json.loads(item.seats_detail) if item.seats_detail else []
            entries.append({
                "code": item.code,
                "reason": item.reason,
                "buy_amount": item.buy_amount,
                "sell_amount": item.sell_amount,
                "net_amount": item.net_amount,
                "seats": seats,
            })

        return {"date": date_str, "entries": entries, "total": len(entries)}

    async def get_stock_dragon_tiger(self, code: str, start: str, end: str) -> dict:
        stmt = (
            select(DragonTiger)
            .where(
                DragonTiger.code == code,
                DragonTiger.trade_date >= start,
                DragonTiger.trade_date <= end,
            )
            .order_by(DragonTiger.trade_date.asc())
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        import json
        return {
            "code": code,
            "history": [
                {
                    "date": str(i.trade_date),
                    "reason": i.reason,
                    "buy_amount": i.buy_amount,
                    "sell_amount": i.sell_amount,
                    "net_amount": i.net_amount,
                    "seats": json.loads(i.seats_detail) if i.seats_detail else [],
                }
                for i in items
            ],
        }
