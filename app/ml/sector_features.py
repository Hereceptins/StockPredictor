"""
行业动量特征 —— 基于baostock申万行业分类 + 行业指数。

计算方式：
1. 每只股票→申万行业→同行业所有股票等权平均日收益→行业指数
2. 行业指数5日/10日收益率
3. 行业收益率在全市场的排名（分位数）
"""

from pathlib import Path

import baostock as bs
import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")


class SectorFeatureBuilder:
    """行业特征构建器"""

    def __init__(self):
        self._industry_map: dict[str, str] = {}  # ts_code → industry_name
        self._industry_returns: pd.DataFrame | None = None  # date × industry

    def build_industry_map(self, price_data: dict[str, pd.DataFrame]) -> None:
        """从baostock获取每只股票的申万行业分类"""
        bs.login()
        try:
            rs = bs.query_stock_industry()
            while rs.next():
                row = rs.get_row_data()
                # row: [update_date, code, code_name, industry, industry_class]
                bs_code = row[1]  # sh.600000
                industry = row[3] if row[3] else row[4]  # 优先取industry字段
                if not industry:
                    continue
                ts_code = bs_code[3:] + (".SH" if bs_code.startswith("sh.") else ".SZ")
                self._industry_map[ts_code] = industry
        finally:
            bs.logout()

        # 对于price_data中存在但baostock分类中没有的股票，用'其他'
        for code in price_data:
            if code not in self._industry_map:
                self._industry_map[code] = "其他"

        print(f"  行业映射: {len(self._industry_map)} 只股票, "
              f"{len(set(self._industry_map.values()))} 个行业", flush=True)

    def compute_industry_returns(
        self,
        price_data: dict[str, pd.DataFrame],
        start_date: str = "2018-01-01",
        end_date: str = "2024-06-30",
    ) -> pd.DataFrame:
        """
        计算每日每个行业的等权平均收益率。

        Returns:
            DataFrame, index=date, columns=industry_name, values=daily_return
        """
        if not self._industry_map:
            self.build_industry_map(price_data)

        # 收集每只股票的日收益率
        all_returns = []
        for code, df in price_data.items():
            industry = self._industry_map.get(code, "其他")
            if len(df) < 2:
                continue
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            df["ret"] = df["close"].pct_change()
            df["industry"] = industry
            all_returns.append(df[["date", "ret", "industry"]])

        if not all_returns:
            return pd.DataFrame()

        combined = pd.concat(all_returns, ignore_index=True)
        # 按日期+行业分组，计算等权平均
        industry_daily = combined.groupby(["date", "industry"])["ret"].mean().reset_index()
        # 透视：date × industry
        industry_returns = industry_daily.pivot(
            index="date", columns="industry", values="ret"
        ).fillna(0.0)

        # 裁剪日期范围
        industry_returns = industry_returns.loc[start_date:end_date]

        self._industry_returns = industry_returns
        return industry_returns

    def get_sector_features(
        self, stock_code: str, date: pd.Timestamp
    ) -> dict[str, float]:
        """获取单只股票在某个日期的行业特征"""
        industry = self._industry_map.get(stock_code, "其他")
        if self._industry_returns is None:
            return {}

        if date not in self._industry_returns.index:
            # 找最近的前一个日期
            prev_dates = self._industry_returns.index[
                self._industry_returns.index <= date
            ]
            if len(prev_dates) == 0:
                return {}
            date = prev_dates[-1]

        sector_rets = self._industry_returns.loc[:date]
        if industry not in sector_rets.columns:
            return {}

        ind_ret = sector_rets[industry]

        # 行业5日/10日累计收益
        ret_5d = ind_ret.iloc[-5:].sum() if len(ind_ret) >= 5 else 0
        ret_10d = ind_ret.iloc[-10:].sum() if len(ind_ret) >= 10 else 0

        # 行业排名（分位数，0=最差，1=最好）
        sector_5d = sector_rets.iloc[-5:].sum() if len(sector_rets) >= 5 else pd.Series()
        if len(sector_5d) > 0 and industry in sector_5d.index:
            rank = sector_5d.rank(pct=True).get(industry, 0.5)
        else:
            rank = 0.5

        return {
            "sector_ret_5d": ret_5d,
            "sector_ret_10d": ret_10d,
            "sector_rank": rank,
        }
