"""股票信息服务"""

from datetime import date

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_models import Stock, DailyKLine, UserWatchlist


class StockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, page: int = 1, size: int = 20) -> tuple[list, int]:
        """搜索股票（代码或名称）"""
        # 先查数据库
        stmt = select(Stock).where(
            or_(
                Stock.code.contains(query.upper()),
                Stock.name.contains(query),
            )
        ).limit(size).offset((page - 1) * size)

        result = await self.db.execute(stmt)
        items = result.scalars().all()

        # 计数
        count_stmt = select(func.count()).select_from(Stock).where(
            or_(Stock.code.contains(query.upper()), Stock.name.contains(query))
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        return list(items), total

    async def get_detail(self, code: str) -> Stock | None:
        """获取股票详情（含最新行情）"""
        stmt = select(Stock).where(Stock.code == code)
        result = await self.db.execute(stmt)
        stock = result.scalar_one_or_none()

        if stock is None:
            return None

        # 获取最新K线附加到stock（动态属性）
        kline_stmt = (
            select(DailyKLine)
            .where(DailyKLine.code == code)
            .order_by(DailyKLine.trade_date.desc())
            .limit(1)
        )
        kline_result = await self.db.execute(kline_stmt)
        latest = kline_result.scalar_one_or_none()

        if latest:
            stock.latest_price = latest.close
            stock.latest_change = latest.pct_change
            stock.latest_change_pct = latest.pct_change

        return stock

    async def get_indicators(self, code: str, types: list[str], period: str) -> dict:
        """计算技术指标"""
        # 获取最近120个日K线
        stmt = (
            select(DailyKLine)
            .where(DailyKLine.code == code)
            .order_by(DailyKLine.trade_date.desc())
            .limit(120)
        )
        result = await self.db.execute(stmt)
        klines = result.scalars().all()

        if not klines:
            return {"code": code, "indicators": {}}

        closes = [k.close for k in reversed(klines)]
        highs = [k.high for k in reversed(klines)]
        lows = [k.low for k in reversed(klines)]

        indicators = {}
        if "macd" in types:
            indicators["macd"] = self._calc_macd(closes)
        if "kdj" in types:
            indicators["kdj"] = self._calc_kdj(highs, lows, closes)
        if "rsi" in types:
            indicators["rsi"] = {
                "rsi6": self._calc_rsi(closes, 6),
                "rsi12": self._calc_rsi(closes, 12),
                "rsi24": self._calc_rsi(closes, 24),
            }
        if "boll" in types:
            indicators["boll"] = self._calc_boll(closes)

        return {"code": code, "indicators": indicators}

    async def batch_quotes(self, codes: list[str]) -> list[dict]:
        """批量获取最新行情"""
        results = []
        for code in codes:
            stmt = select(Stock).where(Stock.code == code)
            result = await self.db.execute(stmt)
            stock = result.scalar_one_or_none()
            if stock:
                kline_stmt = (
                    select(DailyKLine)
                    .where(DailyKLine.code == code)
                    .order_by(DailyKLine.trade_date.desc())
                    .limit(1)
                )
                kline_result = await self.db.execute(kline_stmt)
                latest = kline_result.scalar_one_or_none()
                results.append({
                    "code": code,
                    "name": stock.name,
                    "latest_price": latest.close if latest else None,
                    "change": latest.pct_change if latest else None,
                    "change_pct": latest.pct_change if latest else None,
                    "volume": latest.volume if latest else None,
                    "amount": latest.amount if latest else None,
                })
        return results

    # ---- 技术指标计算 ----

    @staticmethod
    def _calc_ema(data: list[float], period: int) -> list[float]:
        """指数移动平均"""
        if len(data) < period:
            return [data[-1]] * len(data) if data else []
        k = 2 / (period + 1)
        ema = [sum(data[:period]) / period]
        for price in data[period:]:
            ema.append(price * k + ema[-1] * (1 - k))
        return [ema[0]] * (period - 1) + ema

    @classmethod
    def _calc_macd(cls, closes: list[float]) -> dict:
        ema12 = cls._calc_ema(closes, 12)
        ema26 = cls._calc_ema(closes, 26)
        dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        dea = cls._calc_ema(dif, 9)
        hist = [(d - e) * 2 for d, e in zip(dif, dea)]
        return {"dif": dif[-1] if dif else 0, "dea": dea[-1] if dea else 0, "hist": hist[-1] if hist else 0}

    @staticmethod
    def _calc_kdj(highs: list[float], lows: list[float], closes: list[float], n: int = 9) -> dict:
        if len(closes) < n:
            return {"k": 50, "d": 50, "j": 50}
        low_n = min(lows[-n:])
        high_n = max(highs[-n:])
        rsv = (closes[-1] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50
        # 简化为单点RSV
        return {"k": rsv, "d": rsv, "j": 3 * rsv - 2 * rsv}

    @staticmethod
    def _calc_rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        return 100 - 100 / (1 + avg_gain / avg_loss)

    @staticmethod
    def _calc_boll(closes: list[float], period: int = 20) -> dict:
        if len(closes) < period:
            return {"up": closes[-1], "mid": closes[-1], "down": closes[-1]}
        recent = closes[-period:]
        mid = sum(recent) / period
        var = sum((x - mid) ** 2 for x in recent) / period
        std = var ** 0.5
        return {"up": mid + 2 * std, "mid": mid, "down": mid - 2 * std}
