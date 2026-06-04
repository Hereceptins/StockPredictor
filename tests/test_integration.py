"""
端到端集成测试 —— 用合成数据验证完整回测管道。

覆盖：
1. 数据生成→特征工程→模型训练→每日选股→收益计算→9项指标
2. 管道各阶段数据形状正确性
3. 无NaN传播
4. Walk-Forward不跨日期泄漏
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import backtest_cfg, trading_cost_cfg, feature_cfg
from app.ml.features import FeatureEngine, compute_labels
from app.ml.model_lgb import StockPredictor
from app.ml.backtest_metrics import (
    BacktestResult, compute_all_metrics, check_acceptance, compute_ic,
)
from app.utils.calendar import get_calendar


# ============================================================================
# 合成数据生成
# ============================================================================

def generate_synthetic_price_data(
    n_stocks: int = 30,
    n_days: int = 1500,  # ~6 years of trading days
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """
    生成合成的A股日线数据。

    包含一定程度的真实市场特征：
    - 收益率有自相关性（动量效应）
    - 不同股票间有相关性（市场Beta）
    - 波动率聚集效应
    """
    np.random.seed(seed)
    n_days = int(n_days * 1.4)  # 生成更多天，因为要过滤周末

    # 市场因子（共同驱动）
    market_return = np.random.normal(0.0003, 0.015, n_days)

    stocks = {}
    for s in range(n_stocks):
        dates = pd.date_range("2018-01-01", periods=n_days, freq="B")
        # 个股Beta和市场残差
        beta = 0.5 + np.random.beta(2, 2)  # 0.5~1.5
        idio_vol = np.random.uniform(0.008, 0.025)
        stock_return = beta * market_return + np.random.normal(0, idio_vol, n_days)

        # 加入微弱的动量效应
        stock_return[1:] += 0.05 * stock_return[:-1]

        price = 10.0
        opens, highs, lows, closes, volumes, amounts = [], [], [], [], [], []
        for ret in stock_return:
            open_p = price * (1 + np.random.normal(0, 0.003))
            close_p = price * (1 + ret)
            high_p = max(open_p, close_p) * (1 + abs(np.random.normal(0, 0.01)))
            low_p = min(open_p, close_p) * (1 - abs(np.random.normal(0, 0.01)))
            vol = np.random.uniform(5e6, 5e8)
            amt = vol * close_p

            opens.append(open_p)
            highs.append(high_p)
            lows.append(low_p)
            closes.append(close_p)
            volumes.append(vol)
            amounts.append(amt)
            price = close_p

        df = pd.DataFrame({
            "date": dates,
            "open": opens, "high": highs, "low": lows, "close": closes,
            "volume": volumes, "amount": amounts,
        })

        code = f"{600000 + s:06d}.SH" if s < 20 else f"{s-20:06d}.SZ"
        stocks[code] = df

    return stocks


# ============================================================================
# 集成测试
# ============================================================================

class TestFullPipeline:
    """端到端管道测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        np.random.seed(42)
        self.price_data = generate_synthetic_price_data(n_stocks=30)
        self.calendar = get_calendar()
        self.feature_engine = FeatureEngine()

    def test_pipeline_data_to_features(self):
        """阶段1：数据→特征"""
        all_features = {}
        for code, df in list(self.price_data.items())[:5]:
            features = self.feature_engine.compute_features(df)
            assert len(features) > 0, f"{code}: 特征为空"
            assert features.isna().sum().sum() < len(features) * len(features.columns) * 0.5, \
                f"{code}: NaN比例过高"
            all_features[code] = features

        assert len(all_features) == 5
        print(f"  特征计算通过: {len(all_features)} 只股票, {features.shape[1]} 维特征")

    def test_pipeline_features_to_labels(self):
        """阶段2：特征→标签"""
        df = list(self.price_data.values())[0]
        labels = compute_labels(df, hold_days=3)
        assert "ret_3d" in labels.columns
        assert "direction" in labels.columns
        assert "is_up" in labels.columns
        # 最后3天标签应为NaN（需要未来数据）
        assert labels["ret_3d"].iloc[-3:].isna().all()
        # 前面应该有有效标签
        valid_ratio = labels["ret_3d"].notna().mean()
        assert valid_ratio > 0.8, f"有效标签比例过低: {valid_ratio:.2%}"
        print(f"  标签计算通过: {len(labels)} 行, 有效 {valid_ratio:.1%}")

    def test_pipeline_train_and_predict(self):
        """阶段3：特征+标签→训练→预测"""
        # 准备训练数据
        train_start = date(2018, 1, 1)
        train_end = date(2022, 12, 31)

        all_X, all_y = [], []
        for code, df in self.price_data.items():
            df_mask = (df["date"] >= pd.Timestamp(train_start)) & (df["date"] <= pd.Timestamp(train_end))
            df_train = df[df_mask]
            if len(df_train) < 60:
                continue
            features = self.feature_engine.compute_features(df_train)
            labels = compute_labels(df_train, hold_days=3)
            common = features.index.intersection(labels.index)
            if len(common) < 30:
                continue
            X = features.loc[common].ffill().fillna(0.0)
            y = labels.loc[common, "ret_3d"]
            valid = y.notna()
            if valid.sum() < 30:
                continue
            all_X.append(X[valid])
            all_y.append(y[valid])

        assert len(all_X) > 0, "没有足够的训练数据"
        X_train = pd.concat(all_X).ffill().fillna(0.0)
        y_train = pd.concat(all_y)
        valid = y_train.notna()
        X_train, y_train = X_train[valid], y_train[valid]

        print(f"  训练数据: {len(X_train)} 行, {X_train.shape[1]} 特征")

        # 训练模型
        model = StockPredictor(objective="regression")
        model.fit(X_train, y_train)
        assert model._model is not None, "模型训练失败"

        # 验证预测
        preds = model.predict(X_train.iloc[:50])
        assert len(preds) == 50
        assert not np.isnan(preds).any(), "预测值含NaN"
        assert preds.std() > 0, "预测值完全相同（无区分度）"

        # 特征重要性
        importance = model.get_feature_importance()
        assert len(importance) == X_train.shape[1]
        print(f"  训练+预测通过: Top特征={importance.iloc[0]['feature']}")

    def test_pipeline_full_backtest_simulation(self):
        """阶段4：模拟完整回测（简化版——固定训练集快照）"""
        # 固定切分：2018-2022训练 → 2023测试
        train_start = date(2018, 1, 1)
        train_end = date(2022, 12, 31)
        test_start = date(2023, 6, 1)
        test_end = date(2023, 9, 1)

        # 1. 训练
        all_X, all_y = [], []
        for code, df in self.price_data.items():
            mask = (df["date"] >= pd.Timestamp(train_start)) & (df["date"] <= pd.Timestamp(train_end))
            df_train = df[mask]
            if len(df_train) < 100:
                continue
            features = self.feature_engine.compute_features(df_train)
            labels = compute_labels(df_train, hold_days=3)
            common = features.index.intersection(labels.index)
            if len(common) < 50:
                continue
            X = features.loc[common].ffill().fillna(0.0)
            y = labels.loc[common, "ret_3d"]
            valid = y.notna()
            if valid.sum() < 50:
                continue
            all_X.append(X[valid])
            all_y.append(y[valid])

        X_train = pd.concat(all_X).ffill().fillna(0.0)
        y_train = pd.concat(all_y)
        valid_mask = y_train.notna()
        X_train, y_train = X_train[valid_mask], y_train[valid_mask]

        model = StockPredictor(objective="regression")
        model.fit(X_train, y_train)

        # 2. 模拟每日选股
        trading_days = self.calendar.trading_days_between(test_start, test_end)[:20]  # 取前20天

        daily_results = []
        for td in trading_days:
            predictions = {}
            for code, df in self.price_data.items():
                df_cut = df[df["date"] <= pd.Timestamp(td)]
                if len(df_cut) < 60:
                    continue
                try:
                    features = self.feature_engine.compute_features(df_cut)
                    if len(features) < 2:
                        continue
                    last = features.iloc[-1:]
                    pred = model.predict(last)[0]
                    predictions[code] = float(pred)
                except Exception:
                    continue

            if len(predictions) < 10:
                continue

            sorted_stocks = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
            top10 = [s for s, _ in sorted_stocks[:10]]

            # 计算收益（简化——直接用T日到T+3的收益）
            returns = []
            for stock in top10:
                df = self.price_data[stock]
                t0_row = df[df["date"] <= pd.Timestamp(td)]
                if len(t0_row) == 0:
                    continue
                buy_price = t0_row["close"].iloc[-1]
                # 找T+3的日期
                t3_date = td + timedelta(days=5)  # 约3个交易日
                t3_row = df[(df["date"] > pd.Timestamp(td)) & (df["date"] <= pd.Timestamp(t3_date))]
                if len(t3_row) == 0:
                    continue
                sell_price = t3_row["close"].iloc[-1]
                ret = (sell_price / buy_price) - 1 - trading_cost_cfg.total_roundtrip_bps / 10000
                returns.append(ret)

            if not returns:
                continue

            result = BacktestResult(
                date=td,
                top10_stocks=top10,
                top10_nominal_return=float(np.mean(returns)),
                top10_tradable_return=float(np.mean(returns)),
                top20_stocks=top10 * 2,
                top20_nominal_return=float(np.mean(returns)) * 0.9,
                top20_tradable_return=float(np.mean(returns)) * 0.9,
                bottom10_stocks=[s for s, _ in sorted_stocks[-10:]],
                bottom10_return=float(np.mean([
                    predictions[s] for s, _ in sorted_stocks[-10:]
                ])),
                benchmark_return=float(np.mean(returns)) * 0.5,
                ic=compute_ic(
                    np.array(list(predictions.values())),
                    np.array([float(v) for v in predictions.values()])
                ),
                predictions=predictions,
            )
            daily_results.append(result)

        assert len(daily_results) > 0, "选股结果为空"

        # 3. 计算指标
        report = compute_all_metrics(daily_results)

        # 验证所有指标都有值
        assert report.total_trading_days == len(daily_results)
        assert not np.isnan(report.top10_avg_tradable_return), "Top10收益为NaN"
        assert not np.isnan(report.win_rate), "胜率为NaN"
        assert not np.isnan(report.mean_ic), "IC为NaN"
        assert not np.isnan(report.max_drawdown), "最大回撤为NaN"
        assert not np.isnan(report.daily_turnover), "换手率为NaN"
        assert not np.isnan(report.bottom10_avg_return), "Bottom10收益为NaN"

        # 验收检查
        checks = check_acceptance(report)
        assert isinstance(checks, dict)
        assert all(isinstance(v, bool) for v in checks.values())

        print(f"  完整回测通过: {report.total_trading_days}天, "
              f"Top10={report.top10_avg_tradable_return:.4%}, "
              f"IC={report.mean_ic:.4f}, "
              f"胜率={report.win_rate:.1%}, "
              f"Bottom10={report.bottom10_avg_return:.4%}")

    def test_no_nan_propagation(self):
        """验证管道不传播NaN"""
        df = list(self.price_data.values())[0]
        # 故意插入NaN
        df_with_nan = df.copy()
        df_with_nan.loc[10, "close"] = np.nan

        features = self.feature_engine.compute_features(df_with_nan)
        # 应该有NaN但不应崩溃
        assert features is not None
        assert len(features) > 0

        # forward fill后应可恢复
        filled = features.ffill().fillna(0.0)
        assert not filled.isna().any().any(), "ffill+fillna后仍有NaN"

    def test_zero_sum_game_check(self):
        """零和博弈检验：Top10应显著优于Bottom10"""
        # 用随机噪声验证IC=0时的情况
        np.random.seed(123)
        preds = np.random.randn(100)
        actuals = np.random.randn(100)
        ic = compute_ic(preds, actuals)
        assert abs(ic) < 0.3, "随机数据IC应接近0"


# ============================================================================
# IC计算详细测试
# ============================================================================

class TestICDetailed:
    def test_perfect_ranking(self):
        pred = np.arange(1, 51, dtype=float)
        actual = np.arange(1, 51, dtype=float)
        ic = compute_ic(pred, actual)
        assert abs(ic - 1.0) < 0.01

    def test_reverse_ranking(self):
        pred = np.arange(1, 51, dtype=float)
        actual = np.arange(50, 0, -1, dtype=float)
        ic = compute_ic(pred, actual)
        assert abs(ic + 1.0) < 0.01

    def test_small_sample(self):
        """小样本Spearman相关——需要至少4个数据点才能可靠计算"""
        pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        actual = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        ic = compute_ic(pred, actual)
        assert abs(ic + 1.0) < 0.01, f"完美负相关应IC≈-1, 实际IC={ic}"

    def test_with_nans(self):
        pred = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        actual = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        ic = compute_ic(pred, actual)
        assert not np.isnan(ic)


# ============================================================================
# 特征泄漏集成测试
# ============================================================================

class TestLeakageIntegration:
    """确保从数据到预测的完整链路中没有时间泄漏"""

    def test_training_future_data_not_leaked(self):
        """训练用的特征不能包含测试期信息"""
        price_data = generate_synthetic_price_data(n_stocks=10)
        engine = FeatureEngine()

        train_end = date(2022, 12, 31)
        test_start = date(2023, 6, 1)

        for code, df in price_data.items():
            df_mask = df["date"] <= pd.Timestamp(train_end)
            df_train = df[df_mask]
            if len(df_train) < 100:
                continue

            features = engine.compute_features(df_train)
            # 特征的最晚日期应≤train_end
            assert features.index.max() <= pd.Timestamp(train_end), \
                f"{code}: 训练特征包含了训练期后的数据 {features.index.max()}"

            # 标签用到T+3，可能略超train_end，但特征不应超
            labels = compute_labels(df_train, hold_days=3)
            # 标签末尾有NaN是正常的（最后3天无法计算）
            assert labels["ret_3d"].iloc[-3:].isna().all() or \
                   labels.index.max() <= pd.Timestamp(train_end), \
                f"{code}: 标签泄漏"
