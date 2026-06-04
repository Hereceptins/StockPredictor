"""
A股交易日历 —— 剔除节假日和调休，防止回测中非交易日产生信号。

关键功能：
1. 判断某日是否为交易日
2. 获取 T+N 后的交易日（用于计算持有期到期日）
3. 成分股调整日期（6月和12月第二个周五后第一个交易日生效）
4. 申万行业分类切换日期（2022-01-01）
"""

from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

# ============================================================================
# 成分股调整日历
# ============================================================================

# 沪深300/中证500/中证1000 成分股调整生效日期（历史 + 回测期）
# 规则：6月和12月的第二个周五收盘后宣布，下一个交易日生效
CONSTITUENT_REBALANCE_DATES = {
    # 格式：生效日期
    "20180611", "20181217",
    "20190610", "20191216",
    "20200615", "20201214",
    "20210614", "20211213",
    "20220613", "20221212",
    "20230612", "20231211",
    "20240617",  # 2024年6月（预估，通常在第二个周五后周一）
}

# 申万行业分类切换日期
SHENWAN_RECLASSIFICATION_DATE = date(2022, 1, 1)
# 2021年底前：28个一级行业（旧版）
# 2022年起  ：31个一级行业（新版）


# ============================================================================
# 交易日历
# ============================================================================

class TradingCalendar:
    """
    A股交易日历。

    数据来源优先级：
    1. Tushare trade_cal 接口
    2. AKShare tool_trade_date_hist_sina
    3. 本地缓存文件 data/processed/trade_calendar.parquet
    """

    def __init__(self):
        self._trade_dates: set[date] | None = None
        self._trade_dates_list: list[date] | None = None

    def load(self, start: str = "20180101", end: str = "20251231") -> "TradingCalendar":
        """加载交易日历。尝试 Tushare → AKShare → 本地文件。"""
        try:
            self._load_from_tushare(start, end)
        except Exception:
            try:
                self._load_from_akshare()
            except Exception:
                self._load_from_cache()

        if self._trade_dates is None or len(self._trade_dates) == 0:
            raise RuntimeError(
                "无法加载交易日历。请检查 Tushare token 或网络连接。"
            )
        return self

    def _load_from_tushare(self, start: str, end: str) -> None:
        """从 Tushare 加载交易日历"""
        import tushare as ts
        from app.config import load_tushare_token
        token = load_tushare_token()
        if not token:
            raise ValueError("TUSHARE_TOKEN 未设置")
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end)
        self._trade_dates = set(
            date.fromisoformat(row.cal_date)
            for row in df.itertuples()
            if row.is_open == 1
        )
        self._trade_dates_list = sorted(self._trade_dates)

    def _load_from_akshare(self) -> None:
        """从 AKShare 加载交易日历"""
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        self._trade_dates = set(
            d.date() if hasattr(d, 'date') else pd.Timestamp(d).date()
            for d in df["trade_date"]
        )
        self._trade_dates_list = sorted(self._trade_dates)

    def _load_from_cache(self) -> None:
        """从本地缓存加载"""
        import pandas as pd
        cache_path = "data/processed/trade_calendar.parquet"
        try:
            df = pd.read_parquet(cache_path)
            self._trade_dates = set(
                date.fromisoformat(str(d)) for d in df["trade_date"]
            )
            self._trade_dates_list = sorted(self._trade_dates)
        except FileNotFoundError:
            self._trade_dates = None

    def save_cache(self) -> None:
        """保存交易日历到本地"""
        import pandas as pd
        if self._trade_dates_list:
            df = pd.DataFrame({
                "trade_date": [d.isoformat() for d in self._trade_dates_list]
            })
            df.to_parquet("data/processed/trade_calendar.parquet", index=False)

    def is_trading_day(self, d: date) -> bool:
        """判断是否为交易日"""
        if self._trade_dates is None:
            raise RuntimeError("交易日历未加载，请先调用 .load()")
        return d in self._trade_dates

    def next_trading_day(self, d: date, n: int = 1) -> date:
        """获取 d 之后第 n 个交易日（n>=1）"""
        if self._trade_dates_list is None:
            raise RuntimeError("交易日历未加载")
        # 找到 d 之后的第一个交易日
        idx = 0
        for i, td in enumerate(self._trade_dates_list):
            if td > d:
                idx = i
                break
        target_idx = idx + n - 1
        if target_idx >= len(self._trade_dates_list):
            return self._trade_dates_list[-1]
        return self._trade_dates_list[target_idx]

    def prev_trading_day(self, d: date, n: int = 1) -> date:
        """获取 d 之前第 n 个交易日"""
        if self._trade_dates_list is None:
            raise RuntimeError("交易日历未加载")
        for i, td in enumerate(self._trade_dates_list):
            if td >= d:
                target_idx = max(0, i - n)
                return self._trade_dates_list[target_idx]
        return self._trade_dates_list[-n]

    def trading_days_between(self, start: date, end: date) -> list[date]:
        """获取 start 到 end 之间的所有交易日（含两端）"""
        if self._trade_dates_list is None:
            raise RuntimeError("交易日历未加载")
        return [d for d in self._trade_dates_list if start <= d <= end]

    @property
    def all_trading_days(self) -> list[date]:
        if self._trade_dates_list is None:
            raise RuntimeError("交易日历未加载")
        return self._trade_dates_list


# 全局单例
_calendar: TradingCalendar | None = None


def get_calendar() -> TradingCalendar:
    """获取全局交易日历单例（懒加载）"""
    global _calendar
    if _calendar is None:
        _calendar = TradingCalendar().load()
    return _calendar


def is_constituent_rebalance_date(d: date) -> bool:
    """判断是否为成分股调整生效日"""
    return d.strftime("%Y%m%d") in CONSTITUENT_REBALANCE_DATES
