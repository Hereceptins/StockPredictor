"""
LightGBM 模型训练与预测 —— 支持回归和 LambdaRank 两种目标。

训练模式：
- "fast"：固定训练集（2018-2022）→ 测试集（2023.06-2024.06），快速迭代用
- "rolling"：逐月滚动窗口，最终验收用
"""

from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.config import model_cfg, backtest_cfg
from app.ml.features import FeatureEngine


class StockPredictor:
    """
    股票排序模型。

    对每只股票预测其3日收益率，然后横截面排序选出Top N。
    """

    def __init__(self, objective: Literal["regression", "lambdarank"] = "regression"):
        self.objective = objective
        self._model = None
        self._scaler: StandardScaler | None = None
        self._feature_names: list[str] = []
        self._feature_engine = FeatureEngine()

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        X_valid: pd.DataFrame | None = None,
        y_valid: pd.Series | None = None,
        group: pd.Series | None = None,
        group_valid: pd.Series | None = None,
    ) -> "StockPredictor":
        """
        训练 LightGBM 模型。

        Args:
            X: 特征矩阵
            y: 目标变量（3日收益率）
            X_valid: 验证集特征（用于早停）
            y_valid: 验证集目标
            group: 训练集分组（LambdaRank 需要，每日数据为一组）
            group_valid: 验证集分组
        """
        import lightgbm as lgb

        # 标准化
        self._scaler = StandardScaler()
        X_scaled = pd.DataFrame(
            self._scaler.fit_transform(X),
            columns=X.columns,
            index=X.index,
        )
        # 标准化后clip（此时所有特征在同一尺度，统一截断合理）
        X_scaled = X_scaled.clip(lower=-5, upper=5)
        self._feature_names = list(X.columns)

        # 配置参数
        params = model_cfg.lgb_params.copy()
        if self.objective == "lambdarank":
            params["objective"] = "lambdarank"
            params["metric"] = "ndcg"

        # 构建 Dataset
        if X_valid is not None and y_valid is not None:
            X_valid_scaled = pd.DataFrame(
                self._scaler.transform(X_valid),
                columns=X.columns,
                index=X_valid.index,
            )
            valid_sets = [lgb.Dataset(
                X_valid_scaled, label=y_valid,
                group=group_valid.values if group_valid is not None else None,
            )]
            valid_names = ["valid"]
            callbacks = [
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=0),
            ]
        else:
            valid_sets = None
            valid_names = None
            callbacks = []
            # 没有验证集时移除早停参数
            params.pop("early_stopping_rounds", None)

        train_set = lgb.Dataset(
            X_scaled, label=y,
            group=group.values if group is not None else None,
        )

        self._model = lgb.train(
            params=params,
            train_set=train_set,
            valid_sets=valid_sets,
            valid_names=valid_names,
            num_boost_round=params.get("n_estimators", 500),
            callbacks=callbacks,
        )

        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """预测收益率"""
        if self._model is None or self._scaler is None:
            raise RuntimeError("模型尚未训练。请先调用 .fit()")
        X_scaled = self._scaler.transform(X[self._feature_names])
        return self._model.predict(X_scaled)

    def get_feature_importance(self) -> pd.DataFrame:
        """获取特征重要性"""
        if self._model is None:
            raise RuntimeError("模型尚未训练。")
        importance = self._model.feature_importance(importance_type="gain")
        return pd.DataFrame({
            "feature": self._feature_names,
            "importance": importance,
        }).sort_values("importance", ascending=False)


def prepare_training_data(
    stock_data: dict[str, pd.DataFrame],
    target_date: date,
    train_start: date,
    train_end: date,
    feature_engine: FeatureEngine | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    准备单个月份的训练/预测数据。

    Args:
        stock_data: {stock_code: price_df} 所有股票的完整价格数据
        target_date: 目标预测日期（回测中的"当前月"）
        train_start: 训练数据起始日期
        train_end: 训练数据结束日期

    Returns:
        X_train, y_train, groups（LambdaRank 需要的日期分组）
    """
    if feature_engine is None:
        feature_engine = FeatureEngine()

    # 遍历所有股票，计算特征
    # 注意：这里需要N只股票×M天的数据，数据量可能很大
    # 实际实现中需要分批处理和缓存
    pass  # 函数签名预留，完整实现在 backtest.py 中调用
