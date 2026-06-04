"""预测相关 Pydantic schemas"""

from datetime import date

from pydantic import BaseModel, Field


class PredictionResult(BaseModel):
    """单股预测结果"""
    code: str
    name: str
    direction: str = Field(..., description="up/down/flat")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0~1")
    predicted_return: float | None = Field(None, description="预测收益率")
    upper_bound: float | None = Field(None, description="预测区间上限")
    lower_bound: float | None = Field(None, description="预测区间下限")
    signal_tags: list[str] | None = Field(None, description="信号标签列表")
    model_version: str = Field(default="1.0.0")


class PredictionHistory(BaseModel):
    """预测历史记录"""
    code: str
    base_date: str
    target_date: str
    direction: str
    confidence: float
    actual_direction: str | None
    actual_return: float | None
    was_correct: bool | None


class PredictionHistoryResponse(BaseModel):
    code: str
    total_predictions: int
    correct_predictions: int
    accuracy_30d: float | None = Field(None, description="近30日准确率")
    accuracy_90d: float | None = Field(None, description="近90日准确率")
    history: list[PredictionHistory]


# ============================================================================
# 多因子评分
# ============================================================================

class MultiFactorScoreResult(BaseModel):
    code: str
    name: str
    overall_score: float = Field(..., ge=0.0, le=100.0)
    momentum_score: float | None
    value_score: float | None
    quality_score: float | None
    sentiment_score: float | None
    technical_score: float | None


# ============================================================================
# 每日精选池
# ============================================================================

class PoolStock(BaseModel):
    rank: int = Field(..., ge=1, description="排名 1-N")
    code: str
    name: str
    industry: str | None
    latest_price: float | None
    latest_change_pct: float | None
    direction: str
    confidence: float
    overall_score: float
    signal_tags: list[str]
    factor_scores: MultiFactorScoreResult | None


class DailyPoolResponse(BaseModel):
    date: str
    total_analyzed: int = Field(..., description="分析股票总数")
    pool: list[PoolStock]
    disclaimer: str = "本精选池由AI模型基于历史数据统计规律生成，不构成荐股或买卖建议"


# ============================================================================
# 模型版本
# ============================================================================

class ModelVersionInfo(BaseModel):
    model_name: str
    version: str
    accuracy: float | None
    download_url: str | None
    is_active: bool
