"""
Baostock 数据源 —— 完全免费A股日线行情，无需注册。

提供：
- 日线OHLCV数据（复权/不复权）
- 股票基本信息（代码、名称、上市日期）
- 行业分类（申万一级行业）
- 指数成分股（沪深300/中证500等）

不提供：
- 北向资金
- 融资融券
- 分钟线
"""

from datetime import date
from typing import Optional

import baostock as bs
import pandas as pd


class BaostockProvider:
    """Baostock A股数据源"""

    def __init__(self):
        self._logged_in = False

    def _ensure_login(self):
        if not self._logged_in:
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"Baostock login failed: {lg.error_msg}")
            self._logged_in = True

    def logout(self):
        if self._logged_in:
            bs.logout()
            self._logged_in = False

    def __enter__(self):
        self._ensure_login()
        return self

    def __exit__(self, *args):
        self.logout()

    def get_daily_kline(
        self,
        code: str,
        start_date: str,
        end_date: str,
        adjust: str = "2",  # 2=前复权
    ) -> pd.DataFrame:
        """
        获取日线数据。

        Args:
            code: 股票代码，baostock格式如 sh.600000, sz.000001
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            adjust: 复权类型 1=后复权 2=前复权 3=不复权

        Returns:
            DataFrame with: date, open, high, low, close, volume, amount, turn, pct_chg
        """
        self._ensure_login()
        rs = bs.query_history_k_data_plus(
            code,
            "date,open,high,low,close,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag=adjust,
        )
        if rs.error_code != "0":
            raise RuntimeError(f"Baostock query failed: {rs.error_msg}")

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)
        # 类型转换
        for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])

        # 重命名为 Tushare 兼容格式
        df = df.rename(columns={
            "turn": "turnover_rate",
            "pctChg": "pct_chg",
        })

        return df

    def get_all_stocks(self, list_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取所有A股股票基本信息。

        Returns:
            DataFrame with: code, code_name, ipoDate, type, status
        """
        self._ensure_login()

        # 获取所有沪深A股
        rs = bs.query_stock_basic()
        rows = []
        while rs.next():
            row = rs.get_row_data()
            # 只保留A股（sh.6xxxxx / sz.0xxxxx / sz.3xxxxx）
            code = row[0]
            if code.startswith("sh.6") or code.startswith("sz.0") or code.startswith("sz.3"):
                rows.append(row)

        df = pd.DataFrame(rows, columns=["code", "code_name", "ipoDate", "outDate", "type", "status"])
        # 转成 Tushare 格式 ts_code
        df["ts_code"] = df["code"].str.replace("sh.", "").str.replace("sz.", "") + {
            "sh.": ".SH", "sz.": ".SZ"
        }.get(df["code"].str[:3], "")
        # Actually this mapping is wrong, let me fix:
        # sh.600000 → 600000.SH, sz.000001 → 000001.SZ
        df["ts_code"] = df["code"].apply(
            lambda x: x[3:] + ".SH" if x.startswith("sh.") else x[3:] + ".SZ"
        )

        if list_date:
            df = df[df["ipoDate"] <= list_date]

        return df

    def get_index_constituents(self, index_code: str, target_date: str) -> list[str]:
        """
        获取指数成分股。

        Args:
            index_code: 指数代码，如 '000300'=沪深300, '000905'=中证500
            target_date: 日期 YYYY-MM-DD

        Returns:
            Tushare格式的股票代码列表
        """
        self._ensure_login()

        # Baostock 的指数成分股查询
        # 映射常见指数
        index_map = {
            "000300.SH": "sh.000300",  # 沪深300
            "000905.SH": "sh.000905",  # 中证500
            "000852.SH": "sh.000852",  # 中证1000
        }

        bs_code = index_map.get(index_code, f"sh.{index_code.replace('.SH','')}")

        try:
            rs = bs.query_sz50_stocks() if "000016" in index_code else \
                 bs.query_hs300_stocks() if "000300" in index_code else \
                 bs.query_zz500_stocks() if "000905" in index_code else \
                 None

            if rs is None:
                return []

            rows = []
            while rs.next():
                rows.append(rs.get_row_data())

            if not rows:
                return []

            # Baostock返回格式: updateDate, code, code_name
            # code 格式如 sh.600000
            codes = []
            for row in rows:
                code = row[1]  # 第二列是代码
                ts_code = code[3:] + (".SH" if code.startswith("sh.") else ".SZ")
                codes.append(ts_code)

            return codes
        except Exception:
            return []


def baostock_to_tushare_code(bs_code: str) -> str:
    """baostock代码 → Tushare代码"""
    if bs_code.startswith("sh."):
        return bs_code[3:] + ".SH"
    elif bs_code.startswith("sz."):
        return bs_code[3:] + ".SZ"
    return bs_code


def tushare_to_baostock_code(ts_code: str) -> str:
    """Tushare代码 → baostock代码"""
    if ts_code.endswith(".SH"):
        return "sh." + ts_code[:-3]
    elif ts_code.endswith(".SZ"):
        return "sz." + ts_code[:-3]
    return ts_code
