"""
回测指标计算 —— 三组9项验收标准。

第1组（核心收益）：
  1. 精选10只 tradable_return
  2. 胜率
  3. IC（Information Coefficient）

第2组（风险控制）：
  4. 分散20只 tradable_return
  5. 日胜率稳定性
  6. 最大回撤
  7. 换手率

第3组（Alpha真伪验证）：
  8. 分段市况稳定性（上涨/下跌/震荡）
  9. Beta中性收益（下跌市超额）
  10. 零和博弈检验（Bottom 10 vs Top 10）

所有收益统计默认使用 tradable_return（剔除涨停不可买后）。
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class BacktestResult:
    """单日回测结果"""
    date: date
    top10_stocks: list[str]
    top10_nominal_return: float  # 理论值
    top10_tradable_return: float  # 实盘预期值（剔除涨停不可买）
    top20_stocks: list[str]
    top20_nominal_return: float
    top20_tradable_return: float
    bottom10_stocks: list[str]
    bottom10_return: float
    benchmark_return: float  # 等权基准收益率
    ic: float  # 当日信息系数
    predictions: dict[str, float]  # {stock_code: predicted_return}


@dataclass
class MetricsReport:
    """完整回测指标报告"""

    # 第1组：核心收益
    top10_avg_tradable_return: float = 0.0
    top20_avg_tradable_return: float = 0.0
    win_rate: float = 0.0
    mean_ic: float = 0.0
    ic_std: float = 0.0
    icir: float = 0.0  # IC / IC_std

    # 第2组：风险控制
    daily_stability: float = 0.0  # 跑赢基准的交易日占比
    max_drawdown: float = 0.0
    daily_turnover: float = 0.0

    # 第3组：Alpha真伪
    segmented_results: dict[str, "MetricsReport"] = field(default_factory=dict)
    beta_neutral_return_bear: float = 0.0  # 下跌市中Beta中性收益
    bottom10_avg_return: float = 0.0

    # 辅助信息
    total_trading_days: int = 0
    benchmark_total_return: float = 0.0
    top10_nominal_return: float = 0.0  # 用于对比 nominal vs tradable

    # 逐日序列（用于画图和诊断）
    daily_returns: pd.Series = field(default_factory=pd.Series)
    cumulative_returns: pd.Series = field(default_factory=pd.Series)

    def to_dict(self) -> dict:
        """转为字典以便 JSON 序列化"""
        return {
            "第1组_核心收益": {
                "精选10只_tradable_return": f"{self.top10_avg_tradable_return:.4%}",
                "分散20只_tradable_return": f"{self.top20_avg_tradable_return:.4%}",
                "胜率": f"{self.win_rate:.2%}",
                "IC均值": f"{self.mean_ic:.4f}",
                "ICIR": f"{self.icir:.2f}",
            },
            "第2组_风险控制": {
                "日胜率稳定性": f"{self.daily_stability:.2%}",
                "最大回撤": f"{self.max_drawdown:.2%}",
                "每日换手率": f"{self.daily_turnover:.2%}",
            },
            "第3组_Alpha真伪": {
                "分段市况结果": {k: v.to_dict() for k, v in self.segmented_results.items()},
                "下跌市Beta中性收益": f"{self.beta_neutral_return_bear:.4%}",
                "Bottom10平均收益": f"{self.bottom10_avg_return:.4%}",
            },
            "辅助信息": {
                "总交易日": self.total_trading_days,
                "基准总收益": f"{self.benchmark_total_return:.4%}",
                "Top10名义收益(vs实盘)": f"{self.top10_nominal_return:.4%} vs {self.top10_avg_tradable_return:.4%}",
            },
        }


# ============================================================================
# 指标计算
# ============================================================================

def compute_all_metrics(
    daily_results: list[BacktestResult],
    segment_boundaries: dict[str, tuple[date, date]] | None = None,
    benchmark_beta: float = 1.0,
) -> MetricsReport:
    """
    计算全部9项验收指标。

    Args:
        daily_results: 逐日回测结果列表
        segment_boundaries: 子区间划分，如 {"下跌市": (date1, date2), ...}
        benchmark_beta: 模型组合相对基准的Beta系数

    Returns:
        MetricsReport 完整指标报告
    """
    report = MetricsReport()

    if not daily_results:
        return report

    report.total_trading_days = len(daily_results)

    # --- 第1组：核心收益 ---
    top10_tradable = np.array([r.top10_tradable_return for r in daily_results])
    top20_tradable = np.array([r.top20_tradable_return for r in daily_results])
    top10_nominal = np.array([r.top10_nominal_return for r in daily_results])

    report.top10_avg_tradable_return = float(np.mean(top10_tradable))
    report.top20_avg_tradable_return = float(np.mean(top20_tradable))
    report.top10_nominal_return = float(np.mean(top10_nominal))

    # 胜率：预测收益>0 实际也>0 的比例
    successes = sum(
        1 for r in daily_results
        if r.top10_tradable_return > 0
    )
    report.win_rate = successes / len(daily_results) if daily_results else 0

    # IC：横截面预测收益与实际收益的秩相关系数均值
    ic_values = np.array([r.ic for r in daily_results])
    report.mean_ic = float(np.mean(ic_values))
    report.ic_std = float(np.std(ic_values))
    report.icir = report.mean_ic / report.ic_std if report.ic_std > 0 else 0

    # --- 第2组：风险控制 ---
    benchmark_returns = np.array([r.benchmark_return for r in daily_results])

    # 日胜率稳定性：Top10跑赢基准的交易日占比
    outperform_days = sum(
        1 for i, r in enumerate(daily_results)
        if r.top10_tradable_return > benchmark_returns[i]
    )
    report.daily_stability = outperform_days / len(daily_results) if daily_results else 0

    # 最大回撤
    cumulative = np.cumprod(1 + top10_tradable)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    report.max_drawdown = float(np.min(drawdown))

    # 每日换手率
    if len(daily_results) > 1:
        turnovers = []
        for i in range(1, len(daily_results)):
            prev_stocks = set(daily_results[i - 1].top10_stocks)
            curr_stocks = set(daily_results[i].top10_stocks)
            overlap = len(prev_stocks & curr_stocks)
            turnover = 1 - (overlap / max(len(prev_stocks), len(curr_stocks), 1))
            turnovers.append(turnover)
        report.daily_turnover = float(np.mean(turnovers)) if turnovers else 0

    # --- 第3组：Alpha 真伪 ---
    # 分段市况稳定性
    if segment_boundaries:
        for seg_name, (seg_start, seg_end) in segment_boundaries.items():
            seg_results = [
                r for r in daily_results
                if seg_start <= r.date <= seg_end
            ]
            if seg_results:
                seg_report = compute_all_metrics(seg_results)
                report.segmented_results[seg_name] = seg_report

    # Beta中性收益（下跌市）
    bear_results = [
        r for r in daily_results
        if r.benchmark_return < 0  # 基准下跌的交易日
    ]
    if bear_results:
        bear_excess = np.array([
            r.top10_tradable_return - benchmark_beta * r.benchmark_return
            for r in bear_results
        ])
        report.beta_neutral_return_bear = float(np.mean(bear_excess))

    # 零和博弈检验：Bottom 10 的收益
    bottom10_returns = np.array([r.bottom10_return for r in daily_results])
    report.bottom10_avg_return = float(np.mean(bottom10_returns))

    # 辅助
    report.benchmark_total_return = float(np.prod(1 + benchmark_returns) - 1) if len(benchmark_returns) > 0 else 0

    # 序列数据
    report.daily_returns = pd.Series(top10_tradable, index=[r.date for r in daily_results])
    report.cumulative_returns = (1 + report.daily_returns).cumprod()

    return report


def check_acceptance(report: MetricsReport) -> dict[str, bool]:
    """
    检查是否通过所有验收标准。

    Returns:
        {指标名称: 是否达标}
    """
    from app.config import acceptance_cfg as ac

    checks = {}

    # 第1组
    checks["精选10只收益≥0.5%"] = report.top10_avg_tradable_return >= ac.top10_min_return
    checks["胜率≥55%"] = report.win_rate >= ac.win_rate_min
    checks["IC≥0.03"] = report.mean_ic >= ac.ic_min

    # 第2组
    checks["分散20只收益≥0.3%"] = report.top20_avg_tradable_return >= ac.top20_min_return
    checks["日胜率稳定性≥60%"] = report.daily_stability >= ac.daily_stability_min
    checks["最大回撤≥-15%"] = report.max_drawdown >= ac.max_drawdown_limit
    checks["换手率<30%"] = report.daily_turnover <= ac.turnover_max

    # 第3组
    passing_segments = sum(
        1 for seg in report.segmented_results.values()
        if seg.win_rate >= ac.win_rate_min
    )
    checks["分段市况(≥2个区间胜率>55%)"] = passing_segments >= ac.segmented_min_passing
    checks["下跌市Beta中性>5%"] = report.beta_neutral_return_bear >= ac.beta_neutral_min
    checks["零和博弈(Bottom10<Top10)"] = report.bottom10_avg_return < report.top10_avg_tradable_return

    return checks


def print_report(report: MetricsReport) -> None:
    """打印格式化的回测报告"""
    checks = check_acceptance(report)

    print("\n" + "=" * 70)
    print("  回测结果报告")
    print("=" * 70)

    data = report.to_dict()
    for group_name, metrics in data.items():
        status = "✅" if all(
            checks.get(k, True) for k in checks
            if group_name[:2] in k or group_name[:2] == "第"
        ) else "❌"
        print(f"\n  {group_name}:")
        if isinstance(metrics, dict):
            for k, v in metrics.items():
                if isinstance(v, dict):
                    print(f"    {k}:")
                    for sk, sv in v.items():
                        print(f"      {sk}: {sv}")
                else:
                    print(f"    {k}: {v}")

    print("\n  --- 验收结果 ---")
    all_pass = True
    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        all_pass = all_pass and passed
        print(f"    [{status}] {check_name}")

    print(f"\n  {'[OK] 全部达标！' if all_pass else '[!!] 部分指标未达标'}")

    # nominal vs tradable 差距提示
    gap = report.top10_nominal_return - report.top10_avg_tradable_return
    if gap > 0.001:  # > 0.1%
        print(f"  [!] 名义收益-实盘收益 = {gap:.4%}（涨停不可交易效应）")


def compute_ic(predictions: np.ndarray, actual_returns: np.ndarray) -> float:
    """计算横截面信息系数（Spearman秩相关系数）"""
    from scipy.stats import spearmanr
    valid = ~(np.isnan(predictions) | np.isnan(actual_returns))
    if valid.sum() < 5:  # Spearman至少需要5个数据点才可靠
        return 0.0
    pred_valid = predictions[valid]
    act_valid = actual_returns[valid]
    # 常数数组无法计算秩相关——无区分度即IC=0
    if np.std(pred_valid) < 1e-12 or np.std(act_valid) < 1e-12:
        return 0.0
    try:
        corr, _ = spearmanr(pred_valid, act_valid)
    except Exception:
        return 0.0
    return float(corr) if not np.isnan(corr) else 0.0
