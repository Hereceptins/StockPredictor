"""用Tushare申万行业分类重建行业收益矩阵"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_tushare_token


def main():
    import tushare as ts

    token = load_tushare_token()
    ts.set_token(token)
    pro = ts.pro_api()

    # 1. 获取行业分类
    print("获取Tushare行业分类...", flush=True)
    df = pro.stock_basic(list_status="L", fields="ts_code,name,industry")
    print(f"  {len(df)} 只股票, {df['industry'].nunique()} 个行业", flush=True)
    df.to_parquet("data/processed/tushare_industries.parquet")

    # 2. 计算行业收益
    print("构建行业收益矩阵...", flush=True)
    industry_map = dict(zip(df["ts_code"], df["industry"]))

    files = list(Path("data/processed").glob("price_*.parquet"))
    all_data = []
    for f in files:
        code = f.stem.replace("price_", "")
        ind = industry_map.get(code, "其他")
        df_p = pd.read_parquet(f)
        if len(df_p) < 10:
            continue
        df_p["date"] = pd.to_datetime(df_p["date"])
        df_p = df_p.sort_values("date")
        df_p["ret"] = df_p["close"].pct_change()
        df_p["industry"] = ind
        all_data.append(df_p[["date", "ret", "industry"]])

    combined = pd.concat(all_data, ignore_index=True)
    ind_daily = combined.groupby(["date", "industry"])["ret"].mean().reset_index()
    ind_matrix = ind_daily.pivot(index="date", columns="industry", values="ret").fillna(0.0)
    ind_matrix = ind_matrix["2018-01-01":"2024-06-30"]
    print(f"  {ind_matrix.shape[1]} 行业 x {ind_matrix.shape[0]} 天", flush=True)
    ind_matrix.to_parquet("data/processed/industry_returns_v2.parquet")
    print("Done!", flush=True)


if __name__ == "__main__":
    main()
