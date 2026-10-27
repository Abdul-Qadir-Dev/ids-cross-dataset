import glob
import os

import numpy as np
import pandas as pd

RAW_2017 = "data/raw/cic2017"
RAW_2018 = "data/raw/cic2018"
INTERIM = "data/interim"
OUT = "data/processed"
COUNTS_CSV = "results/prep_counts.csv"
SAMPLE_COUNTS_CSV = "results/sample_2018_counts.csv"

SEED = 42
CHUNK_ROWS = 500_000
SAMPLE_2018_ROWS = 1_200_000
# labels with fewer cleaned rows than this are kept whole in the 2018 sample
RARE_LABEL_ROWS = 20_000

# 2018 spelling -> 2017 spelling. Names not listed are already identical.
RENAME_2018 = {
    "Dst Port": "Destination Port",
    "Tot Fwd Pkts": "Total Fwd Packets",
    "Tot Bwd Pkts": "Total Backward Packets",
    "TotLen Fwd Pkts": "Total Length of Fwd Packets",
    "TotLen Bwd Pkts": "Total Length of Bwd Packets",
    "Fwd Pkt Len Max": "Fwd Packet Length Max",
    "Fwd Pkt Len Min": "Fwd Packet Length Min",
    "Fwd Pkt Len Mean": "Fwd Packet Length Mean",
    "Fwd Pkt Len Std": "Fwd Packet Length Std",
    "Bwd Pkt Len Max": "Bwd Packet Length Max",
    "Bwd Pkt Len Min": "Bwd Packet Length Min",
    "Bwd Pkt Len Mean": "Bwd Packet Length Mean",
    "Bwd Pkt Len Std": "Bwd Packet Length Std",
    "Flow Byts/s": "Flow Bytes/s",
    "Flow Pkts/s": "Flow Packets/s",
    "Fwd IAT Tot": "Fwd IAT Total",
    "Bwd IAT Tot": "Bwd IAT Total",
    "Fwd Header Len": "Fwd Header Length",
    "Bwd Header Len": "Bwd Header Length",
    "Fwd Pkts/s": "Fwd Packets/s",
    "Bwd Pkts/s": "Bwd Packets/s",
    "Pkt Len Min": "Min Packet Length",
    "Pkt Len Max": "Max Packet Length",
    "Pkt Len Mean": "Packet Length Mean",
    "Pkt Len Std": "Packet Length Std",
    "Pkt Len Var": "Packet Length Variance",
    "FIN Flag Cnt": "FIN Flag Count",
    "SYN Flag Cnt": "SYN Flag Count",
    "RST Flag Cnt": "RST Flag Count",
    "PSH Flag Cnt": "PSH Flag Count",
    "ACK Flag Cnt": "ACK Flag Count",
    "URG Flag Cnt": "URG Flag Count",
    "ECE Flag Cnt": "ECE Flag Count",
    "Pkt Size Avg": "Average Packet Size",
    "Fwd Seg Size Avg": "Avg Fwd Segment Size",
    "Bwd Seg Size Avg": "Avg Bwd Segment Size",
    "Fwd Byts/b Avg": "Fwd Avg Bytes/Bulk",
    "Fwd Pkts/b Avg": "Fwd Avg Packets/Bulk",
    "Fwd Blk Rate Avg": "Fwd Avg Bulk Rate",
    "Bwd Byts/b Avg": "Bwd Avg Bytes/Bulk",
    "Bwd Pkts/b Avg": "Bwd Avg Packets/Bulk",
    "Bwd Blk Rate Avg": "Bwd Avg Bulk Rate",
    "Subflow Fwd Pkts": "Subflow Fwd Packets",
    "Subflow Fwd Byts": "Subflow Fwd Bytes",
    "Subflow Bwd Pkts": "Subflow Bwd Packets",
    "Subflow Bwd Byts": "Subflow Bwd Bytes",
    "Init Fwd Win Byts": "Init_Win_bytes_forward",
    "Init Bwd Win Byts": "Init_Win_bytes_backward",
    "Fwd Act Data Pkts": "act_data_pkt_fwd",
    "Fwd Seg Size Min": "min_seg_size_forward",
}

# Identifiers and things that are not flow statistics. Destination port is
# dropped because it nearly names the attack (e.g. 21/22 for the Patator runs).
# "Fwd Header Length.1" is a duplicated column in the 2017 CSVs.
DROP = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Source IP", "Source Port",
        "Destination IP", "Timestamp", "Destination Port", "Protocol",
        "Fwd Header Length.1"]


def family(label: str) -> str:
    s = label.lower()
    if s == "benign":
        return "Benign"
    if "ddos" in s:
        return "DDoS"
    if "dos" in s:
        return "DoS"
    # check web before brute force: 2018 calls web brute force "Brute Force -Web"
    if "web" in s or "xss" in s or "sql" in s:
        return "Web attack"
    if "patator" in s or "brute" in s:
        return "Brute force"
    if s == "bot":
        return "Bot"
    if s.startswith("infilt"):
        return "Infiltration"
    if s == "portscan":
        return "Port scan"
    if s == "heartbleed":
        return "Heartbleed"
    raise ValueError(f"unmapped label: {label}")


def shared_features() -> list[str]:
    cols_2017 = pd.read_csv(glob.glob(f"{RAW_2017}/*.csv")[0], nrows=0).columns.str.strip()
    cols_2018 = pd.read_csv(glob.glob(f"{RAW_2018}/*.csv")[0], nrows=0).columns.str.strip()
    cols_2018 = [RENAME_2018.get(c, c) for c in cols_2018]
    shared = [c for c in cols_2017 if c in cols_2018 and c not in DROP and c != "Label"]
    print(f"2017 cols {len(cols_2017)}, 2018 cols {len(cols_2018)}, shared features {len(shared)}")
    return shared


def clean_chunk(df: pd.DataFrame, features: list[str], counts: dict) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    df = df.rename(columns=RENAME_2018)
    counts["raw"] += len(df)

    df = df[df["Label"].astype(str).str.strip() != "Label"]
    counts["after_drop_header_rows"] += len(df)

    df = df[features + ["Label"]].copy()
    df[features] = df[features].apply(pd.to_numeric, errors="coerce")
    df[features] = df[features].replace([np.inf, -np.inf], np.nan)
    df = df.dropna()
    counts["after_drop_nan_inf"] += len(df)

    # the 2017 web attack labels contain U+FFFD where an en dash used to be
    df["Label"] = df["Label"].str.strip().str.replace(r"[^\x00-\x7f]+", "-", regex=True)
    # hash on float64 values before the float32 cast, so dedup is exact
    df["row_hash"] = pd.util.hash_pandas_object(df[features + ["Label"]], index=False).values
    df[features] = df[features].astype("float32")
    return df


def clean_dataset(name: str, files: list[str], features: list[str]) -> tuple[list[str], dict]:
    counts = {"raw": 0, "after_drop_header_rows": 0, "after_drop_nan_inf": 0}
    os.makedirs(f"{INTERIM}/{name}", exist_ok=True)
    parts = []
    for path in files:
        print(f"  reading {os.path.basename(path)}")
        reader = pd.read_csv(path, chunksize=CHUNK_ROWS, low_memory=False)
        for i, chunk in enumerate(reader):
            df = clean_chunk(chunk, features, counts)
            part = f"{INTERIM}/{name}/{os.path.basename(path)[:-4]}_{i:03d}.parquet"
            df.to_parquet(part, index=False)
            parts.append(part)
    return parts, counts


def dedup_mask(parts: list[str]) -> np.ndarray:
    hashes = pd.concat([pd.read_parquet(p, columns=["row_hash"])["row_hash"] for p in parts], ignore_index=True)
    return ~hashes.duplicated(keep="first").to_numpy()


def load_parts(parts: list[str], keep: np.ndarray) -> pd.DataFrame:
    frames, start = [], 0
    for p in parts:
        df = pd.read_parquet(p)
        frames.append(df[keep[start:start + len(df)]])
        start += len(df)
    return pd.concat(frames, ignore_index=True).drop(columns="row_hash")


def add_labels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"Label": "label"})
    df["family"] = df["label"].map({l: family(l) for l in df["label"].unique()})
    df["attack"] = (df["family"] != "Benign").astype("int8")
    return df


def sample_2018(labels: pd.Series) -> np.ndarray:
    counts = labels.value_counts()
    rare = counts[counts < RARE_LABEL_ROWS]
    frac = (SAMPLE_2018_ROWS - rare.sum()) / (counts.sum() - rare.sum())
    print(f"  2018 sample: keeping {len(rare)} rare labels whole, fraction {frac:.4f} for the rest")
    rng = np.random.default_rng(SEED)
    picked = []
    for label, idx in labels.groupby(labels, observed=True).groups.items():
        if label in rare.index:
            picked.append(np.asarray(idx))
        else:
            picked.append(rng.choice(np.asarray(idx), size=round(frac * len(idx)), replace=False))
    return np.sort(np.concatenate(picked))


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs("results", exist_ok=True)
    features = shared_features()
    rows = []

    print("cleaning CIC-IDS2017")
    parts, counts = clean_dataset("cic2017", sorted(glob.glob(f"{RAW_2017}/*.csv")), features)
    keep = dedup_mask(parts)
    counts["after_dedup"] = int(keep.sum())
    rows.append({"dataset": "CIC-IDS2017", **counts})
    df17 = add_labels(load_parts(parts, keep))
    df17.to_parquet(f"{OUT}/cic2017.parquet", index=False)
    print(df17["label"].value_counts().to_string())
    del df17

    print("cleaning CSE-CIC-IDS2018")
    parts, counts = clean_dataset("cic2018", sorted(glob.glob(f"{RAW_2018}/*.csv")), features)
    keep = dedup_mask(parts)
    counts["after_dedup"] = int(keep.sum())
    rows.append({"dataset": "CSE-CIC-IDS2018", **counts})

    labels = pd.concat([pd.read_parquet(p, columns=["Label"])["Label"] for p in parts], ignore_index=True)
    labels = labels[keep].reset_index(drop=True).astype("category")
    picked = sample_2018(labels)
    sampled = np.zeros(len(labels), dtype=bool)
    sampled[picked] = True
    full_keep = keep.copy()
    full_keep[np.flatnonzero(keep)[~sampled]] = False

    df18 = add_labels(load_parts(parts, full_keep))
    df18.to_parquet(f"{OUT}/cic2018_sample.parquet", index=False)
    rows.append({"dataset": "CSE-CIC-IDS2018 sample", "after_dedup": len(df18)})

    sample_counts = pd.DataFrame({"cleaned": labels.value_counts(), "sampled": df18["label"].value_counts()})
    sample_counts["family"] = [family(l) for l in sample_counts.index]
    sample_counts.rename_axis("label").to_csv(SAMPLE_COUNTS_CSV)
    print(sample_counts.to_string())

    counts = pd.DataFrame(rows).convert_dtypes()
    counts.to_csv(COUNTS_CSV, index=False)
    print(counts.to_string(index=False))


if __name__ == "__main__":
    main()
