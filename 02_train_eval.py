import argparse
import os
import time

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

DATA_2017 = "data/processed/cic2017.parquet"
DATA_2018 = "data/processed/cic2018_sample.parquet"
RESULTS = "results"
QUICK_RESULTS = "data/interim/quick_results"

SEEDS = [0, 1, 2]
TEST_FRAC = 0.2
QUICK_ROWS = 100_000
MODELS = ["RF", "LightGBM", "MLP"]
LABEL_COLS = ["label", "family", "attack"]
SHARED_FAMILIES = ["DoS", "DDoS", "Brute force", "Web attack", "Bot", "Infiltration"]

EXP_A = "A: 2017 random split"
EXP_B = "B: train 2017, test 2018"
EXP_C = "C: train 2018, test 2017"
EXP_REF = "Ref: 2018 random split"


def signed_log(x):
    return np.sign(x) * np.log1p(np.abs(x))


# Hyperparameters were fixed before any run and are the same for every experiment.
def make_model(name: str, seed: int):
    if name == "RF":
        return RandomForestClassifier(n_estimators=100, min_samples_leaf=2, n_jobs=-1, random_state=seed)
    if name == "LightGBM":
        return LGBMClassifier(n_estimators=300, learning_rate=0.1, num_leaves=63, n_jobs=6,
                              random_state=seed, deterministic=True, force_row_wise=True, verbose=-1)
    if name == "MLP":
        # flow features span many orders of magnitude, so log-scale before standardising
        mlp = MLPClassifier(hidden_layer_sizes=(64, 32), batch_size=1024, max_iter=30,
                            early_stopping=True, n_iter_no_change=3, random_state=seed)
        return make_pipeline(FunctionTransformer(signed_log), StandardScaler(), mlp)
    raise ValueError(name)


def evaluate(model, df: pd.DataFrame, features: list[str]) -> tuple[dict, list[dict]]:
    proba = model.predict_proba(df[features].to_numpy())[:, 1]
    pred = proba >= 0.5
    y = df["attack"].to_numpy()
    metrics = {
        "macro_f1": f1_score(y, pred, average="macro"),
        "attack_recall": pred[y == 1].mean(),
        "benign_fpr": pred[y == 0].mean(),
        "auroc": roc_auc_score(y, proba),
        "n_test": len(y),
    }
    families = []
    for fam in SHARED_FAMILIES:
        mask = (df["family"] == fam).to_numpy()
        if mask.any():
            families.append({"family": fam, "recall": pred[mask].mean(), "n": int(mask.sum())})
    return metrics, families


def train_and_test(name, seed, train, tests, features, log):
    start = time.time()
    model = make_model(name, seed).fit(train[features].to_numpy(), train["attack"].to_numpy())
    fit_s = time.time() - start
    for exp, test in tests.items():
        metrics, families = evaluate(model, test, features)
        log["runs"].append({"experiment": exp, "model": name, "seed": seed, "n_train": len(train),
                            "fit_seconds": round(fit_s, 1), **metrics})
        log["families"] += [{"experiment": exp, "model": name, "seed": seed, **f} for f in families]
        print(f"  {exp:28s} {name:9s} seed {seed}  F1 {metrics['macro_f1']:.4f}  "
              f"recall {metrics['attack_recall']:.4f}  FPR {metrics['benign_fpr']:.4f}  ({fit_s:.0f}s fit)")
    return model


def summarise(log: dict, out: str):
    runs = pd.DataFrame(log["runs"])
    runs.to_csv(f"{out}/runs.csv", index=False)
    order = {e: i for i, e in enumerate([EXP_A, EXP_B, EXP_C, EXP_REF])}
    metrics = ["macro_f1", "attack_recall", "benign_fpr", "auroc"]
    main = runs.groupby(["experiment", "model"])[metrics].agg(["mean", "std"])
    main.columns = [f"{m}_{s}" for m, s in main.columns]
    main = main.reset_index().sort_values(["experiment", "model"], key=lambda c: c.map(order) if c.name == "experiment" else c)
    main.round(4).to_csv(f"{out}/main_table.csv", index=False)

    fam = pd.DataFrame(log["families"])
    fam = fam.groupby(["experiment", "model", "family"]).agg(recall_mean=("recall", "mean"),
                                                             recall_std=("recall", "std"), n=("n", "first"))
    fam.reset_index().round(4).to_csv(f"{out}/per_family_recall.csv", index=False)
    return main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="small subsample and one seed, for a smoke test")
    args = parser.parse_args()

    df17 = pd.read_parquet(DATA_2017)
    df18 = pd.read_parquet(DATA_2018)
    seeds, out, strat = SEEDS, RESULTS, "label"
    if args.quick:
        df17 = df17.sample(QUICK_ROWS, random_state=0)
        df18 = df18.sample(QUICK_ROWS, random_state=0)
        # rare labels can have a single row in a small subsample, so stratify on the binary label
        seeds, out, strat = SEEDS[:1], QUICK_RESULTS, "attack"
    features = [c for c in df17.columns if c not in LABEL_COLS
                and not (df17[c].nunique() == 1 and df18[c].nunique() == 1)]
    print(f"2017 rows {len(df17):,}, 2018 sample rows {len(df18):,}, features {len(features)}")
    os.makedirs(out, exist_ok=True)
    log = {"runs": [], "families": []}
    gains = []

    for seed in seeds:
        train, test = train_test_split(df17, test_size=TEST_FRAC, stratify=df17[strat], random_state=seed)
        for name in MODELS:
            model = train_and_test(name, seed, train, {EXP_A: test, EXP_B: df18}, features, log)
            if name == "LightGBM":
                gains.append(model.booster_.feature_importance("gain"))
        summarise(log, out)

    for seed in seeds:
        train, test = train_test_split(df18, test_size=TEST_FRAC, stratify=df18[strat], random_state=seed)
        for name in MODELS:
            train_and_test(name, seed, df18, {EXP_C: df17}, features, log)
            train_and_test(name, seed, train, {EXP_REF: test}, features, log)
        summarise(log, out)

    # gain of the 2017-trained LightGBM models, averaged over seeds; used by 03_feature_shift.py
    importance = pd.DataFrame({"feature": features, "gain": np.mean(gains, axis=0)})
    importance.sort_values("gain", ascending=False).to_csv(f"{out}/lgbm_importance.csv", index=False)
    print(summarise(log, out).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
