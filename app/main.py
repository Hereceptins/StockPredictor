"""
StockPredictor API — FastAPI 应用入口

启动: uvicorn app.main:app --reload
文档: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import setup_middleware
from app.core.exceptions import StockPredictorError
from app.models.database import init_db
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化DB，关闭时清理"""
    setup_logging()
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 中间件
setup_middleware(app)

# 路由
app.include_router(api_router, prefix="/api/v1")

# 全局异常处理
@app.exception_handler(StockPredictorError)
async def stock_predictor_exception_handler(request, exc: StockPredictorError):
    return JSONResponse(
        status_code=exc.code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
            "disclaimer": "本数据仅供研究参考，不构成投资建议",
        },
    )


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
