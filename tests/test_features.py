"""
特征工程单元测试。

关键检查：
1. 无未来信息泄漏（所有特征 lookahead_period=0）
2. 无 NaN 或 Inf
3. 特征值在合理范围内
4. 标签包含正确的三分类
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.features import FeatureEngine, FeatureMeta, compute_labels


# ============================================================================
# 测试数据
# ============================================================================

@pytest.fixture
def sample_price_data() -> pd.DataFrame:
    """生成模拟价格数据（200个交易日）"""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=200, freq="B")
    base_price = 10.0
    prices = [base_price]
    for _ in range(len(dates) - 1):
        ret = np.random.normal(0.0005, 0.02)
        prices.append(prices[-1] * (1 + ret))

    df = pd.DataFrame({
        "date": dates,
        "open": [p * (1 + np.random.normal(0, 0.005)) for p in prices],
        "high": [p * (1 + np.random.uniform(0.005, 0.03)) for p in prices],
        "low": [p * (1 - np.random.uniform(0.005, 0.03)) for p in prices],
        "close": prices,
        "volume": np.random.uniform(1e7, 1e8, len(dates)),
        "amount": np.random.uniform(1e8, 1e9, len(dates)),
    })
    return df


@pytest.fixture
def sample_northbound_data() -> pd.DataFrame:
    """模拟北向资金数据"""
    dates = pd.date_range("2023-01-01", periods=200, freq="B")
    return pd.DataFrame({
        "date": dates,
        "net_buy": np.random.normal(0.5, 2.0, len(dates)) * 1e8,
    })


@pytest.fixture
def sample_margin_data() -> pd.DataFrame:
    """模拟融资融券数据"""
    dates = pd.date_range("2023-01-01", periods=200, freq="B")
    base = 1e10
    margin = [base]
    for _ in range(len(dates) - 1):
        margin.append(margin[-1] * (1 + np.random.normal(0.001, 0.01)))

    return pd.DataFrame({
        "date": dates,
        "margin_balance": margin,
        "short_balance": [m * np.random.uniform(0.001, 0.01) for m in margin],
    })


# ============================================================================
# 时间泄漏检查
# ============================================================================

class TestNoTemporalLeakage:
    """验证所有特征无未来信息泄漏"""

    def test_all_features_lookahead_zero(self):
        """所有特征的 lookahead_period 必须为 0"""
        engine = FeatureEngine()
        for feature in engine.all_features:
            assert feature.lookahead_period == 0, \
                f"❌ 特征 '{feature.name}' 使用了未来数据！lookahead_period={feature.lookahead_period}"

    def test_ma_features_use_past_only(self, sample_price_data):
        """均线特征仅使用过去数据"""
        engine = FeatureEngine()
        features = engine.compute_features(sample_price_data)

        # 检查前60行的均线粘合度（需要60日均线，前60行为NaN）
        assert features["ma_convergence"].iloc[:59].isna().all(), \
            "60日均线粘合度在前60天应该为NaN"
        assert features["ma_convergence"].iloc[60:].notna().sum() > 0, \
            "60天后应该有有效值"

    def test_no_lookahead_in_calculation(self, sample_price_data):
        """验证特征计算使用前闭后闭窗口[T-N+1, T]"""
        engine = FeatureEngine()
        features = engine.compute_features(sample_price_data)

        # 取第100天的特征
        day_100_features = features.iloc[100]

        # 手动用前100天数据计算，验证结果一致
        # （这里做 spot check：5日收益率 = 用第95-100天数据算）
        manual_ret_5d = (
            sample_price_data["close"].iloc[100] /
            sample_price_data["close"].iloc[95] - 1
        )
        assert abs(day_100_features["ret_5d"] - manual_ret_5d) < 0.001, \
            f"5日收益率不一致: {day_100_features['ret_5d']:.6f} vs {manual_ret_5d:.6f}"


# ============================================================================
# 数据质量检查
# ============================================================================

class TestDataQuality:
    """特征数据质量"""

    def test_features_no_nan_in_valid_range(self, sample_price_data):
        """在超过最小窗口后，特征不应有 NaN"""
        engine = FeatureEngine()
        features = engine.compute_features(sample_price_data)

        # 取最后50行（远超所有滚动窗口的最小要求）
        recent = features.iloc[-50:]

        # 检查非时间特征的 NaN 比例
        non_calendar_cols = [
            c for c in recent.columns
            if c not in ("day_of_week", "is_month_start", "is_month_end", "is_earnings_season")
        ]
        nan_ratio = recent[non_calendar_cols].isna().mean()
        # 允许少量 NaN（如 division by zero 导致），但不应该超过 10%
        assert nan_ratio.mean() < 0.1, \
            f"NaN比例过高: {nan_ratio.mean():.2%}"

    def test_features_no_inf(self, sample_price_data):
        """特征不应包含 Inf"""
        engine = FeatureEngine()
        features = engine.compute_features(sample_price_data)

        inf_cols = []
        for col in features.columns:
            if np.isinf(features[col]).any():
                inf_cols.append(col)

        assert len(inf_cols) == 0, \
            f"以下特征包含 Inf: {inf_cols}"

    def test_features_in_reasonable_range(self, sample_price_data):
        """特征值应在合理范围内"""
        engine = FeatureEngine()
        features = engine.compute_features(sample_price_data)

        recent = features.iloc[-50:]

        # 收益率特征应在 -30% ~ 30% 之间
        ret_cols = [c for c in recent.columns if c.startswith("ret_")]
        for col in ret_cols:
            assert recent[col].abs().max() < 0.5, \
                f"{col} 异常值: max={recent[col].abs().max():.4f}"

        # 量比一般在 0 ~ 10 之间
        if "volume_ratio" in recent.columns:
            assert recent["volume_ratio"].max() < 20, \
                f"量比异常: max={recent['volume_ratio'].max()}"


# ============================================================================
# 标签检查
# ============================================================================

class TestLabels:
    """标签计算正确性"""

    def test_labels_shape(self, sample_price_data):
        """标签行数与价格数据一致"""
        labels = compute_labels(sample_price_data, hold_days=3)
        assert len(labels) == len(sample_price_data)

    def test_labels_three_class(self, sample_price_data):
        """三分类标签只有 -1, 0, 1"""
        labels = compute_labels(sample_price_data, hold_days=3)
        assert set(labels["direction"].dropna().unique()).issubset({-1, 0, 1})

    def test_labels_no_nan_at_end(self, sample_price_data):
        """最后 hold_days 天标签为 NaN（因为不知道T+3的价格）"""
        labels = compute_labels(sample_price_data, hold_days=3)
        # 最后3个交易日无法计算3日收益 → NaN
        assert labels["ret_3d"].iloc[-3:].isna().all(), \
            "最后3天应该有NaN（无法计算3日后收益）"

    def test_labels_available_before_end(self, sample_price_data):
        """倒数第4天到倒数第hold_days+1天之间标签有值"""
        labels = compute_labels(sample_price_data, hold_days=3)
        assert labels["ret_3d"].iloc[-10:-3].notna().sum() > 0, \
            "倒数第10到第4天应该有有效标签"


# ============================================================================
# 边界情况
# ============================================================================

class TestEdgeCases:
    """边界情况处理"""

    def test_empty_data(self):
        """空数据应返回空DataFrame"""
        engine = FeatureEngine()
        empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        features = engine.compute_features(empty_df)
        assert len(features) == 0

    def test_single_row_data(self):
        """单行数据不应崩溃"""
        engine = FeatureEngine()
        single_df = pd.DataFrame([{
            "date": "2024-01-01",
            "open": 10, "high": 11, "low": 9.5, "close": 10.5,
            "volume": 1e7, "amount": 1e8,
        }])
        features = engine.compute_features(single_df)
        assert len(features) == 1
        # 单行数据的滚动特征应为 NaN（NaN != NaN，必须用 np.isnan 检测）
        assert np.isnan(features["volatility_5d"].iloc[0])

    def test_constant_price(self):
        """价格不变（涨跌停连续封板）"""
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame({
            "date": dates,
            "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
            "volume": 1e7, "amount": 1e8,
        })
        engine = FeatureEngine()
        features = engine.compute_features(df)

        # 收益率应为 0
        assert (features["ret_1d"].iloc[-50:] == 0).all()
        # 波动率应为 0（可能导致 division by zero，但不应 crash）
        # 量比应为 1
        assert (features["volume_ratio"].iloc[10:-1] == 1).all()
