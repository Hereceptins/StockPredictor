"""AI预测服务 —— 含每日精选池生成"""

from datetime import date, timedelta
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_models import Stock, Prediction, MultiFactorScore, ModelVersion


class PredictionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def predict(self, code: str, days: int = 5) -> dict | None:
        """获取单只股票最新预测"""
        stmt = (
            select(Prediction)
            .where(Prediction.code == code)
            .order_by(Prediction.base_date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        pred = result.scalar_one_or_none()

        if pred is None:
            return None

        import json
        tags = json.loads(pred.signal_tags) if pred.signal_tags else []

        return {
            "code": pred.code,
            "name": (await self._get_stock_name(code)),
            "direction": pred.direction,
            "confidence": pred.confidence,
            "predicted_return": pred.predicted_return,
            "upper_bound": pred.upper_bound,
            "lower_bound": pred.lower_bound,
            "signal_tags": tags,
            "model_version": pred.model_version,
        }

    async def get_history(self, code: str, days: int = 30) -> dict:
        """获取预测历史与准确率"""
        cutoff = date.today() - timedelta(days=days)
        stmt = (
            select(Prediction)
            .where(Prediction.code == code, Prediction.base_date >= cutoff)
            .order_by(Prediction.base_date.desc())
        )
        result = await self.db.execute(stmt)
        predictions = result.scalars().all()

        history = []
        correct = 0
        for p in predictions:
            was_correct = None
            if p.actual_direction:
                was_correct = p.direction == p.actual_direction
                if was_correct:
                    correct += 1

            history.append({
                "code": p.code,
                "base_date": p.base_date.isoformat(),
                "target_date": p.target_date.isoformat(),
                "direction": p.direction,
                "confidence": p.confidence,
                "actual_direction": p.actual_direction,
                "actual_return": p.actual_return,
                "was_correct": was_correct,
            })

        total = len(predictions)
        return {
            "code": code,
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy_30d": correct / total if total > 0 else None,
            "accuracy_90d": None,  # TODO
            "history": history,
        }

    async def get_multi_factor(self, code: str) -> dict | None:
        """获取多因子评分"""
        stmt = (
            select(MultiFactorScore)
            .where(MultiFactorScore.code == code)
            .order_by(MultiFactorScore.trade_date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        score = result.scalar_one_or_none()

        if score is None:
            return None

        return {
            "code": code,
            "name": await self._get_stock_name(code),
            "overall_score": score.overall_score or 50,
            "momentum_score": score.momentum_score,
            "value_score": score.value_score,
            "quality_score": score.quality_score,
            "sentiment_score": score.sentiment_score,
            "technical_score": score.technical_score,
        }

    async def get_daily_pool(self) -> dict:
        """获取每日精选池 —— 实时生成（不依赖数据库）"""
        today = date.today()

        try:
            from app.services.pool_generator import get_pool_generator
            gen = get_pool_generator()
            stocks = gen.generate(top_n=20)

            if stocks:
                pool = []
                for i, s in enumerate(stocks):
                    pool.append({
                        "rank": i + 1,
                        "code": s["code"],
                        "name": s["name"],
                        "industry": None,
                        "latest_price": None,
                        "latest_change_pct": None,
                        "direction": s["direction"],
                        "confidence": s["confidence"],
                        "overall_score": s["overall_score"],
                        "signal_tags": s.get("signal_tags", []),
                        "factor_scores": s.get("factor_scores", {}),
                    })

                return {
                    "date": today.isoformat(),
                    "total_analyzed": len(pool),
                    "pool": pool,
                    "source": "live_generator",
                }
        except Exception as e:
            print(f"[Pool] Generator failed: {e}")

        # Fallback: empty
        return {"date": today.isoformat(), "total_analyzed": 0, "pool": []}

    async def get_accuracy_report(self) -> dict:
        """获取模型准确率报告"""
        # 统计最近90天预测准确率
        cutoff = date.today() - timedelta(days=90)
        stmt = (
            select(Prediction)
            .where(Prediction.base_date >= cutoff, Prediction.actual_direction.isnot(None))
        )
        result = await self.db.execute(stmt)
        predictions = result.scalars().all()

        total = len(predictions)
        if total == 0:
            return {"message": "暂无足够的预测数据"}

        correct = sum(1 for p in predictions if p.direction == p.actual_direction)

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": correct / total,
            "period_days": 90,
            "model_version": predictions[0].model_version if predictions else "1.0.0",
        }

    async def get_latest_model_version(self) -> dict:
        stmt = (
            select(ModelVersion)
            .where(ModelVersion.is_active == True)
            .order_by(ModelVersion.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        model = result.scalar_one_or_none()

        return {
            "model_name": model.model_name if model is not None else "StockRankingModel",
            "version": model.version if model is not None else "1.0.0",
            "accuracy": model.accuracy if model is not None else None,
            "download_url": f"/api/v1/models/download/StockRankingModel/{model.version}" if model is not None else None,
            "is_active": model.is_active if model is not None else True,
        }

    async def get_model_download(self, model_name: str, version: str) -> dict:
        stmt = select(ModelVersion).where(
            ModelVersion.model_name == model_name,
            ModelVersion.version == version,
        )
        result = await self.db.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None or not model.file_path:
            return {"error": "Model not found", "download_url": None}

        return {
            "model_name": model_name,
            "version": version,
            "download_url": f"/static/models/{model_name}_{version}.mlpackage",
            "file_hash": model.file_hash,
        }

    async def _get_stock_name(self, code: str) -> str:
        stmt = select(Stock.name).where(Stock.code == code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or code
