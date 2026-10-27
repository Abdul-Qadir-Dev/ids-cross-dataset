# Notes

## 2026-10-27 machine and sizing

- Laptop: i7-10750H (6 cores / 12 threads), 19.8 GB RAM, but only 4.5 GB free
  with my usual stuff open (8 GB of commit headroom). D: has 63 GB free.
- 2018 processed CSVs are 6.9 GB on disk and about 16 M rows. Loaded whole as
  float64 they would need well over 10 GB, so that is out.
- What I chose: read every CSV in 500k-row chunks, clean each chunk, write it to
  parquet as float32 under data/interim/, then dedup globally using a 64-bit
  hash per row (16 M hashes is about 130 MB). The 2018 sample is 1.2 M rows,
  which as float32 with 76 features is about 0.4 GB. Training sets stay under
  about 2 M rows so RF, LightGBM and the MLP fit in the free RAM.
- Downloads: 2018 is public on S3 but came in at 0.1 to 0.5 MB/s from here,
  which would have taken hours. The Hugging Face mirror c01dsnap/CIC-IDS2018
  has the same 10 files with byte-identical sizes to the S3 listing and was
  several times faster; I checked every file against the SHA-256 that HF
  publishes. 2017 MachineLearningCSV.zip from UNB redirects to a sign-up page,
  so I took it from bencorn/CICIDS2017 on HF; the 8 extracted CSVs match the
  sizes in a second mirror (c01dsnap/CIC-IDS2017) to the byte.

## 2026-10-27 preparation

Row counts per cleaning step (also in results/prep_counts.csv):

| step | CIC-IDS2017 | CSE-CIC-IDS2018 |
|---|---|---|
| raw rows | 2,830,743 | 16,233,002 |
| drop repeated header rows | 2,830,743 | 16,232,943 |
| inf to NaN, drop NaN rows | 2,827,876 | 16,137,183 |
| drop exact duplicates | 2,233,164 | 10,851,047 |
| stratified 2018 sample | - | 1,199,999 |

- Order of steps: strip column names, rename 2018 columns to the 2017 names,
  drop the 59 repeated header rows (2018 only), keep the 76 shared flow features
  plus Label, inf to NaN, drop NaN, dedup. I select columns before the NaN step
  so a row isn't dropped for a NaN in a column I throw away anyway.
- Dedup is on the 76 features plus label, after dropping identifiers and the
  destination port, across all files of a dataset. That is stricter than
  deduping the raw rows, on purpose: the model only sees these columns, and
  identical vectors on both sides of a random split inflate experiment A.
- Surprise 1: without the destination port, 2017 PortScan collapses from
  158,930 rows to 1,956. Most scan probes are the same one or two packet flow
  and only differed by port. Port scan isn't in 2018, so it only matters for A.
- Surprise 2: in 2018, FTP-BruteForce goes from 193,360 rows to 53 and
  DoS SlowHTTPTest from 139,890 to 55. Those flows are almost all identical,
  which fits the reports that these two attacks mostly failed and produced
  near-empty connections. So 2018 "brute force" is essentially SSH only.
- 2017 web attack labels contain U+FFFD where the en dash was; I replace any
  non-ASCII run in a label with "-".
- Families: DoS, DDoS, brute force (FTP/SSH-Patator vs FTP/SSH-BruteForce),
  web attack (2017 brute force/XSS/SQLi vs 2018 Brute Force -Web/-XSS/SQL
  Injection), bot, infiltration. Port scan and Heartbleed exist only in 2017.
  These six are the shared families for per-family recall.
- 2018 sample: labels with fewer than 20k cleaned rows are kept whole (7
  labels: Brute Force -Web, Brute Force -XSS, SQL Injection, LOIC-UDP,
  SlowHTTPTest, Slowloris, FTP-BruteForce); every other label is sampled at
  10.96% with seed 42. Benign is 1,043,518 rows and attacks are 156,481 (13%).
  Side effect: inside the DoS family, Slowloris is now a third of the rows
  instead of about 5%, so DoS recall on the sample leans on Slowloris.
- Features constant in both datasets (8 of them: Bwd PSH/URG Flags and the
  six bulk-rate columns) are dropped in 02, leaving 68.
- Features are stored as float32. The dedup hash is computed on the float64
  values before the cast.
