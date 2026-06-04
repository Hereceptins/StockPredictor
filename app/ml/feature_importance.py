"""
特征重要性分析 —— SHAP值 + LightGBM内置重要性。

用于回测达标后诊断：
- 哪些特征贡献最大？
- 是否存在冗余特征？
- 特征方向是否与直觉一致？
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from app.ml.model_lgb import StockPredictor


def analyze_feature_importance(
    model: StockPredictor,
    X: pd.DataFrame,
    top_n: int = 20,
    save_path: str | None = None,
) -> pd.DataFrame:
    """
    特征重要性分析。

    Args:
        model: 训练好的模型
        X: 特征矩阵
        top_n: 展示前N个重要特征
        save_path: 图表保存路径

    Returns:
        特征重要性 DataFrame
    """
    importance_df = model.get_feature_importance()
    top_features = importance_df.head(top_n)

    # 打印
    print("\n" + "=" * 60)
    print(f"  Top {top_n} 特征重要性（Gain）")
    print("=" * 60)
    for _, row in top_features.iterrows():
        bar = "█" * int(row["importance"] / top_features["importance"].max() * 40)
        print(f"  {row['feature']:<35} {row['importance']:>10.1f}  {bar}")

    # 按类别汇总
    category_importance = _group_by_category(importance_df)
    print("\n  --- 按类别汇总 ---")
    for cat, imp in category_importance.items():
        print(f"  {cat:<20} {imp:>10.1f}")

    # 绘图
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 左图：Top N 特征重要性
    ax1 = axes[0]
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(top_features)))
    ax1.barh(range(len(top_features)), top_features["importance"].values[::-1], color=colors[::-1])
    ax1.set_yticks(range(len(top_features)))
    ax1.set_yticklabels(top_features["feature"].values[::-1], fontsize=8)
    ax1.set_xlabel("Importance (Gain)")
    ax1.set_title(f"Top {top_n} Feature Importance")

    # 右图：按类别汇总
    ax2 = axes[1]
    cat_colors = plt.cm.Set2(np.linspace(0, 1, len(category_importance)))
    ax2.pie(
        category_importance.values(),
        labels=category_importance.keys(),
        autopct="%1.1f%%",
        colors=cat_colors,
        textprops={"fontsize": 8},
    )
    ax2.set_title("Feature Importance by Category")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"\n  图表已保存: {save_path}")
    else:
        plt.show()

    return importance_df


def _group_by_category(importance_df: pd.DataFrame) -> dict[str, float]:
    """按特征类别汇总重要性"""
    category_map = {
        "ret_": "return",
        "volatility_": "risk",
        "volume_": "volume_price",
        "ma_": "ma",
        "northbound_": "northbound",
        "margin_": "margin",
        "active_buy_": "active_buy",
        "sector_": "sector",
        "anomaly_": "anomaly",
        "days_to_": "unlock",
        "day_of_week": "calendar",
        "is_month_": "calendar",
        "is_earnings_": "calendar",
    }

    categories: dict[str, float] = {}
    for _, row in importance_df.iterrows():
        cat = "other"
        for prefix, name in category_map.items():
            if row["feature"].startswith(prefix):
                cat = name
                break
        categories[cat] = categories.get(cat, 0) + row["importance"]

    return dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))


if __name__ == "__main__":
    print("特征重要性分析 —— 在回测达标后运行")
    print("用法: 在 backtest.py 中训练模型后，传入 model 和 X_test")
