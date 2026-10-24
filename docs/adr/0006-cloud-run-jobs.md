# 6. Cloud Run jobs for the batch work, Terraform for all of it

## Decision

One container image runs as four Cloud Run jobs and one service, all defined in
`infra/terraform`:
- `crawl`, nightly, on a schedule;
- `work`, hourly, as parallel tasks;
- `release`, run by hand;
- `setup`, run once per deploy;
- the API, which also serves the review console.

Raw audio and releases are in GCS, and the record is in Cloud SQL on a private IP.

## Why

- **The work is per file and CPU-bound.** Each file goes through ffmpeg decoding, ONNX models
  on CPU and fingerprinting. Tasks that lease from the PostgreSQL queue scale by raising
  `worker_tasks` and `worker_parallelism`. They need no cluster to run and no Beam pipeline to
  keep in step with the models.
- **The cost model is the bill.** Measured CPU seconds, priced at Cloud Run job rates
  (config/pricing.yaml), give dollars per *usable* hour per source. That is the number that
  decides whether a source is worth crawling. The Terraform worker size is tested against the
  pricing file, so the two cannot drift.
- **Crawler identity is infrastructure.** All crawler traffic leaves through Cloud NAT from
  one static address. That address is documented, so site owners can recognise us.

## Limits

- Cloud Run jobs cap a task at 24 hours, and a release over a very large corpus would be split
  by shard.
- At petabyte scale, decoding and fingerprinting would move closer to the data, for example to
  Dataflow over GCS notifications. The per-file job contract (`process.analyse`) is what would
  move.
