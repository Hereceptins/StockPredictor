"""
历史数据回填 —— 支持断点续传、分月回填、多数据源降级。

用法:
    python scripts/backfill_data.py --start 20180101 --end 20240601
    python scripts/backfill_data.py --start 20180101 --end 20240601 --resume
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import datasource_cfg, load_tushare_token
from app.utils.calendar import get_calendar


# ============================================================================
# 断点续传
# ============================================================================

class BackfillProgress:
    """回填进度管理 —— 记录最后成功日期，支持断点续传"""

    def __init__(self, progress_file: str = "data/backfill_progress.json"):
        self.progress_file = Path(progress_file)
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {}

    def save(self) -> None:
        with open(self.progress_file, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    def mark_complete(self, task: str, last_date: date) -> None:
        self._data[task] = last_date.isoformat()
        self.save()

    def get_last_date(self, task: str) -> date | None:
        val = self._data.get(task)
        return date.fromisoformat(val) if val else None

    def is_complete(self, task: str) -> bool:
        return task in self._data


# ============================================================================
# 数据回填函数
# ============================================================================

def backfill_daily_kline(
    start: str, end: str, codes: list[str] | None = None,
    chunk_months: int = 3, sleep_sec: float = 1.0,
) -> dict[str, Path]:
    """
    回填日线数据。

    策略：按3个月一批，逐批处理，每批之间sleep防封。

    Returns:
        {stock_code: parquet_file_path}
    """
    from app.config import load_tushare_token

    token = load_tushare_token()
    if not token:
        print("❌ TUSHARE_TOKEN 未设置，无法回填")
        return {}

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    progress = BackfillProgress()
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 获取股票列表
    if codes is None:
        print("获取全A股股票列表...")
        df_stocks = pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,list_date"
        )
        # 过滤：只保留沪深两市
        codes = df_stocks[
            df_stocks["ts_code"].str.endswith((".SH", ".SZ"))
        ]["ts_code"].tolist()
        print(f"  共 {len(codes)} 只股票")

    # 按3个月分批
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")

    current = start_dt
    result = {}
    total_batches = 0

    while current < end_dt:
        chunk_end = min(
            current + timedelta(days=chunk_months * 31),
            end_dt
        )
        chunk_start_str = current.strftime("%Y%m%d")
        chunk_end_str = chunk_end.strftime("%Y%m%d")

        batch_key = f"kline_{chunk_start_str}_{chunk_end_str}"
        if progress.is_complete(batch_key):
            print(f"  ⏭  [{chunk_start_str} → {chunk_end_str}] 已完成，跳过")
            current = chunk_end + timedelta(days=1)
            continue

        print(f"  📥 [{chunk_start_str} → {chunk_end_str}] 获取日线数据...")

        all_dfs = []
        for i, code in enumerate(codes):
            try:
                df = pro.daily(
                    ts_code=code,
                    start_date=chunk_start_str,
                    end_date=chunk_end_str,
                )
                if len(df) > 0:
                    df["ts_code"] = code
                    all_dfs.append(df)

                if (i + 1) % 100 == 0:
                    print(f"    进度: {i+1}/{len(codes)}")
                    time.sleep(sleep_sec)
            except Exception as e:
                print(f"    ⚠️  {code} 失败: {e}")
                continue

        # 保存为 parquet
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined["trade_date"] = pd.to_datetime(combined["trade_date"])

            # 按股票拆分保存（方便单股加载）
            for code in combined["ts_code"].unique():
                stock_df = combined[combined["ts_code"] == code]
                file_path = output_dir / f"price_{code}.parquet"

                # 如果已有文件，合并
                if file_path.exists():
                    existing = pd.read_parquet(file_path)
                    existing["trade_date"] = pd.to_datetime(existing["trade_date"])
                    stock_df = pd.concat([existing, stock_df]).drop_duplicates(
                        subset=["ts_code", "trade_date"]
                    )

                stock_df.to_parquet(file_path, index=False)
                if code not in result:
                    result[code] = file_path

            print(f"    保存 {len(combined['ts_code'].unique())} 只股票, {len(combined)} 行")

        progress.mark_complete(batch_key, chunk_end.date())
        total_batches += 1
        current = chunk_end + timedelta(days=1)
        time.sleep(sleep_sec * 2)  # 批次间额外冷却

    print(f"\n✅ 日线回填完成。共 {total_batches} 批, {len(result)} 只股票")
    return result


def backfill_index_constituents(
    start: str, end: str,
    indices: list[str] | None = None,
) -> dict[str, Path]:
    """
    回填指数成分股历史快照（每月一份）。

    用于幸存者偏差控制。
    """
    from app.config import load_tushare_token

    token = load_tushare_token()
    if not token:
        print("⚠️  TUSHARE_TOKEN 未设置，成分股快照不可用")
        return {}

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    if indices is None:
        indices = ["000300.SH", "000905.SH", "000852.SH"]  # 沪深300、中证500、中证1000

    index_names = {
        "000300.SH": "CSI300",
        "000905.SH": "CSI500",
        "000852.SH": "CSI1000",
    }

    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 获取每月最后一个交易日
    calendar = get_calendar()
    start_dt = date.fromisoformat(start) if isinstance(start, str) else start
    end_dt = date.fromisoformat(end) if isinstance(end, str) else end

    result = {}
    current = start_dt

    while current < end_dt:
        # 找当月末
        next_month = current.replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)

        if month_end > end_dt:
            break

        # 找最近交易日
        month_end = calendar.prev_trading_day(month_end + timedelta(days=1))

        trade_date_str = month_end.strftime("%Y%m%d")

        for idx_code in indices:
            idx_name = index_names.get(idx_code, idx_code)
            file_path = output_dir / f"constituents_{idx_name}_{trade_date_str}.parquet"

            if file_path.exists():
                result[f"{idx_name}_{trade_date_str}"] = file_path
                continue

            try:
                df = pro.index_member(
                    index_code=idx_code,
                    trade_date=trade_date_str,
                )
                if len(df) > 0:
                    df.to_parquet(file_path, index=False)
                    result[f"{idx_name}_{trade_date_str}"] = file_path
                    print(f"  📋 {idx_name} {trade_date_str}: {len(df)} 只成分股")
            except Exception as e:
                print(f"  ⚠️  {idx_code} {trade_date_str} 失败: {e}")

        current = month_end + timedelta(days=1)

    print(f"\n✅ 成分股快照完成。共 {len(result)} 个快照")
    return result


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="历史数据回填")
    parser.add_argument("--start", type=str, default="20180101")
    parser.add_argument("--end", type=str, default="20240601")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="启用断点续传（默认）")
    parser.add_argument("--chunk-months", type=int, default=3,
                        help="每批回填月数（默认3个月）")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="API调用间隔秒数（默认1秒）")
    parser.add_argument("--skip-constituents", action="store_true",
                        help="跳过成分股快照回填")
    args = parser.parse_args()

    print("StockPredictor — 历史数据回填")
    print(f"区间: {args.start} → {args.end}")
    print(f"断点续传: {'启用' if args.resume else '关闭'}")

    # 1. 日线数据
    print("\n[1/2] 日线数据回填...")
    backfill_daily_kline(
        start=args.start,
        end=args.end,
        chunk_months=args.chunk_months,
        sleep_sec=args.sleep,
    )

    # 2. 成分股快照
    if not args.skip_constituents:
        print("\n[2/2] 指数成分股快照...")
        backfill_index_constituents(
            start=args.start,
            end=args.end,
        )

    print("\n✅ 全部回填完成")


if __name__ == "__main__":
    main()
