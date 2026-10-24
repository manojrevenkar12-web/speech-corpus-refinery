# Working on this repository

Fast feedback:
- `pytest -q -m "not slow"`: about 45 s; needs PostgreSQL at `SCR_TEST_DATABASE_URL` and
  `scr fetch` once.
- `pytest -q -m slow`: the whole pipeline on the dev world, about 7 minutes.
- `cd web && npm test`.
- Lint: `ruff check src tests scripts`, `ruff format --check src tests scripts`, `mypy`.

Invariants (each has a test or a CI check; keep it that way):
- **Rights before bytes.** Blocked domains, takedowns, robots.txt and TDMRep are checked before
  a request is made; licence and AI declarations before audio is decoded.
  `tests/test_crawl.py` checks this against the test server's own request log.
- **Decision code never sees the answers.** Only `scr.world`, `scr.evaluation`, `scr.heldout`,
  `scr.pipeline` and `scr.cli` may know about truth files (`tests/test_isolation.py`).
- **Thresholds live in `config/`**, never in code. Prices are in `config/pricing.yaml`, and the
  Terraform worker size is tested against them (`tests/test_infra.py`).
- **A decision is one transaction.** Jobs are leased; a late write from a lost lease is fenced
  out. A worse duplicate is demoted only when the better copy is kept.
- **Releases are immutable.** The audit table is append-only and hash-chained.
- **Held-out sets.** Never change decision code to pass `heldout/<set>` before its first run
  is recorded. `reports/heldout/<set>/first_run.json` is never edited
  (`scripts/check_first_runs.py`). If you study a set's failures, write `regression` to its
  STATUS, and have someone who has not seen the code write a new set from
  `heldout/WRITING_SETS.md`.
- **Test data.** Hosts end in `.example`. Content is ordinary and neutral, with nothing involving
  minors. No credentials are committed.
