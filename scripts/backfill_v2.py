"""
全量A股回填 v2 —— 稳健、断点续传、进度可见。
每100只报告一次进度和ETA。
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import baostock as bs
import pandas as pd

DATA_DIR = Path("data/processed")


def count_files():
    return len(list(DATA_DIR.glob("price_*.parquet")))


def main():
    print(f"[{datetime.now():%H:%M:%S}] 登录...", flush=True)
    bs.login()
    print("login ok", flush=True)

    # 加载池
    pool = pd.read_parquet(DATA_DIR / "stock_pool.parquet")["bs_code"].tolist()
    print(f"[{datetime.now():%H:%M:%S}] 池: {len(pool)}", flush=True)

    # 已完成
    before = count_files()
    completed = {f.stem.replace("price_", "") for f in DATA_DIR.glob("price_*.parquet")}
    print(f"已完成: {before}", flush=True)

    # 构建待处理列表
    to_fetch = []
    for bs_code in pool:
        ts_code = bs_code[3:] + (".SH" if bs_code.startswith("sh.") else ".SZ")
        if ts_code not in completed:
            to_fetch.append((bs_code, ts_code))

    total = len(to_fetch)
    print(f"待处理: {total}", flush=True)
    if total == 0:
        print("全部完成！", flush=True)
        bs.logout()
        return

    success = 0
    t0 = time.time()

    for i, (bs_code, ts_code) in enumerate(to_fetch, 1):
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
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
                df["open"] = pd.to_numeric(df["open"], errors="coerce")
                df["high"] = pd.to_numeric(df["high"], errors="coerce")
                df["low"] = pd.to_numeric(df["low"], errors="coerce")
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
                df["turn"] = pd.to_numeric(df["turn"], errors="coerce")
                df["pctChg"] = pd.to_numeric(df["pctChg"], errors="coerce")
                df["date"] = pd.to_datetime(df["date"])
                df.to_parquet(DATA_DIR / f"price_{ts_code}.parquet", index=False)
                success += 1
        except Exception:
            pass

        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed * 60  # stocks per minute
            remaining = (total - i) / rate if rate > 0 else 0
            now = count_files()
            print(
                f"[{datetime.now():%H:%M:%S}] "
                f"{i}/{total} ({100*i/total:.1f}%) "
                f"成功:{success} 文件:{now} "
                f"{elapsed/60:.0f}分 速率:{rate:.0f}只/分 "
                f"剩:{remaining:.0f}分",
                flush=True,
            )

    bs.logout()
    after = count_files()
    elapsed = (time.time() - t0) / 60
    print(
        f"[{datetime.now():%H:%M:%S}] 完成! "
        f"{before}→{after} (+{after-before}), "
        f"耗时{elapsed:.0f}分",
        flush=True,
    )


if __name__ == "__main__":
    main()
