"""
统一配置中心 —— 回测、特征、数据源、交易成本、模型更新全部在此管理。
所有硬编码数值必须通过此文件引用，禁止在业务代码中写死。
"""

from dataclasses import dataclass, field
from typing import Literal


# ============================================================================
# 1. 回测核心配置
# ============================================================================

@dataclass
class BacktestConfig:
    """Walk-Forward 回测参数"""

    # 时间范围
    train_start: str = "20180101"  # 训练数据起点（至少5年）
    backtest_start: str = "20230601"  # 回测起点（第一个预测日）
    backtest_end: str = "20240601"  # 回测终点

    # Walk-Forward 模式
    retrain_frequency: Literal["monthly", "quarterly"] = "monthly"
    min_train_window_years: int = 5

    # 两种切分模式
    # "fast" = 固定训练集 2018-2022 → 测试集 2023.06-2024.06（快速迭代用）
    # "rolling" = 逐月滚动窗口（最终验收用）
    validation_mode: Literal["fast", "rolling"] = "fast"

    # 选股
    top_n_select: int = 10  # 精选模式
    top_n_diversified: int = 20  # 分散模式
    hold_days: int = 3  # 持有交易日数（T+3）

    # 股票池
    indices: list[str] = field(default_factory=lambda: ["CSI300", "CSI500", "CSI1000"])
    min_daily_volume: float = 50_000_000  # 日均成交额 > 5000万
    min_daily_turnover: float = 0.01  # 日均换手率 > 1%
    exclude_st: bool = True
    exclude_suspended: bool = True
    exclude_limit_up: bool = True  # 当日涨停排除（买不到）
    exclude_limit_down: bool = True  # 当日跌停排除
    exclude_new_listing_days: int = 60  # 上市不足60日排除
    survivorship_bias_control: bool = True  # True=历史成分股快照, False=当前成分股（仅快速调试）


# ============================================================================
# 2. 交易成本配置
# ============================================================================

@dataclass
class TradingCostConfig:
    """A股 T+1 实际交易成本（2023年8月印花税减半后）"""

    stamp_duty: float = 0.0005  # 印花税（卖出单向，0.05%）
    commission: float = 0.00025  # 佣金（买卖双向，万2.5）
    transfer_fee: float = 0.00001  # 过户费（买卖双向，可忽略）

    # 滑点（按指数分级）
    slippage_csi300: float = 0.0002  # 沪深300大盘股
    slippage_csi500: float = 0.0005  # 中证500
    slippage_csi1000: float = 0.0010  # 中证1000小票

    @property
    def total_roundtrip_bps(self) -> float:
        """一买一卖总成本（基点）"""
        return (self.stamp_duty + self.commission * 2 + self.transfer_fee * 2) * 10000

    def get_slippage(self, index: str) -> float:
        """根据指数返回对应滑点"""
        mapping = {
            "CSI300": self.slippage_csi300,
            "CSI500": self.slippage_csi500,
            "CSI1000": self.slippage_csi1000,
        }
        return mapping.get(index, self.slippage_csi500)


# ============================================================================
# 3. 验收标准（9项指标阈值）
# ============================================================================

@dataclass
class AcceptanceCriteria:
    """三组9项指标的全部阈值"""

    # 第一组：核心收益
    top10_min_return: float = 0.005  # 精选10只 tradable_return > 0.5%
    top10_target_return: float = 0.01  # > 1.0%
    top20_min_return: float = 0.003  # 分散20只 > 0.3%
    top20_target_return: float = 0.007  # > 0.7%
    win_rate_min: float = 0.55  # 胜率 > 55%
    win_rate_target: float = 0.58  # > 58%
    ic_min: float = 0.03  # IC > 0.03
    ic_target: float = 0.05  # > 0.05

    # 第二组：风险控制
    daily_stability_min: float = 0.60  # > 60%交易日跑赢基准
    daily_stability_target: float = 0.70
    max_drawdown_limit: float = -0.15  # > -15%
    max_drawdown_target: float = -0.10
    turnover_max: float = 0.30  # < 30%
    turnover_target: float = 0.20

    # 第三组：Alpha 真伪
    segmented_min_passing: int = 2  # 3个子区间中≥2个胜率>55%
    segmented_target_passing: int = 3
    beta_neutral_min: float = 0.05  # 下跌市超额 > 5%
    beta_neutral_target: float = 0.08
    # 零和博弈：Bottom 10 必须显著差于 Top 10


# ============================================================================
# 4. 特征工程开关
# ============================================================================

@dataclass
class FeatureConfig:
    """控制启用哪些特征组（方便对比实验）"""

    # 第一梯队
    enable_northbound: bool = True  # 北向资金
    enable_margin: bool = True  # 融资融券
    enable_active_buy: bool = True  # 主动买卖占比

    # 第二梯队
    enable_volume_ratio: bool = True  # 量比
    enable_ma_convergence: bool = True  # 均线粘合度+位置
    enable_sector_momentum: bool = True  # 行业动量

    # 第三梯队
    enable_retail_sentiment: bool = False  # 散户舆情（MVP先关）
    enable_anomaly_check: bool = True  # 异常检验（防出货陷阱）
    enable_share_unlock: bool = True  # 限售股解禁

    # 第六类（1b阶段启用）
    enable_policy_signal: bool = False  # 政策事件（Phase 1b）


# ============================================================================
# 5. 数据源配置
# ============================================================================

@dataclass
class DataSourceConfig:
    """数据源优先级与参数"""

    tushare_token: str = ""  # 从环境变量 TUSHARE_TOKEN 读取
    data_source_priority: list[str] = field(
        default_factory=lambda: ["tushare", "akshare", "tencent", "sina"]
    )
    tencent_enabled: bool = False  # 格式不稳定，默认关闭
    sina_enabled: bool = False  # 2023年大改版，默认关闭

    # 缓存
    cache_ttl_daily: int = 3600  # 日线缓存1小时
    cache_ttl_minute: int = 300  # 分钟线缓存5分钟

    # 回填控制
    backfill_sleep_seconds: float = 1.0  # 每次API调用间隔（防封IP）
    backfill_chunk_months: int = 3  # 每次回填3个月数据


# ============================================================================
# 6. 模型与推理配置（远期预留）
# ============================================================================

@dataclass
class ModelConfig:
    """模型训练与部署参数"""

    # 训练
    model_type: Literal["lgb", "xgb", "lambdarank"] = "lgb"
    lgb_params: dict = field(default_factory=lambda: {
        "objective": "regression",  # 回归目标；不稳定可切 'lambdarank'
        "metric": "rmse",
        "boosting_type": "gbdt",
        "num_leaves": 63,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "n_estimators": 500,
        "early_stopping_rounds": 50,
    })

    # 推理模式（Phase 2）
    inference_mode: Literal["local", "api", "hybrid"] = "local"

    # 模型更新策略
    retrain_schedule: Literal["monthly", "weekly"] = "monthly"
    recalibrate_schedule: Literal["daily", "weekly"] = "daily"
    feature_freshness_max_hours: int = 24


# ============================================================================
# 全局单例
# ============================================================================

backtest_cfg = BacktestConfig()
trading_cost_cfg = TradingCostConfig()
acceptance_cfg = AcceptanceCriteria()
feature_cfg = FeatureConfig()
datasource_cfg = DataSourceConfig()
model_cfg = ModelConfig()


def load_tushare_token() -> str:
    """从环境变量或 .env 文件加载 Tushare token"""
    import os
    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv("TUSHARE_TOKEN", "")
        except ImportError:
            pass
    datasource_cfg.tushare_token = token
    return token


# ============================================================================
# FastAPI 兼容 Settings（用于 app/main.py）
# ============================================================================

@dataclass
class Settings:
    """FastAPI应用配置"""
    app_name: str = "StockPredictor API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/stock.db"
    redis_url: str = "redis://localhost:6379/0"
    tushare_token: str = ""
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    api_key_header: str = "X-API-Key"
    rate_limit_per_minute: int = 60
    ml_model_dir: str = "./models_output"
    coreml_export_dir: str = "./coreml_models"

    def __post_init__(self):
        import os
        token = os.getenv("TUSHARE_TOKEN", "")
        if not token:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                token = os.getenv("TUSHARE_TOKEN", "")
            except ImportError:
                pass
        self.tushare_token = token


settings = Settings()

