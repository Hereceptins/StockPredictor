"""
全量A股数据回填脚本 —— Baostock，2018-2024，支持增量续传。
"""

import sys
from datetime import datetime
from pathlib import Path

import baostock as bs
import pandas as pd

DATA_DIR = Path("data/processed")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print(f"[{datetime.now():%H:%M:%S}] 登录 Baostock...", flush=True)
    bs.login()

    # 加载股票池
    pool_df = pd.read_parquet(DATA_DIR / "stock_pool.parquet")
    pool = pool_df["bs_code"].tolist()
    print(f"[{datetime.now():%H:%M:%S}] 股票池: {len(pool)} 只")

    # 已完成
    completed = {f.stem.replace("price_", "") for f in DATA_DIR.glob("price_*.parquet")}
    print(f"[{datetime.now():%H:%M:%S}] 已完成: {len(completed)}")

    # 待回填（含增量：已有数据但需要扩展到2018）
    to_fetch = []
    for bs_code in pool:
        ts_code = bs_code[3:] + (".SH" if bs_code.startswith("sh.") else ".SZ")
        if ts_code not in completed:
            to_fetch.append(bs_code)
    print(f"[{datetime.now():%H:%M:%S}] 待回填: {len(to_fetch)}")

    if not to_fetch:
        print("全部完成！")
        bs.logout()
        return

    # 分批回填
    batch_size = 50
    total = len(to_fetch)
    success = 0

    for i, code in enumerate(to_fetch):
        try:
            rs = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,volume,amount,turn,pctChg",
                start_date="2018-01-01",
                end_date="2024-06-30",
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())

            if rows:
                df = pd.DataFrame(rows, columns=rs.fields)
                for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["date"] = pd.to_datetime(df["date"])
                ts_code = code[3:] + (".SH" if code.startswith("sh.") else ".SZ")
                df.to_parquet(DATA_DIR / f"price_{ts_code}.parquet", index=False)
                success += 1

        except Exception as e:
            if i < 3:  # 只打印前几个错误
                print(f"  ⚠ {code}: {e}")
            continue

        if (i + 1) % batch_size == 0:
            pct = (i + 1) / total * 100
            print(f"[{datetime.now():%H:%M:%S}] {i+1}/{total} ({pct:.1f}%) 成功:{success}")

    bs.logout()
    print(f"[{datetime.now():%H:%M:%S}] 完成! 新增 {success} 只, 总计 {success+len(completed)} 只")


if __name__ == "__main__":
    main()
