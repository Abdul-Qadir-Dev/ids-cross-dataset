import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

DATA_2017 = "data/processed/cic2017.parquet"
DATA_2018 = "data/processed/cic2018_sample.parquet"
IMPORTANCE_CSV = "results/lgbm_importance.csv"
SHIFT_CSV = "results/feature_shift.csv"
FIGURE = "figures/feature_shift.png"

TOP_N = 10
PLOT_ROWS = 200_000
SEED = 0
COLOR_2017 = "#2a78d6"
COLOR_2018 = "#eb6834"
INK = "#52514e"


def ks_row(df17: pd.DataFrame, df18: pd.DataFrame, feature: str) -> dict:
    b17, b18 = df17["attack"] == 0, df18["attack"] == 0
    return {
        "feature": feature,
        "ks_all": ks_2samp(df17[feature], df18[feature]).statistic,
        "ks_benign": ks_2samp(df17.loc[b17, feature], df18.loc[b18, feature]).statistic,
        "ks_attack": ks_2samp(df17.loc[~b17, feature], df18.loc[~b18, feature]).statistic,
        "median_benign_2017": df17.loc[b17, feature].median(),
        "median_benign_2018": df18.loc[b18, feature].median(),
    }


def ecdf(values: pd.Series, rng) -> tuple[np.ndarray, np.ndarray]:
    x = values.to_numpy()
    if len(x) > PLOT_ROWS:
        x = rng.choice(x, PLOT_ROWS, replace=False)
    x = np.sort(x)
    return x, np.arange(1, len(x) + 1) / len(x)


def plot_shift(df17, df18, shift: pd.DataFrame):
    rng = np.random.default_rng(SEED)
    fig, axes = plt.subplots(2, 5, figsize=(16, 6.5), sharey=True)
    for ax, row in zip(axes.flat, shift.itertuples()):
        for df, color, year in [(df17, COLOR_2017, "2017"), (df18, COLOR_2018, "2018")]:
            for cls, style in [(0, "-"), (1, "--")]:
                x, y = ecdf(df.loc[df["attack"] == cls, row.feature], rng)
                ax.plot(x, y, style, color=color, lw=1.6,
                        label=f"{year} {'benign' if cls == 0 else 'attack'}")
        ax.set_xscale("symlog", linthresh=1)
        # 35 rows of 2017 have Fwd Header Length down to -3e10 (a CICFlowMeter bug); cut them off
        ax.set_xlim(left=-1)
        ax.set_title(f"{row.feature}\nKS benign {row.ks_benign:.2f}, attack {row.ks_attack:.2f}",
                     fontsize=9, color=INK)
        ax.tick_params(labelsize=8, colors=INK)
        ax.grid(alpha=0.25, lw=0.5)
        for side in ["top", "right"]:
            ax.spines[side].set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("ECDF", color=INK)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("Top 10 LightGBM features (trained on 2017): 2017 vs 2018, symlog x axis from -1 "
                 "(35 negative 2017 header lengths off the left edge)", color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(FIGURE, dpi=130)


def main():
    top = pd.read_csv(IMPORTANCE_CSV)["feature"].head(TOP_N).tolist()
    cols = top + ["attack"]
    df17 = pd.read_parquet(DATA_2017, columns=cols)
    df18 = pd.read_parquet(DATA_2018, columns=cols)
    shift = pd.DataFrame([ks_row(df17, df18, f) for f in top])
    shift.round(4).to_csv(SHIFT_CSV, index=False)
    print(shift.round(3).to_string(index=False))
    plot_shift(df17, df18, shift)
    print(f"wrote {SHIFT_CSV} and {FIGURE}")


if __name__ == "__main__":
    main()
