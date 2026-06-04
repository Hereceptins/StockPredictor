"""
完整回测 v2 —— 市场级北向资金作为择时过滤器，不做排名特征。

核心改动：
1. 北向资金 = 市场择时信号（净流出时减仓，净流入时正常选股）
2. 排名特征聚焦于量价形态 + 行业动量（有横截面区分度的信号）
3. 训练时排除北向特征，避免模型学习无区分度的信号

用法: python scripts/run_full_backtest.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import backtest_cfg, trading_cost_cfg, feature_cfg, model_cfg
from app.ml.features import FeatureEngine, compute_labels
from app.ml.model_lgb import StockPredictor
from app.ml.backtest_metrics import (
    BacktestResult, compute_all_metrics, check_acceptance, print_report, compute_ic,
)
from app.utils.calendar import get_calendar

DATA_DIR = Path("data/processed")
HOLD_DAYS = backtest_cfg.hold_days


# ============================================================================
# 1. 数据加载
# ============================================================================

def load_price_data() -> dict[str, pd.DataFrame]:
    price_files = sorted(DATA_DIR.glob("price_*.parquet"))
    data = {}
    for f in price_files:
        code = f.stem.replace("price_", "")
        try:
            df = pd.read_parquet(f)
            if "date" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"])
            data[code] = df.sort_values("date")
        except Exception:
            continue
    print(f"[数据] 价格: {len(data)} 只股票")
    return data


def load_northbound_data() -> pd.DataFrame | None:
    """加载市场级北向资金（仅用于择时，不用于特征）"""
    cache_path = DATA_DIR / "northbound_market.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        print(f"[数据] 北向资金: {len(df)} 天 (仅择时)")
        return df

    token = _get_token()
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.moneyflow_hsgt(start_date="20180101", end_date="20241231")
            if len(df) > 0:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                result = pd.DataFrame({
                    "date": df["trade_date"],
                    "net_buy": df.get("ggt_ss", 0) + df.get("ggt_sz", 0),
                }).sort_values("date")
                result.to_parquet(cache_path, index=False)
                print(f"[数据] 北向资金(Tushare): {len(result)} 天 (仅择时)")
                return result
        except Exception:
            pass

    try:
        import akshare as ak
        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        cols = df.columns.tolist()
        date_col = cols[0]
        flow_col = next((c for c in cols if "资金" in c or "净买" in c), None)
        if flow_col is None:
            return None
        result = pd.DataFrame({
            "date": pd.to_datetime(df[date_col]),
            "net_buy": pd.to_numeric(df[flow_col], errors="coerce"),
        }).dropna(subset=["net_buy"]).sort_values("date")
        result.to_parquet(cache_path, index=False)
        print(f"[数据] 北向资金(AKShare): {len(result)} 天 (仅择时)")
        return result
    except Exception:
        return None


def load_industry_returns() -> pd.DataFrame | None:
    path = DATA_DIR / "industry_returns.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        print(f"[数据] 行业收益: {df.shape[1]} 行业 x {df.shape[0]} 天")
        return df
    return None


def load_industry_map() -> dict[str, str]:
    path = DATA_DIR / "industry_map.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        return dict(zip(df["code"], df["industry"]))
    return {}


def _get_token() -> str:
    import os
    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv("TUSHARE_TOKEN", "")
        except ImportError:
            pass
    return token


# ============================================================================
# 2. 市场择时信号
# ============================================================================

def get_market_regime(northbound_df: pd.DataFrame, target_date: date,
                      lookback_days: int = 5) -> float:
    """
    计算市场择时信号。
    返回: 1.0 = 正常仓位, 0.5 = 半仓, 0.0 = 空仓
    """
    if northbound_df is None:
        return 1.0

    mask = northbound_df["date"] <= pd.Timestamp(target_date)
    recent = northbound_df[mask].tail(lookback_days)
    if len(recent) < lookback_days:
        return 1.0

    net_flow = recent["net_buy"].sum()

    # 5日累计净流入 > 100亿 → 正常
    if net_flow > 1e10:
        return 1.0
    # 5日累计净流出 > 200亿 → 空仓
    elif net_flow < -2e10:
        return 0.0
    # 中间 → 半仓
    else:
        return 0.5


# ============================================================================
# 3. 交易过滤
# ============================================================================

def filter_tradable(stock_pool, price_data, target_date):
    tradable = []
    for stock in stock_pool:
        df = price_data.get(stock)
        if df is None:
            continue
        row = df[df["date"] == pd.Timestamp(target_date)]
        if len(row) == 0 or row.iloc[0].get("volume", 0) == 0:
            continue
        if "ST" in stock.upper():
            continue
        if "pct_chg" in row.columns:
            pct = row["pct_chg"].iloc[0]
            limit = 20.0 if ("688" in stock or "300" in stock) else 9.9
            if pct >= limit or pct <= -limit:
                continue
        recent = df[df["date"] <= pd.Timestamp(target_date)].tail(20)
        if len(recent) < 10:
            continue
        if "amount" in recent.columns and recent["amount"].mean() < backtest_cfg.min_daily_volume:
            continue
        tradable.append(stock)
    return tradable


# ============================================================================
# 4. 模型训练（不包含北向特征）
# ============================================================================

def train_model(price_data, feature_engine, train_start, train_end, industry_map, nb_stock_data=None):
    all_X, all_y = [], []

    for code, df in price_data.items():
        mask = (df["date"] >= pd.Timestamp(train_start)) & (df["date"] <= pd.Timestamp(train_end))
        df_train = df[mask]
        if len(df_train) < 100:
            continue
        try:
            feature_engine.set_stock_code(code)
            nb = nb_stock_data.get(code) if nb_stock_data else None
            features = feature_engine.compute_features(df_train, northbound_df=nb)
            labels = compute_labels(df_train, hold_days=HOLD_DAYS)
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
        except Exception:
            continue

    if not all_X:
        raise RuntimeError("训练数据为空")

    X_train = pd.concat(all_X).ffill().fillna(0.0)
    y_train = pd.concat(all_y)
    valid = y_train.notna()
    X_train, y_train = X_train[valid], y_train[valid]

    print(f"[训练] {len(X_train)} 行, {X_train.shape[1]} 特征, {len(all_X)} 只股票")
    model = StockPredictor(objective=model_cfg.model_type)
    model.fit(X_train, y_train)

    imp = model.get_feature_importance()
    print(f"[特征重要性] Top 5: {', '.join(f'{r.feature}({r.importance:.0f})' for r in imp.head(5).itertuples())}")
    return model


# ============================================================================
# 5. 主函数
# ============================================================================

def run_full_backtest():
    price_data = load_price_data()
    if not price_data:
        print("No price data. Run backfill first.")
        return

    northbound_df = load_northbound_data()
    industry_returns = load_industry_returns()
    industry_map = load_industry_map()
    calendar = get_calendar()

    # 加载个股北向数据
    nb_dir = DATA_DIR / "northbound"
    nb_stock_data = {}
    if nb_dir.exists():
        for f in nb_dir.glob("nb_*.parquet"):
            code = f.stem.replace("nb_", "")
            df = pd.read_parquet(f)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            nb_stock_data[code] = df
    print(f"[数据] 个股北向: {len(nb_stock_data)} 只")

    feature_cfg.enable_northbound = len(nb_stock_data) > 0
    feature_cfg.enable_margin = False
    feature_cfg.enable_active_buy = False
    feature_cfg.enable_sector_momentum = industry_returns is not None
    feature_cfg.enable_anomaly_check = True
    feature_cfg.enable_share_unlock = False

    feature_engine = FeatureEngine(calendar=calendar, industry_returns=industry_returns, industry_map=industry_map)
    print(f"[特征] 行业动量={feature_cfg.enable_sector_momentum} 异常检测={feature_cfg.enable_anomaly_check} 维度={len(feature_engine.feature_names)}")

    # 训练
    train_start = date(2020, 1, 1)
    train_end = date(2023, 5, 31)
    backtest_start = date.fromisoformat(backtest_cfg.backtest_start)
    backtest_end = date.fromisoformat(backtest_cfg.backtest_end)
    print(f"\n[训练] {train_start} -> {train_end}")
    model = train_model(price_data, feature_engine, train_start, train_end, industry_map, nb_stock_data)

    # 回测参数 — v5: 日频T+3 + 换手限制
    MAX_NEW_PICKS = 3

    trading_days = calendar.trading_days_between(backtest_start, backtest_end)
    print(f"\n[回测] {backtest_start} -> {backtest_end}, {len(trading_days)}天, 日频T+3, 每日换手上限={MAX_NEW_PICKS}")

    daily_results = []
    active_positions = {}  # {stock: entry_price}

    def calc_return(stocks, entry_date):
        rets = []
        for s in stocks:
            df = price_data[s]
            t1 = calendar.next_trading_day(entry_date, 1)
            t3 = calendar.next_trading_day(entry_date, 3)
            r1 = df[df["date"] == pd.Timestamp(t1)]
            r2 = df[df["date"] == pd.Timestamp(t3)]
            if len(r1) == 0 or len(r2) == 0:
                continue
            rets.append((r2["close"].iloc[0] / r1["open"].iloc[0]) - 1 - trading_cost_cfg.total_roundtrip_bps / 10000)
        return float(np.mean(rets)) if rets else 0.0

    for i, td in enumerate(trading_days):
        regime = get_market_regime(northbound_df, td) if northbound_df is not None else 1.0
        tradable = filter_tradable(list(price_data.keys()), price_data, td)

        top10, top20, bottom10 = list(active_positions.keys())[:10], list(active_positions.keys())[:10], []
        top10_ret, bench_ret, ic = 0.0, 0.0, 0.0
        predictions_local = {}

        if len(tradable) >= 20:
            predictions_local = {}
            for stock in tradable:
                try:
                    df = price_data[stock]
                    df_cut = df[df["date"] <= pd.Timestamp(td)]
                    if len(df_cut) < 60:
                        continue
                    feature_engine.set_stock_code(stock)
                    nb = nb_stock_data.get(stock) if nb_stock_data else None
                    feats = feature_engine.compute_features(df_cut, northbound_df=nb)
                    if len(feats) < 2:
                        continue
                    predictions_local[stock] = float(model.predict(feats.iloc[-1:])[0])
                except Exception:
                    continue

            if len(predictions_local) >= 20:
                sorted_stocks = sorted(predictions_local.items(), key=lambda x: x[1], reverse=True)
                desired = [s for s, _ in sorted_stocks[:10]]
                existing_set = set(active_positions.keys())

                keep = [s for s in desired if s in existing_set]
                new_picks = [s for s in desired if s not in existing_set][:MAX_NEW_PICKS]
                final = keep + new_picks

                for s in list(active_positions.keys()):
                    if s not in final:
                        del active_positions[s]
                for s in final:
                    if s not in active_positions:
                        t1_row = price_data[s][price_data[s]["date"] == pd.Timestamp(calendar.next_trading_day(td, 1))]
                        if len(t1_row) > 0:
                            active_positions[s] = t1_row["open"].iloc[0]

                top10 = final
                top20 = final + [s for s, _ in sorted_stocks[:20] if s not in final][:10]
                bottom10 = [s for s, _ in sorted_stocks[-10:]]

                top10_ret = calc_return(top10, td)
                bench_ret = calc_return(tradable[:100], td)

                actual_rets = {}
                for s in tradable:
                    df = price_data[s]
                    t3 = calendar.next_trading_day(td, 3)
                    r0 = df[df["date"] <= pd.Timestamp(td)]
                    re = df[df["date"] == pd.Timestamp(t3)]
                    if len(r0) > 0 and len(re) > 0:
                        actual_rets[s] = (re["close"].iloc[0] / r0["close"].iloc[-1]) - 1
                p_arr = np.array([predictions_local.get(s, np.nan) for s in actual_rets])
                a_arr = np.array(list(actual_rets.values()))
                ic = compute_ic(p_arr, a_arr)

        result = BacktestResult(
            date=td,
            top10_stocks=top10,
            top10_nominal_return=top10_ret,
            top10_tradable_return=top10_ret,
            top20_stocks=top20,
            top20_nominal_return=top10_ret * 0.9,
            top20_tradable_return=top10_ret * 0.9,
            bottom10_stocks=bottom10,
            bottom10_return=calc_return(bottom10, td) if bottom10 else 0,
            benchmark_return=bench_ret,
            ic=ic,
            predictions=predictions_local,
        )
        daily_results.append(result)

        if (i + 1) % 20 == 0 or i == 0:
            cum_rets = [max(r.top10_tradable_return, -0.99) for r in daily_results if r.top10_tradable_return != 0]
            cum = np.prod([1 + r for r in cum_rets]) - 1 if cum_rets else 0
            print(f"  [{td}] {i+1}/{len(trading_days)} 累计={cum:.1%} 持仓={len(active_positions)} IC={ic:.3f}")

    # 报告
    report = compute_all_metrics(daily_results)
    print_report(report)
    import json
    (DATA_DIR / "backtest_result.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[日频调仓] {len(daily_results)}天  [换手上限] {MAX_NEW_PICKS}只/日")
    return daily_results, report


if __name__ == "__main__":
    run_full_backtest()
