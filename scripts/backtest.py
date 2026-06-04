"""
回测主入口 —— Walk-Forward 滚动窗口 + 固定切分双模式。

用法:
    # 快速迭代模式（固定训练集）
    python scripts/backtest.py --mode fast

    # 最终验收模式（逐月滚动窗口）
    python scripts/backtest.py --mode rolling

    # 指定回测区间
    python scripts/backtest.py --start 20230601 --end 20240601 --mode fast

依赖: 需要先运行 fetch_data.py 获取数据，数据存在 data/processed/ 下
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import (
    backtest_cfg, trading_cost_cfg, feature_cfg, model_cfg,
)
from app.ml.features import FeatureEngine, compute_labels
from app.ml.model_lgb import StockPredictor
from app.ml.backtest_metrics import (
    BacktestResult, MetricsReport,
    compute_all_metrics, check_acceptance, print_report, compute_ic,
)
from app.utils.calendar import get_calendar


# ============================================================================
# 交易过滤函数
# ============================================================================

def filter_tradable(
    stock_pool: list[str],
    price_data: dict[str, pd.DataFrame],
    target_date: date,
) -> list[str]:
    """
    过滤不可交易的股票（回测与实盘保持一致）。

    排除条件：
    1. ST股
    2. 停牌股
    3. 当日涨停（封板买不到）
    4. 当日跌停（流动性枯竭）
    5. 上市不足60日
    6. 日均成交额 < 5000万
    7. 日均换手率 < 1%
    """
    tradable = []

    for stock in stock_pool:
        df = price_data.get(stock)
        if df is None:
            continue

        # 获取目标日期所在行
        df["date"] = pd.to_datetime(df["date"])
        row = df[df["date"] == pd.Timestamp(target_date)]
        if len(row) == 0:
            continue
        row = row.iloc[0]

        # 停牌检查：成交量为0 → 停牌
        if row.get("volume", 0) == 0:
            continue

        # ST检查：股票代码包含 "ST"（简化判断，生产环境用 Tushare name 字段）
        if "ST" in stock.upper():
            continue

        # 涨跌停检查
        if "pct_chg" in row:
            pct = row["pct_chg"]
            # A股±10%，科创板/创业板±20%
            if "688" in stock or "300" in stock:
                limit = 20.0
            else:
                limit = 9.9  # 实际涨停价可能略低于10%
            if pct >= limit:  # 涨停
                continue
            if pct <= -limit:  # 跌停
                continue

        # 日均成交额检查（近20日）
        recent = df[df["date"] <= pd.Timestamp(target_date)].tail(20)
        if len(recent) < 10:
            continue
        avg_amount = recent["amount"].mean() if "amount" in recent.columns else 0
        if avg_amount < backtest_cfg.min_daily_volume:
            continue

        # 日均换手率检查
        if "turnover_rate" in recent.columns:
            avg_turnover = recent["turnover_rate"].mean()
            if avg_turnover < backtest_cfg.min_daily_turnover:
                continue

        tradable.append(stock)

    return tradable


# ============================================================================
# 核心回测循环
# ============================================================================

def run_backtest(
    price_data: dict[str, pd.DataFrame],
    northbound_data: dict[str, pd.DataFrame] | None = None,
    margin_data: dict[str, pd.DataFrame] | None = None,
    sector_data: pd.DataFrame | None = None,
    industry_returns: pd.DataFrame | None = None,
    industry_map: dict[str, str] | None = None,
    constituents: dict[date, list[str]] | None = None,
    mode: str = "fast",
) -> tuple[list[BacktestResult], MetricsReport]:
    """
    运行完整回测。

    Args:
        price_data: {stock_code: price_df} —— 所有股票的OHLCV数据
        northbound_data: {stock_code: northbound_df} —— 北向资金
        margin_data: {stock_code: margin_df} —— 融资融券
        sector_data: 行业动量数据
        constituents: {date: [stock_codes]} —— 每日成分股列表（幸存者偏差控制）
        mode: "fast" | "rolling"

    Returns:
        (daily_results, full_report)
    """
    calendar = get_calendar()
    feature_engine = FeatureEngine(
        calendar=calendar,
        industry_returns=industry_returns,
        industry_map=industry_map,
    )

    backtest_start = date.fromisoformat(backtest_cfg.backtest_start)
    backtest_end = date.fromisoformat(backtest_cfg.backtest_end)
    train_start = date.fromisoformat(backtest_cfg.train_start)

    # 预加载成分股快照（用于分级交易成本）
    _load_constituents_cache(str(backtest_start), str(backtest_end))

    trading_days = calendar.trading_days_between(backtest_start, backtest_end)
    print(f"回测区间: {backtest_start} → {backtest_end}")
    print(f"交易日数: {len(trading_days)}")
    print(f"模式: {mode}")

    daily_results: list[BacktestResult] = []
    model: StockPredictor | None = None
    last_train_end: date | None = None

    for i, target_date in enumerate(trading_days):
        # --- 确定股票池（幸存者偏差控制） ---
        if constituents and backtest_cfg.survivorship_bias_control:
            stock_pool = constituents.get(target_date, list(price_data.keys()))
        else:
            stock_pool = list(price_data.keys())

        # --- 过滤不可交易股票 ---
        tradable_pool = filter_tradable(stock_pool, price_data, target_date)

        if len(tradable_pool) < backtest_cfg.top_n_diversified:
            print(f"  {target_date}: 可交易股票不足 ({len(tradable_pool)})，跳过")
            continue

        # --- Walk-Forward：检查是否需要重新训练 ---
        if mode == "rolling":
            # 逐月重训
            train_end = target_date - timedelta(days=1)
            if last_train_end is None or \
               train_end.month != last_train_end.month or \
               train_end.year != last_train_end.year:
                model = _train_model(
                    price_data, northbound_data, margin_data,
                    tradable_pool, train_start, train_end, feature_engine
                )
                last_train_end = train_end
                print(f"  [{target_date}] 模型已重训（训练截止: {train_end}）")
        elif mode == "fast" and model is None:
            # 固定训练集——用回测期之前所有可用数据
            train_end = backtest_start - timedelta(days=1)
            # 往前推 min_train_window_years，但不能早于实际数据起点
            # 使用全部可用历史数据（不限制最少年份，让模型自己利用所有信息）
            # 验证训练起点——自动调整为最早可用数据
            actual_train_start = train_start
            # 诊断：检查有多少股票在训练起点前有数据
            stocks_before_train = sum(
                1 for df in price_data.values()
                if len(df) > 0 and df["date"].min() <= pd.Timestamp(train_start)
            )
            if stocks_before_train < len(price_data) * 0.5:
                # 自动调整：取覆盖50%+股票的最早日期
                all_starts = sorted(
                    df["date"].min()
                    for df in price_data.values()
                    if len(df) > 0
                )
                if all_starts:
                    median_start = all_starts[len(all_starts) // 2]
                    if hasattr(median_start, "date"):
                        median_start = median_start.date()
                    actual_train_start = date.fromisoformat(str(median_start)[:10]) if hasattr(median_start, "isoformat") else median_start
                    print(f"  [WARN] Only {stocks_before_train}/{len(price_data)} stocks have data before {train_start}")
                    print(f"    训练起点自动调整为: {actual_train_start}（覆盖50%+股票）")
            print(f"  训练集: {actual_train_start} → {train_end}")
            model = _train_model(
                price_data, northbound_data, margin_data,
                tradable_pool, actual_train_start, train_end, feature_engine
            )
            print(f"  [{target_date}] 固定训练集模型已就绪")

        if model is None:
            print(f"  [{target_date}] 模型未就绪，跳过")
            continue

        # --- 计算特征并预测 ---
        predictions = {}
        for stock in tradable_pool:
            try:
                df = price_data[stock]
                # 截取到 target_date 为止的数据（不能用未来数据！）
                df_cut = df[df["date"] <= pd.Timestamp(target_date)]

                nb_df = northbound_data.get(stock) if northbound_data else None
                mg_df = margin_data.get(stock) if margin_data else None

                feature_engine.set_stock_code(stock)
                features = feature_engine.compute_features(
                    df_cut, northbound_df=nb_df, margin_df=mg_df,
                    sector_df=sector_data,
                )
                if len(features) < 2:
                    continue

                # 只取最后一行（T日特征）
                last_features = features.iloc[-1:]

                # 预测
                pred = model.predict(last_features)[0]
                predictions[stock] = float(pred)
            except Exception:
                continue

        if len(predictions) < backtest_cfg.top_n_diversified:
            continue

        # --- 排序选股 ---
        sorted_stocks = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        top10 = [s for s, _ in sorted_stocks[:backtest_cfg.top_n_select]]
        top20 = [s for s, _ in sorted_stocks[:backtest_cfg.top_n_diversified]]
        bottom10 = [s for s, _ in sorted_stocks[-backtest_cfg.top_n_select:]]

        # --- 计算实际收益 ---
        top10_nominal = _compute_portfolio_return(
            price_data, top10, target_date, calendar, mode="nominal"
        )
        top10_tradable = _compute_portfolio_return(
            price_data, top10, target_date, calendar, mode="tradable"
        )
        top20_nominal = _compute_portfolio_return(
            price_data, top20, target_date, calendar, mode="nominal"
        )
        top20_tradable = _compute_portfolio_return(
            price_data, top20, target_date, calendar, mode="tradable"
        )
        bottom10_return = _compute_portfolio_return(
            price_data, bottom10, target_date, calendar, mode="nominal"
        )

        # 等权基准
        benchmark_return = _compute_benchmark_return(
            price_data, tradable_pool, target_date, calendar
        )

        # --- 计算IC ---
        actual_returns = {}
        for stock in tradable_pool:
            df = price_data[stock]
            df_d = df[df["date"] <= pd.Timestamp(target_date)]
            if len(df_d) < backtest_cfg.hold_days + 1:
                continue
            # 实际3日收益率
            current_close = df_d["close"].iloc[-1]
            # 找 T+3 的收盘价
            t3_date = calendar.next_trading_day(target_date, backtest_cfg.hold_days)
            t3_row = df[df["date"] == pd.Timestamp(t3_date)]
            if len(t3_row) > 0:
                actual_ret = (t3_row["close"].iloc[0] / current_close) - 1
                actual_returns[stock] = actual_ret

        pred_array = np.array([predictions.get(s, np.nan) for s in actual_returns])
        actual_array = np.array(list(actual_returns.values()))
        ic = compute_ic(pred_array, actual_array)

        # --- 记录结果 ---
        result = BacktestResult(
            date=target_date,
            top10_stocks=top10,
            top10_nominal_return=top10_nominal,
            top10_tradable_return=top10_tradable,
            top20_stocks=top20,
            top20_nominal_return=top20_nominal,
            top20_tradable_return=top20_tradable,
            bottom10_stocks=bottom10,
            bottom10_return=bottom10_return,
            benchmark_return=benchmark_return,
            ic=ic,
            predictions=predictions,
        )
        daily_results.append(result)

        if (i + 1) % 20 == 0 or i == 0:
            cum_ret = np.prod([1 + r.top10_tradable_return for r in daily_results]) - 1
            print(f"  [{target_date}] {i+1}/{len(trading_days)} "
                  f"累计收益={cum_ret:.4%} IC={ic:.3f}")

    # --- 汇总报告 ---
    report = compute_all_metrics(daily_results)
    return daily_results, report


def _train_model(
    price_data: dict[str, pd.DataFrame],
    northbound_data: dict[str, pd.DataFrame] | None,
    margin_data: dict[str, pd.DataFrame] | None,
    tradable_pool: list[str],
    train_start: date,
    train_end: date,
    feature_engine: FeatureEngine,
) -> StockPredictor:
    """训练 LightGBM 模型"""
    all_X, all_y = [], []

    for stock in tradable_pool:
        df = price_data[stock]
        # 确保date列是datetime
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])

        df_mask = (
            (df["date"] >= pd.Timestamp(train_start)) &
            (df["date"] <= pd.Timestamp(train_end))
        )
        df_train = df.loc[df_mask]

        if len(df_train) < 60:
            continue

        try:
            feature_engine.set_stock_code(stock)
            features = feature_engine.compute_features(
                df_train,
                northbound_df=northbound_data.get(stock) if northbound_data else None,
                margin_df=margin_data.get(stock) if margin_data else None,
            )
            labels = compute_labels(df_train, hold_days=backtest_cfg.hold_days)

            # 对齐
            common_idx = features.index.intersection(labels.index)
            if len(common_idx) < 30:
                continue

            X = features.loc[common_idx].ffill().fillna(0.0)
            y = labels.loc[common_idx, "ret_3d"]

            # 只保留label有效的行（不要求所有特征都非NaN）
            valid = y.notna()
            if valid.sum() < 30:
                continue
            X = X[valid]
            y = y[valid]

            all_X.append(X)
            all_y.append(y)
        except Exception:
            continue

    if not all_X:
        # 诊断：尝试一只股票看看具体问题
        for stock in list(tradable_pool)[:1]:
            df = price_data[stock]
            mask = (df["date"] >= pd.Timestamp(train_start)) & (df["date"] <= pd.Timestamp(train_end))
            df_t = df.loc[mask]
            print(f"  诊断 {stock}: total={len(df)}, train_period={len(df_t)}")
            if len(df_t) >= 60:
                try:
                    feats = feature_engine.compute_features(df_t)
                    labs = compute_labels(df_t, hold_days=backtest_cfg.hold_days)
                    common = feats.index.intersection(labs.index)
                    print(f"    features={len(feats)}, labels={len(labs)}, common={len(common)}")
                    if len(common) > 0:
                        X = feats.loc[common]; y = labs.loc[common, "ret_3d"]
                        valid = ~(X.isna().any(axis=1) | y.isna())
                        print(f"    valid rows={valid.sum()}, X cols={X.shape[1]}")
                        nan_cols = X.columns[X.isna().any()].tolist()
                        print(f"    NaN cols({len(nan_cols)}): {nan_cols[:5]}...")
                except Exception as e:
                    print(f"    ERROR: {e}")
        print(f"  训练区间: {train_start} -> {train_end}")
        raise RuntimeError(f"训练数据为空——没有股票在训练区间内有足够数据")

    X_all = pd.concat(all_X).ffill().fillna(0.0)
    y_all = pd.concat(all_y)
    # 只保留X和y都有的行
    common_idx = X_all.index.intersection(y_all.index)
    X_all = X_all.loc[common_idx]
    y_all = y_all.loc[common_idx]

    # 只要求label有效（特征NaN已通过ffill+fillna处理）
    valid_mask = y_all.notna()
    X_all = X_all[valid_mask]
    y_all = y_all[valid_mask]

    print(f"  训练样本: {len(X_all)} 行, {X_all.shape[1]} 特征, {len(all_X)} 只股票贡献")

    model = StockPredictor(objective=model_cfg.model_type)
    model.fit(X_all, y_all)
    return model


def _compute_portfolio_return(
    price_data: dict[str, pd.DataFrame],
    stocks: list[str],
    target_date: date,
    calendar,
    mode: str = "tradable",
) -> float:
    """
    计算组合持有3日后的收益率。

    Args:
        mode: "nominal" 理论值 / "tradable" 实盘值（剔除涨停不可买）
    """
    returns = []

    for stock in stocks:
        df = price_data.get(stock)
        if df is None:
            continue

        df["date"] = pd.to_datetime(df["date"])

        # T日买入价（次日开盘价）
        t1_date = calendar.next_trading_day(target_date, 1)  # T+1
        t1_row = df[df["date"] == pd.Timestamp(t1_date)]
        if len(t1_row) == 0:
            continue

        buy_price = t1_row["open"].iloc[0]

        # tradable模式：检查T日是否涨停（买不到）
        if mode == "tradable":
            t0_row = df[df["date"] == pd.Timestamp(target_date)]
            if len(t0_row) > 0 and "pct_chg" in t0_row.columns:
                pct = t0_row["pct_chg"].iloc[0]
                limit = 20.0 if ("688" in stock or "300" in stock) else 9.9
                if pct >= limit:
                    returns.append(0.0)  # 买不到，该仓位收益为0
                    continue

        # T+3 卖出价（收盘价）
        sell_date = calendar.next_trading_day(target_date, backtest_cfg.hold_days)
        sell_row = df[df["date"] == pd.Timestamp(sell_date)]
        if len(sell_row) == 0:
            continue

        sell_price = sell_row["close"].iloc[0]

        # 收益（含交易成本）
        gross_return = (sell_price / buy_price) - 1

        # 交易成本（按指数分级）
        for idx_name in ["CSI300", "CSI500", "CSI1000"]:
            if stock in _get_index_stocks(idx_name, target_date):
                slippage = trading_cost_cfg.get_slippage(idx_name)
                break
        else:
            slippage = trading_cost_cfg.slippage_csi500

        net_return = gross_return - trading_cost_cfg.total_roundtrip_bps / 10000 - slippage
        returns.append(net_return)

    returns = [r for r in returns if not np.isnan(r)]
    return float(np.mean(returns)) if returns else 0.0


def _compute_benchmark_return(
    price_data: dict[str, pd.DataFrame],
    stock_pool: list[str],
    target_date: date,
    calendar,
) -> float:
    """计算等权基准收益率"""
    all_returns = []
    for stock in stock_pool:
        df = price_data.get(stock)
        if df is None:
            continue
        df["date"] = pd.to_datetime(df["date"])

        t1_date = calendar.next_trading_day(target_date, 1)
        t1_row = df[df["date"] == pd.Timestamp(t1_date)]
        if len(t1_row) == 0:
            continue

        buy_price = t1_row["open"].iloc[0]

        sell_date = calendar.next_trading_day(target_date, backtest_cfg.hold_days)
        sell_row = df[df["date"] == pd.Timestamp(sell_date)]
        if len(sell_row) == 0:
            continue

        ret = (sell_row["close"].iloc[0] / buy_price) - 1
        all_returns.append(ret)

    all_returns = [r for r in all_returns if not np.isnan(r)]
    return float(np.mean(all_returns)) if all_returns else 0.0


# 全局缓存：回测启动时预加载所有成分股快照
_index_constituents_cache: dict[str, dict[str, set[str]]] = {}  # {index: {YYYYMM: {codes}}}


def _load_constituents_cache(backtest_start: str, backtest_end: str) -> None:
    """回测开始前预加载所有成分股快照"""
    from datetime import date as dt, timedelta
    from pathlib import Path

    data_dir = Path("data/processed")
    start_dt = dt.fromisoformat(backtest_start) if isinstance(backtest_start, str) else backtest_start
    end_dt = dt.fromisoformat(backtest_end) if isinstance(backtest_end, str) else backtest_end

    for index_name in ["CSI300", "CSI500", "CSI1000"]:
        _index_constituents_cache[index_name] = {}
        pattern = f"constituents_{index_name}_*.parquet"
        for f in sorted(data_dir.glob(pattern)):
            # 从文件名提取日期 e.g. constituents_CSI300_20180101.parquet
            date_str = f.stem.split("_")[-1]
            try:
                df = pd.read_parquet(f)
                # 兼容不同列名格式
                if "ts_code" in df.columns:
                    codes = set(df["ts_code"].tolist())
                elif "code" in df.columns:
                    codes = set(c.strip() for c in df["code"].tolist())
                else:
                    codes = set(str(c) for c in df.iloc[:, 0].tolist())
                _index_constituents_cache[index_name][date_str] = codes
            except Exception:
                continue


def _get_index_stocks(index_name: str, target_date: date | None = None) -> set[str]:
    """获取某指数在特定日期的成分股集合"""
    if not _index_constituents_cache:
        # 快照不存在，使用当前数据中的所有股票（回退方案）
        return set()

    cache = _index_constituents_cache.get(index_name, {})
    if not cache:
        return set()

    if target_date:
        # 找最接近 target_date 但不晚于它的快照
        date_str = target_date.strftime("%Y%m%d") if hasattr(target_date, "strftime") else str(target_date)
        available = sorted(cache.keys())
        best = None
        for d in available:
            if d <= date_str:
                best = d
        if best:
            return cache.get(best, set())
    # 没有日期参数时返回最近快照
    latest = max(cache.keys()) if cache else None
    return cache.get(latest, set()) if latest else set()


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="A股T+3预测回测")
    parser.add_argument("--mode", choices=["fast", "rolling"], default="fast",
                        help="回测模式: fast=固定训练集, rolling=逐月滚动")
    parser.add_argument("--start", type=str, default=backtest_cfg.backtest_start,
                        help="回测起始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, default=backtest_cfg.backtest_end,
                        help="回测结束日期 YYYYMMDD")
    parser.add_argument("--data-dir", type=str, default="data/processed",
                        help="处理后数据目录")
    parser.add_argument("--output", type=str, default=None,
                        help="结果输出路径（JSON）")
    args = parser.parse_args()

    # 更新配置
    backtest_cfg.backtest_start = args.start
    backtest_cfg.backtest_end = args.end
    backtest_cfg.validation_mode = args.mode

    # 检查数据
    data_path = Path(args.data_dir)
    if not data_path.exists():
        print(f"❌ 数据目录不存在: {data_path}")
        print("   请先运行: python scripts/fetch_data.py")
        sys.exit(1)

    # 加载数据
    print("加载数据...")
    price_data = _load_price_data(data_path)
    if not price_data:
        print("❌ 未找到价格数据。请先运行 fetch_data.py")
        sys.exit(1)

    print(f"  已加载 {len(price_data)} 只股票的价格数据")

    # 加载行业数据
    industry_returns = None
    industry_map = None
    sector_path = data_path / "industry_returns.parquet"
    if sector_path.exists():
        industry_returns = pd.read_parquet(sector_path)
        print(f"  已加载行业收益: {industry_returns.shape[1]} 行业 × {industry_returns.shape[0]} 天")
        # 重建 industry_map（从已有的price文件+baostock分类）
        try:
            from app.ml.sector_features import SectorFeatureBuilder
            builder = SectorFeatureBuilder()
            builder.build_industry_map(price_data)
            industry_map = builder._industry_map
        except Exception:
            pass

    # 运行回测
    print("\n开始回测...")
    daily_results, report = run_backtest(
        price_data=price_data,
        industry_returns=industry_returns,
        industry_map=industry_map,
        mode=args.mode,
    )

    # 打印报告
    print_report(report)

    # 保存结果
    if args.output:
        output = report.to_dict()
        output["config"] = {
            "mode": args.mode,
            "start": args.start,
            "end": args.end,
            "n_stocks": len(price_data),
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {args.output}")


def _load_price_data(data_path: Path) -> dict[str, pd.DataFrame]:
    """从 parquet 文件加载价格数据，确保所有类型正确"""
    price_files = list(data_path.glob("price_*.parquet"))
    data = {}
    for f in price_files:
        code = f.stem.replace("price_", "")
        try:
            df = pd.read_parquet(f)
            if "date" not in df.columns and df.index.name == "date":
                df = df.reset_index()
            # 确保日期列是 datetime
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            # 将所有非数值列转为数值（baostock数据全是string）
            for col in df.columns:
                if col == "date":
                    continue
                try:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                except Exception:
                    pass
            data[code] = df
        except Exception:
            continue
    return data


if __name__ == "__main__":
    main()
