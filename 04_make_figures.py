import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MAIN_CSV = "results/main_table.csv"
FAMILY_CSV = "results/per_family_recall.csv"
FIG_MAIN = "figures/random_vs_cross.png"
FIG_FAMILY = "figures/per_family_recall.png"

EXPERIMENTS = ["A: 2017 random split", "B: train 2017, test 2018",
               "C: train 2018, test 2017", "Ref: 2018 random split"]
MODELS = ["RF", "LightGBM", "MLP"]
FAMILIES = ["DoS", "DDoS", "Brute force", "Web attack", "Bot", "Infiltration"]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK = "#52514e"
BAR_W = 0.2


def style(ax, title: str):
    ax.set_title(title, color=INK, fontsize=10)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.set_axisbelow(True)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)


def grouped_bars(ax, table: pd.DataFrame, groups: list[str], group_col: str, value: str, err: str):
    x = np.arange(len(groups))
    for i, exp in enumerate(EXPERIMENTS):
        sub = table[table["experiment"] == exp].set_index(group_col).reindex(groups)
        ax.bar(x + (i - 1.5) * BAR_W, sub[value], BAR_W * 0.9, yerr=sub[err],
               color=COLORS[i], label=exp, error_kw={"lw": 0.8, "ecolor": INK})
    ax.set_xticks(x, groups)


def plot_main():
    main = pd.read_csv(MAIN_CSV)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, metric, title in zip(axes, ["macro_f1", "attack_recall", "benign_fpr"],
                                 ["Macro F1", "Attack recall", "False positive rate on benign"]):
        grouped_bars(ax, main, MODELS, "model", f"{metric}_mean", f"{metric}_std")
        style(ax, title)
    axes[0].set_ylim(0, 1.05)
    axes[1].set_ylim(0, 1.05)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("Random split vs cross-dataset (mean over 3 seeds, bars show std)", color=INK)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(FIG_MAIN, dpi=130)


def plot_families():
    fam = pd.read_csv(FAMILY_CSV)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), sharey=True)
    for ax, model in zip(axes, MODELS):
        grouped_bars(ax, fam[fam["model"] == model], FAMILIES, "family", "recall_mean", "recall_std")
        ax.tick_params(axis="x", rotation=20)
        ax.set_ylim(0, 1.05)
        style(ax, model)
    axes[0].set_ylabel("Recall", color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("Per-family attack recall (families present in both datasets)", color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.savefig(FIG_FAMILY, dpi=130)


def main():
    plot_main()
    plot_families()
    print(f"wrote {FIG_MAIN} and {FIG_FAMILY}")


if __name__ == "__main__":
    main()
