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
