"""拉取个股级北向资金数据并缓存"""
import sys
from pathlib import Path
import time
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path("data/processed")
NB_DIR = DATA_DIR / "northbound"
NB_DIR.mkdir(parents=True, exist_ok=True)


def main():
    # 加载股票列表
    price_files = sorted(DATA_DIR.glob("price_*.parquet"))
    codes = [f.stem.replace("price_", "") for f in price_files]
    print(f"待拉取: {len(codes)} 只股票")

    import akshare as ak

    success = 0
    skip = 0
    fail = 0
    t0 = time.time()

    for i, ts_code in enumerate(codes):
        # 转AKShare格式: 000001.SZ → 000001
        ak_code = ts_code.split(".")[0]
        cache_path = NB_DIR / f"nb_{ts_code}.parquet"

        if cache_path.exists():
            skip += 1
            continue

        try:
            df = ak.stock_hsgt_individual_em(symbol=ak_code)
            if len(df) == 0:
                fail += 1
                continue

            # 列名标准化
            cols = df.columns.tolist()
            date_col = cols[0]
            # 找净买入/持股变化列（第7或第8列通常是当日持股数量变化或当日净买入资金）
            # 列顺序: 日期, 收盘价, 涨跌幅, 持股数量, 持股市值, 持股占比, 当日持股变化, 当日净买入资金, 当日持股市值变化
            flow_col = None
            for c in cols:
                cn = str(c)
                if "净买入" in cn or "资金" in cn:
                    flow_col = c
                    break
            if flow_col is None:
                flow_col = cols[-2]  # 倒数第二列通常是净买入资金

            result = pd.DataFrame({
                "date": pd.to_datetime(df[date_col]),
                "net_buy": pd.to_numeric(df[flow_col], errors="coerce"),
            }).dropna(subset=["net_buy"]).sort_values("date")

            if len(result) > 0:
                result.to_parquet(cache_path, index=False)
                success += 1
            else:
                fail += 1

        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"  {ts_code}: {str(e)[:80]}")

        # 进度
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed * 60
            remaining = (len(codes) - i - 1) / rate if rate > 0 else 0
            print(f"  {i+1}/{len(codes)} 成功={success} 跳过={skip} 失败={fail} "
                  f"速率={rate:.0f}只/分 剩余={remaining:.0f}分")

        time.sleep(0.3)  # 避免被封

    elapsed = (time.time() - t0) / 60
    print(f"\n完成: {success}成功 {skip}缓存 {fail}失败, 耗时{elapsed:.1f}分")


if __name__ == "__main__":
    main()
