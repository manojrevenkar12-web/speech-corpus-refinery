# 1. PostgreSQL is the frontier, the job queue and the record

## Decision

One PostgreSQL database holds:
- the crawl frontier (URLs, with per-host leases and next-allowed times);
- the analysis queue (jobs leased with `FOR UPDATE SKIP LOCKED`, extended by a heartbeat, retried
  with back-off, and dead after three attempts);
- every decision and release;
- the audit chain.

There is no separate broker.

## Why

- **One transaction per decision.** An analysis writes its result, its segments, its costs and
  its fingerprint together, so a job that runs twice leaves one result
  (`tests/test_pipeline.py::test_analysing_a_file_twice_leaves_one_result`). A worker that dies
  loses its lease, and its late write is fenced out by `lease_owner`
  (`tests/test_db.py::test_a_crashed_workers_job_is_picked_up_after_its_lease_expires`).
- **Politeness is shared state.** "One request at a time per host, a second apart" has to hold
  across every crawler process. A host row with a lease and a next-allowed time does that without
  another moving part.
- **The scale is files, not samples.** A job is a whole file: minutes of audio and seconds of
  CPU. At 1,000 hours of audio a day that is under 100,000 jobs a day, about one a second. That
  is far inside what a leased-row queue handles.

## When to change it

Move the analysis queue to Pub/Sub when leasing shows up in Cloud SQL's query insights, or when
workers outgrow the connection budget. That is about 50 tasks at `max_connections = 100`. The
decision tables stay in PostgreSQL either way.
