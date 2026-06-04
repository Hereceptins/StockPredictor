"""新闻情绪服务"""

from datetime import date, timedelta

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_models import NewsSentiment


class SentimentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stock_news(self, code: str, page: int, size: int) -> tuple[list, int]:
        """获取个股相关新闻"""
        stmt = (
            select(NewsSentiment)
            .where(NewsSentiment.code == code)
            .order_by(NewsSentiment.publish_time.desc())
            .limit(size)
            .offset((page - 1) * size)
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        count_stmt = select(func.count()).where(NewsSentiment.code == code)
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        news_list = [
            {
                "title": n.title,
                "source": n.source,
                "sentiment": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "summary": n.summary,
                "url": n.url,
                "published_at": n.publish_time.isoformat() if n.publish_time else None,
            }
            for n in items
        ]

        return news_list, total

    async def get_market_overview(self) -> dict:
        """获取市场整体情绪"""
        # 近1日所有新闻的情绪均分
        cutoff = date.today() - timedelta(days=1)
        stmt = (
            select(NewsSentiment.sentiment_score)
            .where(NewsSentiment.publish_time >= cutoff)
        )
        result = await self.db.execute(stmt)
        scores = [s[0] for s in result.all() if s[0] is not None]

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # 判断情绪偏向
        if avg_score > 0.2:
            bias = "偏乐观"
        elif avg_score < -0.2:
            bias = "偏悲观"
        else:
            bias = "中性"

        return {
            "sentiment_score": round(avg_score, 3),
            "bias": bias,
            "news_count": len(scores),
            "period": "24小时",
        }

    async def get_hot_news(self, page: int, size: int) -> tuple[list, int]:
        """热门新闻（不区分股票）"""
        cutoff = date.today() - timedelta(days=7)
        stmt = (
            select(NewsSentiment)
            .where(NewsSentiment.publish_time >= cutoff)
            .order_by(NewsSentiment.publish_time.desc())
            .limit(size)
            .offset((page - 1) * size)
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        count_stmt = select(func.count()).where(NewsSentiment.publish_time >= cutoff)
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        news_list = [
            {
                "title": n.title,
                "source": n.source,
                "sentiment": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "code": n.code,
                "published_at": n.publish_time.isoformat() if n.publish_time else None,
            }
            for n in items
        ]
        return news_list, total
