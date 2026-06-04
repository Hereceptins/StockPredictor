"""
SQLAlchemy ORM 模型 —— 与 iOS SwiftData 模型对应
"""

from datetime import date as date_type, datetime

from sqlalchemy import (
    String, Float, Integer, Date, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


# ============================================================================
# 股票基本信息
# ============================================================================

class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String(10), primary_key=True, comment="股票代码 e.g. 000001.SZ")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="股票名称")
    market: Mapped[str] = mapped_column(String(5), nullable=False, comment="SH/SZ/BJ")
    industry: Mapped[str | None] = mapped_column(String(50), comment="申万一级行业")
    list_date: Mapped[date_type | None] = mapped_column(Date, comment="上市日期")
    total_shares: Mapped[float | None] = mapped_column(Float, comment="总股本(万)")
    circulating_shares: Mapped[float | None] = mapped_column(Float, comment="流通股本(万)")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    klines: Mapped[list["DailyKLine"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="stock", cascade="all, delete-orphan")


# ============================================================================
# 日K线
# ============================================================================

class DailyKLine(Base):
    __tablename__ = "daily_kline"
    __table_args__ = (
        UniqueConstraint("code", "trade_date"),
        Index("idx_kline_code_date", "code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), ForeignKey("stocks.code"), nullable=False)
    trade_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float | None] = mapped_column(Float)
    turnover_rate: Mapped[float | None] = mapped_column(Float, comment="换手率%")
    pct_change: Mapped[float | None] = mapped_column(Float, comment="涨跌幅%")
    adjust_factor: Mapped[float] = mapped_column(Float, default=1.0, comment="复权因子")

    stock: Mapped["Stock"] = relationship(back_populates="klines")


# ============================================================================
# AI预测
# ============================================================================

class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("idx_pred_code_date", "code", "base_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), ForeignKey("stocks.code"), nullable=False)
    base_date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="预测基准日")
    target_date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="预测目标日(T+3)")
    direction: Mapped[str] = mapped_column(String(5), nullable=False, comment="up/down/flat")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, comment="置信度0~1")
    predicted_return: Mapped[float | None] = mapped_column(Float, comment="预测收益率")
    upper_bound: Mapped[float | None] = mapped_column(Float, comment="预测区间上限")
    lower_bound: Mapped[float | None] = mapped_column(Float, comment="预测区间下限")
    signal_tags: Mapped[str | None] = mapped_column(String(200), comment="JSON信号标签列表")
    model_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    actual_direction: Mapped[str | None] = mapped_column(String(5), comment="实际方向（事后填充）")
    actual_return: Mapped[float | None] = mapped_column(Float, comment="实际收益率")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock: Mapped["Stock"] = relationship(back_populates="predictions")


# ============================================================================
# 多因子评分
# ============================================================================

class MultiFactorScore(Base):
    __tablename__ = "multi_factor_scores"
    __table_args__ = (
        UniqueConstraint("code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    momentum_score: Mapped[float | None] = mapped_column(Float)
    value_score: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    technical_score: Mapped[float | None] = mapped_column(Float)
    overall_score: Mapped[float | None] = mapped_column(Float)


# ============================================================================
# 新闻情绪
# ============================================================================

class NewsSentiment(Base):
    __tablename__ = "news_sentiment"
    __table_args__ = (
        Index("idx_news_code", "code", "publish_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    news_id: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(50))
    publish_time: Mapped[datetime] = mapped_column(DateTime)
    sentiment_label: Mapped[str] = mapped_column(String(10), comment="positive/negative/neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, comment="-1.0 ~ 1.0")
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================================
# 涨跌停+龙虎榜
# ============================================================================

class LimitUpDown(Base):
    __tablename__ = "limit_up_down"
    __table_args__ = (UniqueConstraint("code", "trade_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    limit_type: Mapped[str] = mapped_column(String(5), comment="up/down")
    limit_time: Mapped[str | None] = mapped_column(String(8), comment="封板时间 HH:MM:SS")
    open_limit: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否一字板")
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1)


class DragonTiger(Base):
    __tablename__ = "dragon_tiger"
    __table_args__ = (UniqueConstraint("code", "trade_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), comment="上榜原因")
    buy_amount: Mapped[float | None] = mapped_column(Float)
    sell_amount: Mapped[float | None] = mapped_column(Float)
    net_amount: Mapped[float | None] = mapped_column(Float)
    seats_detail: Mapped[str | None] = mapped_column(Text, comment="JSON席位明细")


# ============================================================================
# 用户
# ============================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apple_user_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    email: Mapped[str | None] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active: Mapped[datetime | None] = mapped_column(DateTime)


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"
    __table_args__ = (UniqueConstraint("user_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================================
# 模型版本
# ============================================================================

class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_name", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    accuracy: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
