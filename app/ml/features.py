"""
特征工程 —— A股T+3预测的完整特征计算管道。

所有特征必须遵循"T日收盘时已知信息"原则（无未来信息泄漏）。
特征按三个梯队组织，可通过 FeatureConfig 开关控制。

特征清单（总计约80+维）：
  第一梯队（主信号）：
    - 北向资金：3/5/10日净买入、连续净买入天数、净买入加速率
    - 融资余额：5日变化率、加速度、融券占比
    - 主动买卖占比：5日滚动占比、加速度

  第二梯队（辅助）：
    - 量比：量比>2持续天数、量价一致性
    - 均线粘合度 + 位置：均线标准差、相对250日均线位置
    - 行业动量：行业5/10日收益排名、行业ETF资金流

  第三梯队（独特Alpha）：
    - 散户舆情：股吧负面情绪占比（可选）
    - 异常检验：异常度（防出货陷阱）
    - 限售股解禁：距解禁日天数、解禁市值占比

  基础特征（始终启用）：
    - 收益类：1/3/5/10/20日收益率、波动率
    - 量价类：换手率、振幅、成交额占比
    - 时间类：星期几、月初/月末、财报季
"""

from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd

from app.config import feature_cfg


# ============================================================================
# 特征元数据（用于时间泄漏检查）
# ============================================================================

class FeatureMeta:
    """特征元数据 —— 每个特征声明其数据窗口，便于自动化防泄漏检查"""

    def __init__(self, name: str, lookahead_period: int = 0,
                 category: str = "", description: str = ""):
        """
        Args:
            name: 特征名称
            lookahead_period: 超前天数——必须始终为0！
                              (特征只能用到T日数据，不能用到T+1/T+2/T+3)
            category: 特征类别（用于分组分析）
            description: 特征描述
        """
        self.name = name
        self.lookahead_period = lookahead_period
        self.category = category
        self.description = description


# ============================================================================
# 特征工程主类
# ============================================================================

class FeatureEngine:
    """
    特征工程引擎。

    输入：单只股票的价格历史 + 可选的外部数据（北向资金/融资等）
    输出：特征DataFrame，每行一个交易日，列=所有特征
    """

    def __init__(self, calendar=None, industry_returns=None, industry_map=None):
        """
        Args:
            calendar: TradingCalendar 实例（用于日期计算）
            industry_returns: DataFrame, date×industry 的日收益率矩阵（预计算）
            industry_map: dict, ts_code→industry_name
        """
        self._calendar = calendar
        self._feature_metas: list[FeatureMeta] = []
        self._industry_returns = industry_returns
        self._industry_map = industry_map or {}
        self._current_stock_code = ""
        self._register_features()

    def _register_features(self) -> None:
        """注册所有特征及其元数据"""
        # 基础收益特征
        for n in [1, 3, 5, 10, 20]:
            self._feature_metas.append(FeatureMeta(
                f"ret_{n}d", category="return",
                description=f"{n}日收益率"
            ))

        # 波动率
        for n in [5, 10, 20]:
            self._feature_metas.append(FeatureMeta(
                f"volatility_{n}d", category="risk",
                description=f"{n}日波动率（收益率标准差）"
            ))

        # 量价特征
        for name, desc in [
            ("turnover_rate", "换手率"),
            ("amplitude", "振幅"),
            ("volume_ratio", "量比"),
            ("volume_ratio_gt2_days", "量比>2持续天数"),
            ("volume_price_corr", "量价相关性（5日）"),
        ]:
            self._feature_metas.append(FeatureMeta(
                name, category="volume_price", description=desc
            ))

        # 均线特征
        for name, desc in [
            ("ma_convergence", "均线粘合度（5/10/20/60日均线标准差/均价）"),
            ("ma_position", "粘合位置（价格/250日均线）"),
            ("ma_divergence_speed", "均线发散速度"),
        ]:
            self._feature_metas.append(FeatureMeta(
                name, category="ma", description=desc
            ))

        # 第一梯队：北向资金
        if feature_cfg.enable_northbound:
            for name, desc in [
                ("northbound_net_3d", "北向资金3日累计净买入"),
                ("northbound_net_5d", "北向资金5日累计净买入"),
                ("northbound_net_10d", "北向资金10日累计净买入"),
                ("northbound_consecutive_days", "北向资金连续净买入天数"),
                ("northbound_acceleration", "北向资金净买入加速率（5日变化率）"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="northbound", description=desc
                ))

        # 第一梯队：融资余额
        if feature_cfg.enable_margin:
            for name, desc in [
                ("margin_balance_change_5d", "融资余额5日变化率"),
                ("margin_acceleration", "融资余额加速度（二阶导）"),
                ("short_ratio", "融券余额/融资余额比"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="margin", description=desc
                ))

        # 第一梯队：主动买卖占比
        if feature_cfg.enable_active_buy:
            for name, desc in [
                ("active_buy_ratio_5d", "主动买入占比（5日滚动）"),
                ("active_buy_ratio_change", "主动买入占比变化加速度"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="active_buy", description=desc
                ))

        # 第二梯队：行业动量
        if feature_cfg.enable_sector_momentum:
            for name, desc in [
                ("sector_ret_5d", "所属行业5日收益率"),
                ("sector_ret_10d", "所属行业10日收益率"),
                ("sector_rank", "行业收益率排名（分位数）"),
                ("sector_etf_flow_5d", "行业ETF资金流5日"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="sector", description=desc
                ))

        # 第三梯队：异常检验
        if feature_cfg.enable_anomaly_check:
            for name, desc in [
                ("anomaly_score", "异常度 = (当日涨幅-5日均涨幅)/5日涨幅标准差"),
                ("pump_and_dump_risk", "出货陷阱风险（异常度>2且量比>3=强烈回避）"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="anomaly", description=desc
                ))

        # 第三梯队：限售股解禁
        if feature_cfg.enable_share_unlock:
            for name, desc in [
                ("days_to_unlock", "距解禁日天数"),
                ("unlock_market_value_ratio", "解禁市值占流通市值比"),
            ]:
                self._feature_metas.append(FeatureMeta(
                    name, category="unlock", description=desc
                ))

        # 时间特征
        for name, desc in [
            ("day_of_week", "星期几（0=周一）"),
            ("is_month_start", "是否月初前3个交易日"),
            ("is_month_end", "是否月末最后3个交易日"),
            ("is_earnings_season", "是否财报季（3-4月，8-10月）"),
        ]:
            self._feature_metas.append(FeatureMeta(
                name, category="calendar", description=desc
            ))

    @property
    def all_features(self) -> list[FeatureMeta]:
        return self._feature_metas

    @property
    def feature_names(self) -> list[str]:
        return [f.name for f in self._feature_metas]

    # ========================================================================
    # 特征计算
    # ========================================================================

    def compute_features(
        self,
        price_df: pd.DataFrame,
        northbound_df: pd.DataFrame | None = None,
        margin_df: pd.DataFrame | None = None,
        active_buy_df: pd.DataFrame | None = None,
        sector_df: pd.DataFrame | None = None,
        unlock_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        计算所有特征。

        Args:
            price_df: 价格数据，必须有 date, open, high, low, close, volume, amount, turnover_rate 列
            northbound_df: 北向资金数据 date, net_buy
            margin_df: 融资融券数据 date, margin_balance, short_balance
            active_buy_df: 主动买卖数据 date, active_buy_ratio
            sector_df: 行业数据 date, sector_code, sector_ret
            unlock_df: 解禁数据 date, unlock_shares, unlock_market_value

        Returns:
            特征 DataFrame，index=date，columns=所有特征名
        """
        df = price_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")

        features = pd.DataFrame(index=df.index)

        # --- 基础量价特征 ---
        self._compute_return_features(df, features)
        self._compute_volatility_features(df, features)
        self._compute_volume_features(df, features)
        self._compute_ma_features(df, features)

        # --- 第一梯队 ---
        if feature_cfg.enable_northbound and northbound_df is not None:
            self._compute_northbound_features(northbound_df, features)
        if feature_cfg.enable_margin and margin_df is not None:
            self._compute_margin_features(margin_df, features)
        if feature_cfg.enable_active_buy and active_buy_df is not None:
            self._compute_active_buy_features(active_buy_df, features)

        # --- 第二梯队 ---
        if feature_cfg.enable_sector_momentum and self._industry_returns is not None:
            self._compute_sector_features_from_precomputed(df, features)

        # --- 第三梯队 ---
        if feature_cfg.enable_anomaly_check:
            self._compute_anomaly_features(df, features)
        if feature_cfg.enable_share_unlock and unlock_df is not None:
            self._compute_unlock_features(unlock_df, features)

        # --- 时间特征 ---
        self._compute_calendar_features(features)

        # 去除无穷值（clip移到StandardScaler之后，避免截断量比等大值特征）
        features = features.replace([np.inf, -np.inf], np.nan)

        return features

    # ========================================================================
    # 基础特征
    # ========================================================================

    def _compute_return_features(self, df: pd.DataFrame, features: pd.DataFrame) -> None:
        """收益率特征"""
        close = df["close"]
        for n in [1, 3, 5, 10, 20]:
            features[f"ret_{n}d"] = close.pct_change(n)

    def _compute_volatility_features(self, df: pd.DataFrame, features: pd.DataFrame) -> None:
        """波动率特征"""
        ret_1d = df["close"].pct_change()
        for n in [5, 10, 20]:
            features[f"volatility_{n}d"] = ret_1d.rolling(n).std()

    def _compute_volume_features(self, df: pd.DataFrame, features: pd.DataFrame) -> None:
        """量价特征"""
        # 换手率（如果源数据有）
        if "turnover_rate" in df.columns:
            features["turnover_rate"] = df["turnover_rate"]

        # 振幅
        features["amplitude"] = (df["high"] - df["low"]) / df["close"].shift(1)

        # 量比 = 当日成交量 / 5日均量
        vol_ma5 = df["volume"].rolling(5).mean()
        features["volume_ratio"] = df["volume"] / vol_ma5

        # 量比>2持续天数
        volume_ratio_gt2 = (features["volume_ratio"] > 2).astype(int)
        features["volume_ratio_gt2_days"] = (
            volume_ratio_gt2.groupby(
                (volume_ratio_gt2 != volume_ratio_gt2.shift()).cumsum()
            ).cumcount() + 1
        ) * volume_ratio_gt2

        # 量价一致性（5日量比与5日收益率的相关性）
        ret_1d = df["close"].pct_change()
        features["volume_price_corr"] = (
            features["volume_ratio"]
            .rolling(5)
            .corr(ret_1d)  # 直接用ret_1d，不用.mean()
        )

    def _compute_ma_features(self, df: pd.DataFrame, features: pd.DataFrame) -> None:
        """均线粘合度 + 位置特征"""
        close = df["close"]

        # 计算各均线
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        ma250 = close.rolling(250).mean()

        # 粘合度 = 各均线/std / 均价（归一化，不同价格区间可比较）
        # 注意：必须所有均线都在有效期内才计算（skipna=False 防止用部分均线凑数）
        ma_values = pd.concat([ma5, ma10, ma20, ma60], axis=1)
        ma_valid = ma_values.notna().all(axis=1)
        ma_mean = ma_values.where(ma_valid).mean(axis=1, skipna=False)
        ma_std = ma_values.where(ma_valid).std(axis=1, skipna=False)
        features["ma_convergence"] = ma_std / ma_mean

        # 粘合位置 = 价格 / 250日均线
        features["ma_position"] = close / ma250

        # 发散速度 = 粘合度的一阶差分
        features["ma_divergence_speed"] = features["ma_convergence"].diff(5)

    # ========================================================================
    # 第一梯队特征
    # ========================================================================

    def _compute_northbound_features(
        self, northbound_df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """北向资金特征"""
        nb = northbound_df.copy()
        nb["date"] = pd.to_datetime(nb["date"])
        nb = nb.sort_values("date").set_index("date")

        # 对齐到价格数据的日期
        net_buy = nb["net_buy"].reindex(features.index, method="ffill")

        features["northbound_net_3d"] = net_buy.rolling(3).sum()
        features["northbound_net_5d"] = net_buy.rolling(5).sum()
        features["northbound_net_10d"] = net_buy.rolling(10).sum()

        # 连续净买入天数
        is_buy = (net_buy > 0).astype(int)
        features["northbound_consecutive_days"] = (
            is_buy.groupby((is_buy != is_buy.shift()).cumsum()).cumcount() + 1
        ) * is_buy

        # 净买入加速率（5日变化率的加速度）
        nb_5d = net_buy.rolling(5).sum()
        features["northbound_acceleration"] = nb_5d.diff(5) / nb_5d.shift(5).abs()

    def _compute_margin_features(
        self, margin_df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """融资余额特征"""
        mg = margin_df.copy()
        mg["date"] = pd.to_datetime(mg["date"])
        mg = mg.sort_values("date").set_index("date")

        margin_balance = mg["margin_balance"].reindex(features.index, method="ffill")

        # 5日变化率
        features["margin_balance_change_5d"] = margin_balance.pct_change(5)

        # 加速度（二阶导）
        change_1d = margin_balance.pct_change()
        features["margin_acceleration"] = change_1d.diff(5)

        # 融券占比
        if "short_balance" in mg.columns:
            short = mg["short_balance"].reindex(features.index, method="ffill")
            features["short_ratio"] = short / margin_balance

    def _compute_active_buy_features(
        self, active_buy_df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """主动买卖占比特征"""
        ab = active_buy_df.copy()
        ab["date"] = pd.to_datetime(ab["date"])
        ab = ab.sort_values("date").set_index("date")

        ratio = ab["active_buy_ratio"].reindex(features.index, method="ffill")

        features["active_buy_ratio_5d"] = ratio.rolling(5).mean()
        features["active_buy_ratio_change"] = features["active_buy_ratio_5d"].diff(5)

    # ========================================================================
    # 第二梯队特征
    # ========================================================================

    def _compute_sector_features(
        self, sector_df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """行业动量特征（从外部DataFrame读取——保留兼容）"""
        sc = sector_df.copy()
        sc["date"] = pd.to_datetime(sc["date"])
        sc = sc.sort_values("date").set_index("date")

        for col in ["sector_ret_5d", "sector_ret_10d", "sector_rank", "sector_etf_flow_5d"]:
            if col in sc.columns:
                features[col] = sc[col].reindex(features.index, method="ffill")

    def set_stock_code(self, code: str) -> None:
        """设置当前正在处理的股票代码（用于行业特征查询）"""
        self._current_stock_code = code

    def _compute_sector_features_from_precomputed(
        self, df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """行业动量特征——使用该股票所属行业的数据"""
        if self._industry_returns is None:
            return

        ind_rets = self._industry_returns
        industry_name = self._industry_map.get(
            getattr(self, "_current_stock_code", ""), None
        )

        if industry_name and industry_name in ind_rets.columns:
            # 该股票所属行业的日收益序列
            sector_ret = ind_rets[industry_name]
        else:
            # 回退：取所有行业等权均值
            sector_ret = ind_rets.mean(axis=1)

        # 5日/10日滚动累计
        sector_ret_5d = sector_ret.rolling(5).sum()
        sector_ret_10d = sector_ret.rolling(10).sum()

        # 行业排名（该行业在当日所有行业中的分位数，0=最差，1=最好）
        sector_5d_all = ind_rets.rolling(5).sum()
        if industry_name and industry_name in sector_5d_all.columns:
            # 每日重新计算排名
            rank_series = sector_5d_all.rank(axis=1, pct=True).reindex(
                columns=[industry_name]
            ).iloc[:, 0]
        else:
            rank_series = pd.Series(0.5, index=ind_rets.index)

        # 对齐到features的日期
        features["sector_ret_5d"] = sector_ret_5d.reindex(features.index, method="ffill")
        features["sector_ret_10d"] = sector_ret_10d.reindex(features.index, method="ffill")
        features["sector_rank"] = rank_series.reindex(features.index, method="ffill")

    # ========================================================================
    # 第三梯队特征
    # ========================================================================

    def _compute_anomaly_features(
        self, df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """异常检验特征（防出货陷阱）"""
        ret_1d = df["close"].pct_change()

        # 异常度 = (当日涨幅 - 前5日平均涨幅) / 前5日涨幅标准差
        ret_5d_mean = ret_1d.rolling(5).mean()
        ret_5d_std = ret_1d.rolling(5).std()
        features["anomaly_score"] = (ret_1d - ret_5d_mean) / ret_5d_std.replace(0, np.nan)

        # 出货陷阱风险：异常度>2 且 量比>3
        features["pump_and_dump_risk"] = (
            (features["anomaly_score"] > 2) &
            (features["volume_ratio"] > 3)
        ).astype(int)

    def _compute_unlock_features(
        self, unlock_df: pd.DataFrame, features: pd.DataFrame
    ) -> None:
        """限售股解禁特征"""
        ul = unlock_df.copy()
        ul["date"] = pd.to_datetime(ul["date"])
        ul = ul.sort_values("date").set_index("date")

        for col in ["days_to_unlock", "unlock_market_value_ratio"]:
            if col in ul.columns:
                features[col] = ul[col].reindex(features.index, method="ffill")

    # ========================================================================
    # 时间特征
    # ========================================================================

    def _compute_calendar_features(self, features: pd.DataFrame) -> None:
        """日历特征"""
        features["day_of_week"] = features.index.dayofweek
        features["is_month_start"] = (features.index.day <= 3).astype(int)
        features["is_month_end"] = (
            features.index.day >= (features.index + pd.offsets.MonthEnd(0)).day - 2
        ).astype(int)
        features["is_earnings_season"] = (
            features.index.month.isin([3, 4, 8, 9, 10])
        ).astype(int)


# ============================================================================
# 标签计算
# ============================================================================

def compute_labels(
    price_df: pd.DataFrame,
    hold_days: int = 3,
    threshold_up: float = 0.005,  # >0.5% 为涨
    threshold_down: float = -0.005,  # <-0.5% 为跌
) -> pd.DataFrame:
    """
    计算 T+3 收益率标签。

    Args:
        price_df: 价格数据
        hold_days: 持有天数
        threshold_up: 上涨阈值（用于分类标签）
        threshold_down: 下跌阈值

    Returns:
        DataFrame with columns: ret_3d (连续回归目标), direction (三分类标签)
    """
    df = price_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    labels = pd.DataFrame(index=df.index)

    # 回归目标：T日收盘 → T+N日收盘 的收益率
    labels["ret_3d"] = df["close"].pct_change(hold_days).shift(-hold_days)

    # 三分类标签
    labels["direction"] = 0  # 平
    labels.loc[labels["ret_3d"] > threshold_up, "direction"] = 1  # 涨
    labels.loc[labels["ret_3d"] < threshold_down, "direction"] = -1  # 跌

    # 二分类标签（用于胜率评估）
    labels["is_up"] = (labels["ret_3d"] > 0).astype(int)

    return labels
