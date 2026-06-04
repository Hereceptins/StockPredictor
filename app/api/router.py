"""API v1 主路由聚合"""

from fastapi import APIRouter

from app.api.v1 import stocks, kline, predictions, sentiment, board

api_router = APIRouter()

api_router.include_router(stocks.router, prefix="/stocks", tags=["股票"])
api_router.include_router(kline.router, prefix="/stocks", tags=["K线"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["预测"])
api_router.include_router(sentiment.router, prefix="/sentiment", tags=["情绪"])
api_router.include_router(board.router, prefix="/board", tags=["复盘"])
