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
  which fits Liu and Patras (2022, NetSentry, arXiv 2202.09873), who say
  these two attacks were captured with only SYN and RST packets. So 2018
  "brute force" is essentially SSH only.
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

## 2026-10-28 first full run, and LightGBM diverging

- First full run took about two hours. The cross-dataset drop was large for
  every model: on B (train 2017, test 2018) macro F1 fell to 0.52 to 0.60 and
  attack recall to 6 to 23%, against 0.94 to 0.998 F1 on the 2017 split.
- LightGBM looked wrong on A: mean F1 0.94 with a 0.05 std across seeds, and
  AUROC 0.93 +/- 0.07, while RF and the MLP were at 0.996+ with tiny std. A
  boosted model scoring lower AUROC than RF on in-domain data is odd.
- Checked on the 2017 training split only (seed 1): training AUROC is 1.0 at
  50 and 100 rounds, then 0.995 at 200 and 0.836 at 300, with raw scores out
  to about +/-1e7. So boosting diverges on its own training data; this is not
  overfitting or shift. My guess at the cause: 2017 has rows with identical
  features and different labels (the dedup is on features plus label, so these
  survive). A confidently wrong row has gradient ~1 and hessian ~0, and the
  Newton step for its leaf blows up.
- Fix: max_delta_step=1.0, which caps each leaf's output. I chose it on
  training data only: with it, seeds 1 and 2 reach training AUROC 1.0 and raw
  scores stay within about +/-22. I did not try other values and did not look
  at any test numbers for it.
- I am aware this is a re-run after seeing results. The reason is a training
  failure visible without any test data, not a test number I didn't like. The
  first run is kept in results/first_run_lgbm_diverged_runs.csv. RF and MLP
  are deterministic with fixed seeds, so their numbers should repeat exactly
  in the second run; I'll check that.
- Not a dead end but worth noting: 2018 Infiltration gets ~4% recall even
  within 2018, for all three models, so as labelled it is barely separable
  from benign. Liu et al. (2022) report labelling errors in 2018; I only read
  the abstract, so I can't say whether they single out infiltration. 2017 Bot
  sits around 60% recall in-domain, in line with the labelling problems
  Engelen et al. (2021) describe for 2017.

## 2026-10-28 second run, with the LightGBM fix

- RF and MLP came out the same as in the first run: MLP identical, RF within
  5e-5 on every metric (probably the multithreaded averaging of tree votes
  flipping a few rows that sit right at 0.5). So the re-run only changed
  LightGBM, as intended.
- LightGBM now behaves: A goes from 0.94 +/- 0.05 to 0.9986 +/- 0.0001 macro
  F1. Its B number went down, not up: attack recall 3.9% instead of 23%. The
  diverged model had been pushing more of everything towards "attack" (its B
  false positive rate was 6% vs 0.05% now), so its earlier 23% was partly
  noise, not better transfer.
- The laptop slept overnight in the middle of this run. Two RF fits show 3,876 s
  and 25,129 s instead of the usual ~250 s. The fit_seconds column in
  results/runs.csv is wall-clock time, so ignore it for those two rows.
- What surprised me most: in B the false positive rate stays tiny (0.05 to
  0.9%). The 2017 models don't panic on 2018; they call nearly everything
  benign, attacks included. AUROC for RF and LightGBM is still 0.77 to 0.83,
  so some ranking survives, but the 0.5 threshold learned on 2017 lands in the
  wrong place. I did not pick a new threshold, because the only data to pick
  it on would be 2018 itself.
- Bot, brute force and web attack transfer at essentially zero in both
  directions. DoS is the only family that partly carries over (19 to 37%
  recall in B, 33 to 52% in C). DDoS doesn't, which I didn't expect: 2017 DDoS
  is LOIC, and 2018 has LOIC-HTTP too (63k of the 87k sampled DDoS rows). So
  the tool alone doesn't explain it; my guess is the different network setup
  (AWS in 2018), but I haven't checked.
- C (train 2018, test 2017) is a bit better than B for the tree models (macro
  F1 0.67 to 0.69, recall 26 to 31%), but the MLP is unstable there: false
  positive rate 12 to 31% depending on seed.
- Feature shift: 9 of the top 10 LightGBM features have a KS statistic of
  0.15 to 0.34 on benign traffic alone, so even "normal" looks different a year
  later. The clearest cases are the TCP window fields (Init_Win_bytes_forward
  median 60 vs 8192 for benign) and backward packet lengths. On attack traffic
  three features shift by KS 0.70 to 0.72, which is expected since the attack
  tools themselves changed between the two years.
