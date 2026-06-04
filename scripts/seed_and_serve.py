"""
启动时灌数据 + 生成每日精选池。

Railway 部署时作为 pre-start 命令运行。
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings


def seed_stock_metadata():
    """从 parquet 文件灌入股票元数据到 SQLite"""
    from app.models.database import async_session
    from app.models.stock_models import Stock, DailyKLine
    import asyncio

    async def _seed():
        async with async_session() as db:
            # 检查是否已有数据
            from sqlalchemy import select, func
            result = await db.execute(select(func.count()).select_from(Stock))
            count = result.scalar()
            if count and count > 100:
                print(f"[Seed] {count} 只股票已存在，跳过")
                return

            data_dir = Path("data/processed")
            price_files = sorted(data_dir.glob("price_*.parquet"))

            stocks_added = 0
            klines_added = 0

            for f in price_files:
                code = f.stem.replace("price_", "")
                try:
                    df = pd.read_parquet(f)
                    if "date" not in df.columns:
                        continue
                    df["date"] = pd.to_datetime(df["date"])

                    # 判断市场
                    market = "SH" if code.endswith(".SH") else "SZ"

                    # 股票名——从代码推断（MVP简化）
                    name = code  # 生产环境从 baostock 或 Tushare 获取

                    stock = Stock(code=code, name=name, market=market)
                    db.add(stock)
                    stocks_added += 1

                    # 最近60天K线（API只需这些）
                    recent = df.sort_values("date").tail(60)
                    for _, row in recent.iterrows():
                        kline = DailyKLine(
                            code=code,
                            trade_date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                            open=float(row.get("open", 0)),
                            high=float(row.get("high", 0)),
                            low=float(row.get("low", 0)),
                            close=float(row.get("close", 0)),
                            volume=float(row.get("volume", 0)),
                            amount=float(row.get("amount", 0)) if pd.notna(row.get("amount", 0)) else None,
                            turnover_rate=float(row.get("turn", 0)) if pd.notna(row.get("turn", 0)) else None,
                            pct_change=float(row.get("pctChg", 0)) if pd.notna(row.get("pctChg", 0)) else None,
                        )
                        db.add(kline)
                        klines_added += 1

                except Exception as e:
                    print(f"  [Seed] 跳过 {code}: {str(e)[:50]}")
                    continue

            await db.commit()
            print(f"[Seed] 完成: {stocks_added} 只股票, {klines_added} 条K线")

    asyncio.run(_seed())


def generate_daily_pool():
    """用简单规则生成每日精选池（MVP——生产环境用LightGBM模型）"""
    from app.models.database import async_session
    from app.models.stock_models import Stock, DailyKLine, MultiFactorScore
    import asyncio

    async def _gen():
        async with async_session() as db:
            from sqlalchemy import select, desc

            # 获取所有股票
            result = await db.execute(select(Stock))
            stocks = result.scalars().all()

            scores = []
            for stock in stocks:
                # 取最近K线计算简单评分
                kline_result = await db.execute(
                    select(DailyKLine)
                    .where(DailyKLine.code == stock.code)
                    .order_by(DailyKLine.trade_date.desc())
                    .limit(20)
                )
                klines = kline_result.scalars().all()
                if len(klines) < 10:
                    continue

                closes = [k.close for k in reversed(klines)]
                volumes = [k.volume for k in reversed(klines)]

                # 简单评分：近期动量(40%) + 量比(30%) + 波动适中(30%)
                ret_5d = (closes[-1] / closes[-6] - 1) if len(closes) > 5 else 0
                ret_10d = (closes[-1] / closes[-11] - 1) if len(closes) > 10 else 0
                vol_ratio = volumes[-1] / (sum(volumes[-6:-1]) / 5) if len(volumes) >= 6 else 1
                volatility = np.std(closes[-10:]) / np.mean(closes[-10:]) if len(closes) >= 10 else 0

                momentum_score = min(100, max(0, 50 + ret_5d * 200 + ret_10d * 100))
                volume_score = min(100, max(0, vol_ratio * 30))
                quality_score = min(100, max(0, 60 - volatility * 200))

                overall = momentum_score * 0.4 + volume_score * 0.3 + quality_score * 0.3

                scores.append((stock.code, overall, momentum_score, volume_score, quality_score))

            # Top 20
            scores.sort(key=lambda x: x[1], reverse=True)
            top20 = scores[:20]

            today = date.today()
            for i, (code, overall, mom, vol, qual) in enumerate(top20):
                mfs = MultiFactorScore(
                    code=code,
                    trade_date=today,
                    overall_score=overall,
                    momentum_score=mom,
                    value_score=50,
                    quality_score=qual,
                    sentiment_score=50,
                    technical_score=vol,
                )
                db.add(mfs)

            await db.commit()
            print(f"[Pool] 生成 {len(top20)} 只精选, Top3: {', '.join(f'{c}({s:.0f})' for c, s, _, _, _ in top20[:3])}")

    asyncio.run(_gen())


if __name__ == "__main__":
    print("[Seed] 灌入股票数据...")
    seed_stock_metadata()
    print("[Pool] 生成每日精选池...")
    generate_daily_pool()
    print("[Done]")
