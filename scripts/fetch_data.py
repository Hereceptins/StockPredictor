"""
数据可用性检查 + 数据采集。

在开始任何回测之前运行此脚本，确认所有数据源可用。
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import (
    backtest_cfg,
    datasource_cfg,
    load_tushare_token,
)


# ============================================================================
# 数据可用性检查
# ============================================================================

class DataAvailabilityReport:
    """报告每个数据源的可用状态和限制"""

    def __init__(self):
        self.results: dict[str, dict] = {}

    def add(self, name: str, available: bool, detail: str = "",
            daily_limit: int | None = None, note: str = "") -> None:
        self.results[name] = {
            "available": available,
            "detail": detail,
            "daily_limit": daily_limit,
            "note": note,
        }

    def print_report(self) -> None:
        print("\n" + "=" * 70)
        print("  数据源可用性检查报告")
        print("=" * 70)
        for name, info in self.results.items():
            status = "[OK] 可用" if info["available"] else "[!!] 不可用"
            print(f"\n  {name}: {status}")
            if info["detail"]:
                print(f"    详情: {info['detail']}")
            if info["daily_limit"]:
                print(f"    日限额: {info['daily_limit']} 次")
            if info["note"]:
                print(f"    [!]  {info['note']}")
        print("\n" + "=" * 70)

    def all_critical_available(self) -> bool:
        """关键数据源是否都可用（至少有一个可用的日线源）"""
        critical_sources = ["Tushare日线行情", "AKShare日线行情"]
        return any(
            self.results.get(s, {}).get("available", False)
            for s in critical_sources
        )


def check_data_availability() -> DataAvailabilityReport:
    """检查所有数据源的可用性"""
    report = DataAvailabilityReport()

    # 1. Tushare 日线行情
    token = load_tushare_token()
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.daily(ts_code="000001.SZ", start_date="20240601", end_date="20240601")
            available = len(df) > 0
            report.add(
                "Tushare日线行情", available,
                detail=f"测试返回 {len(df)} 行" if available else "返回空数据",
                daily_limit=500 if available else None,
                note="免费额度够用，但月度总量有限制" if available else "检查 TUSHARE_TOKEN"
            )
        except Exception as e:
            report.add("Tushare日线行情", False, detail=str(e),
                       note="检查 TUSHARE_TOKEN 是否正确设置")
    else:
        report.add("Tushare日线行情", False, detail="TUSHARE_TOKEN 未设置",
                   note="可通过环境变量或 .env 文件设置")

    # 2. Tushare 沪深港通资金流向
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.moneyflow_hsgt(start_date="20240601", end_date="20240601")
            available = len(df) > 0
            report.add(
                "Tushare沪深港通", available,
                detail=f"测试返回 {len(df)} 行" if available else "返回空数据",
                daily_limit=5000 if available else None,
                note="每日5000条，1800只够用但余量不多" if available else ""
            )
        except Exception as e:
            report.add("Tushare沪深港通", False, detail=str(e))
    else:
        report.add("Tushare沪深港通", False, detail="TUSHARE_TOKEN 未设置")

    # 3. Tushare 融资融券明细
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.margin_detail(trade_date="20240601")
            available = len(df) > 0
            report.add(
                "Tushare融资融券明细", available,
                detail=f"测试返回 {len(df)} 行" if available else "可能需要更高积分",
                note="若不可用→使用行业级别两融数据替代" if not available else ""
            )
        except Exception as e:
            report.add("Tushare融资融券明细", False, detail=str(e),
                       note="降级方案：AKShare stock_margin_detail_szse/sse")
    else:
        report.add("Tushare融资融券明细", False, detail="TUSHARE_TOKEN 未设置")

    # 4. Tushare 指数成分股
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.index_member(index_code="000300.SH", trade_date="20240601")
            available = len(df) > 0
            report.add(
                "Tushare指数成分股", available,
                detail=f"测试返回 {len(df)} 行" if available else "可能需要更高积分",
                note="用于幸存者偏差控制" + ("" if available else "→降级：使用当前固定成分股")
            )
        except Exception as e:
            report.add("Tushare指数成分股", False, detail=str(e),
                       note="降级：使用固定成分股列表（SURVIVORSHIP_BIAS_CONTROL=False）")
    else:
        report.add("Tushare指数成分股", False, detail="TUSHARE_TOKEN 未设置")

    # 5. AKShare 日线行情
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                                start_date="20240601", end_date="20240601")
        available = len(df) > 0
        report.add(
            "AKShare日线行情", available,
            detail=f"测试返回 {len(df)} 行" if available else "返回空数据",
            note="免费、无注册、数据延迟3-15分钟"
        )
    except Exception as e:
        report.add("AKShare日线行情", False, detail=str(e),
                   note="Tushare不可用时的降级方案")

    # 6. AKShare 北向资金
    try:
        import akshare as ak
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        available = len(df) > 0
        report.add(
            "AKShare北向资金", available,
            detail=f"测试返回 {len(df)} 行" if available else "返回空数据",
            note="Tushare沪深港通的免费替代"
        )
    except Exception as e:
        report.add("AKShare北向资金", False, detail=str(e))

    # 7. Tushare 5分钟K线
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.stk_mins(ts_code="000001.SZ", freq="5min",
                              start_date="20240601", end_date="20240601")
            available = len(df) > 0
            report.add(
                "Tushare 5分钟K线", available,
                detail=f"测试返回 {len(df)} 行" if available else "可能需要更高积分或专业版",
                note="免费额度非常有限" + ("→仅用于主动买卖占比计算" if available else "→降级：15分钟K线或日线近似")
            )
        except Exception as e:
            report.add("Tushare 5分钟K线", False, detail=str(e),
                       note="降级：15分钟K线 或 仅用日线数据")
    else:
        report.add("Tushare 5分钟K线", False, detail="TUSHARE_TOKEN 未设置")

    return report


# ============================================================================
# 命令行入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据源可用性检查")
    parser.add_argument("--check", action="store_true", default=True,
                        help="运行数据可用性检查")
    args = parser.parse_args()

    print("StockPredictor — 数据源可用性检查")
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"回测区间: {backtest_cfg.backtest_start} → {backtest_cfg.backtest_end}")

    report = check_data_availability()
    report.print_report()

    if not report.all_critical_available():
        print("\n[!!] 关键数据源不可用，无法继续。请检查配置。")
        sys.exit(1)
    else:
        print("\n[OK] 关键数据源可用，可以开始回测。")
