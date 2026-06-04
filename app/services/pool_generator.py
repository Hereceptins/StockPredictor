"""
每日精选池生成器 —— 启动时和每日收盘后运行。
MVP版：简单多因子评分（动量+量价+波动率）。
生产版：替换为 LightGBM 模型预测。
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


class PoolGenerator:
    """精选池生成器"""

    def __init__(self, data_dir: str = "data/processed"):
        self.data_dir = Path(data_dir)
        self._price_cache: dict[str, pd.DataFrame] = {}

    def load_prices(self) -> dict[str, pd.DataFrame]:
        """加载所有已回填的价格数据"""
        if self._price_cache:
            return self._price_cache

        for f in sorted(self.data_dir.glob("price_*.parquet")):
            code = f.stem.replace("price_", "")
            try:
                df = pd.read_parquet(f)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                self._price_cache[code] = df.sort_values("date")
            except Exception:
                continue
        return self._price_cache

    def generate(self, top_n: int = 20) -> list[dict]:
        """
        生成今日精选池。

        评分 = 动量(40%) + 量价(30%) + 低波动(30%)
        """
        prices = self.load_prices()
        if not prices:
            return []

        results = []
        for code, df in prices.items():
            if len(df) < 20:
                continue
            recent = df.tail(20)
            closes = recent["close"].values
            volumes = recent["volume"].values if "volume" in recent.columns else np.ones(20)

            # 动量评分：近5日和近10日收益率
            ret_5d = (closes[-1] / closes[-6] - 1) if len(closes) > 5 else 0
            ret_10d = (closes[-1] / closes[-11] - 1) if len(closes) > 10 else 0
            momentum = min(100, max(0, 50 + ret_5d * 300 + ret_10d * 150))

            # 量价评分：量比>1且价格向上=加分
            vol_ma5 = volumes[-6:-1].mean() if len(volumes) >= 6 else volumes[-1]
            vol_ratio = volumes[-1] / max(vol_ma5, 1)
            vol_up = 1 if (vol_ratio > 1.2 and ret_5d > 0.01) else 0
            volume_score = min(100, max(0, vol_ratio * 25 + vol_up * 20))

            # 低波动评分：波动率越低越好
            returns = np.diff(closes[-15:]) / closes[-15:-1]
            vol = np.std(returns) if len(returns) > 0 else 0.03
            quality_score = min(100, max(0, 70 - vol * 500))

            overall = momentum * 0.4 + volume_score * 0.3 + quality_score * 0.3

            # 方向判定
            direction = "up" if overall >= 60 else ("down" if overall < 40 else "flat")
            confidence = min(0.9, overall / 100)

            # 信号标签
            tags = []
            if ret_5d > 0.02:
                tags.append("技术突破")
            if vol_ratio > 1.5:
                tags.append("资金流入")

            results.append({
                "code": code,
                "name": code,
                "industry": None,
                "latest_price": None,
                "latest_change_pct": None,
                "direction": direction,
                "confidence": float(round(confidence, 3)),
                "overall_score": float(round(overall, 1)),
                "signal_tags": tags,
                "factor_scores": {
                    "code": code,
                    "name": code,
                    "overall_score": float(round(overall, 1)),
                    "momentum_score": float(round(momentum, 1)),
                    "value_score": 50.0,
                    "quality_score": float(round(quality_score, 1)),
                    "sentiment_score": 50.0,
                    "technical_score": float(round(volume_score, 1)),
                },
            })

        results.sort(key=lambda x: x["overall_score"], reverse=True)
        return results[:top_n]


# 全局单例
_generator: PoolGenerator | None = None


def get_pool_generator() -> PoolGenerator:
    global _generator
    if _generator is None:
        _generator = PoolGenerator()
    return _generator
