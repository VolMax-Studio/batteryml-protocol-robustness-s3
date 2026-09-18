#!/usr/bin/env python3
"""
Generate publication-quality figures for BatteryML Protocol Robustness S3.
Saves plots into the `figures/` directory.
"""

import json
import os
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# Ensure output directory exists
FIGURES_DIR = Path(__file__).resolve().parent.parent / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Load data
DATA_PATH = Path(__file__).resolve().parent.parent / "s3_execution_output" / "s3-artifact" / "adjudication_candidate.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

summaries = data["split_summaries"]

# Styling configuration
plt.rcParams.update({
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
    "font.family": "sans-serif",
    "figure.titlesize": 16,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "figure.dpi": 300,
})

# -------------------------------------------------------------
# Figure 1: Relative RMSE Change Distribution (D^RMSE)
# -------------------------------------------------------------
def plot_d_rmse_distribution():
    fig, ax = plt.subplots(figsize=(10, 6.5))
    
    models = ["ridge", "variance", "xgb", "dummy"]
    labels = ["Ridge\n(p_abs=90.6%)", "Variance\n(p_abs=31.3%)", "XGBoost\n(p_abs=43.8%)", "Dummy Baseline\n(p_abs=46.9%)"]
    colors = ["#E63946", "#457B9D", "#2A9D8F", "#6C757D"]
    
    data_by_model = []
    for m in ["ridge", "variance", "xgb"]:
        data_by_model.append([s["d_rmse"][m] * 100 for s in summaries])
    data_by_model.append([s["dummy_d_rmse"] * 100 for s in summaries])
    
    # Material threshold band (+/- 10%)
    ax.axhspan(-10, 10, color="#E9ECEF", alpha=0.7, zorder=1, label="Material Threshold Band (±10%)")
    ax.axhline(0, color="#6C757D", linestyle="--", linewidth=1, zorder=2)
    ax.axhline(10, color="#E63946", linestyle=":", linewidth=1.2, alpha=0.6)
    ax.axhline(-10, color="#E63946", linestyle=":", linewidth=1.2, alpha=0.6)
    
    # Box plot
    bp = ax.boxplot(
        data_by_model,
        positions=range(len(models)),
        widths=0.45,
        patch_artist=True,
        showmeans=False,
        showfliers=False,
        zorder=3
    )
    
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
        patch.set_edgecolor(color)
        patch.set_linewidth(1.8)
        
    for median in bp["medians"]:
        median.set_color("#1D3557")
        median.set_linewidth(2.2)
        
    for whisker in bp["whiskers"]:
        whisker.set_color("#495057")
        whisker.set_linewidth(1.2)
        
    for cap in bp["caps"]:
        cap.set_color("#495057")
        cap.set_linewidth(1.2)

    # Jittered scatter points for all 64 partitions
    np.random.seed(42)
    for i, (vals, color) in enumerate(zip(data_by_model, colors)):
        jitter = np.random.normal(0, 0.06, size=len(vals))
        ax.scatter(
            i + jitter,
            vals,
            color=color,
            alpha=0.65,
            s=36,
            edgecolors="none",
            zorder=4
        )
        
        # Annotate median
        med = np.median(vals)
        sign = "+" if med > 0 else ""
        ax.text(
            i,
            med + (4 if med >= 0 else -6),
            f"Median: {sign}{med:.1f}%",
            ha="center",
            va="bottom" if med >= 0 else "top",
            fontweight="bold",
            fontsize=10.5,
            color="#1D3557",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="none"),
            zorder=5
        )

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(labels, fontweight="medium")
    ax.set_ylabel("Relative RMSE Change vs Split A (%)")
    ax.set_title("Distribution of Relative RMSE Change Across K=64 Partitions (MATR1)", pad=15, fontweight="bold")
    
    # Annotate verdict
    ax.text(
        0.02, 0.94,
        "Governing Verdict: MODEL_SPECIFIC\n• Ridge: Material Prevalent (p_abs = 90.6%, p_pos = 85.9%)\n• Variance & XGBoost: Below 50% Threshold\n• Dummy Composition Flag: Inactive (46.9%)",
        transform=ax.transAxes,
        fontsize=10,
        va="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#F8F9FA", edgecolor="#CED4DA", alpha=0.95),
        zorder=6
    )
    
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
    ax.set_ylim(-65, 130)
    plt.tight_layout()
    
    out_path = FIGURES_DIR / "s3_d_rmse_distribution.png"
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# Figure 2: Ranking Inversion Across 64 Splits
# -------------------------------------------------------------
def plot_ranking_inversions():
    fig, ax = plt.subplots(figsize=(9, 4.5))
    
    # 45 splits inverted (Variance > Ridge > XGB), 19 splits baseline (Ridge > Variance > XGB)
    orders = [
        "Inverted Ordering\n(Variance > Ridge > XGBoost)",
        "Split A Baseline Ordering\n(Ridge > Variance > XGBoost)"
    ]
    counts = [45, 19]
    percentages = [45 / 64 * 100, 19 / 64 * 100]
    colors = ["#E63946", "#457B9D"]
    
    bars = ax.barh(orders, counts, color=colors, height=0.5, alpha=0.85, edgecolor="#1D3557", linewidth=1.2)
    
    for bar, count, pct in zip(bars, counts, percentages):
        width = bar.get_width()
        ax.text(
            width + 1.2,
            bar.get_y() + bar.get_height() / 2,
            f"{count} / 64 splits ({pct:.1f}%)",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
            color="#1D3557"
        )
        
    ax.set_xlim(0, 70)
    ax.set_xlabel("Number of Partitions (out of K=64)")
    ax.set_title("Model Ranking Shifts Across Protocol-Disjoint Partitions", pad=15, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.invert_yaxis()
    
    plt.tight_layout()
    out_path = FIGURES_DIR / "s3_ranking_inversion.png"
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# Figure 3: Outlier Cell b2c1 Sensitivity Index J
# -------------------------------------------------------------
def plot_b2c1_sensitivity():
    fig, ax = plt.subplots(figsize=(9, 4.8))
    
    models = ["Ridge", "Variance", "XGBoost", "Dummy"]
    # Extract b2c1_j medians and IQRs
    ridge_j = [s["b2c1_j"]["ridge"] for s in summaries]
    var_j = [s["b2c1_j"]["variance"] for s in summaries]
    xgb_j = [s["b2c1_j"]["xgb"] for s in summaries]
    dummy_j = [s["b2c1_j"]["dummy"] for s in summaries]
    
    all_j = [ridge_j, var_j, xgb_j, dummy_j]
    colors = ["#E63946", "#457B9D", "#2A9D8F", "#6C757D"]
    
    bp = ax.boxplot(
        all_j,
        positions=range(len(models)),
        widths=0.45,
        patch_artist=True,
        showmeans=False,
        showfliers=False
    )
    
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.4)
        patch.set_edgecolor(color)
        patch.set_linewidth(1.8)
        
    for median in bp["medians"]:
        median.set_color("#1D3557")
        median.set_linewidth(2.2)
        
    np.random.seed(42)
    for i, (vals, color) in enumerate(zip(all_j, colors)):
        jitter = np.random.normal(0, 0.05, size=len(vals))
        ax.scatter(i + jitter, vals, color=color, alpha=0.6, s=30)
        med = np.median(vals)
        ax.text(
            i,
            med + (0.25 if i == 0 else 0.15),
            f"Median J: {med:.2f}",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=10,
            color="#1D3557"
        )
        
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, fontweight="medium")
    ax.set_ylabel("Outlier Leverage Index J(b2c1)")
    ax.set_title("Single-Cell Outlier Leverage: Sensitivity to Cell b2c1", pad=15, fontweight="bold")
    ax.axhline(0, color="#6C757D", linestyle="--", linewidth=1)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_ylim(-0.5, 5.5)
    
    plt.tight_layout()
    out_path = FIGURES_DIR / "s3_outlier_sensitivity_b2c1.png"
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    plot_d_rmse_distribution()
    plot_ranking_inversions()
    plot_b2c1_sensitivity()
