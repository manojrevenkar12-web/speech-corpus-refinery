# 5. Quality is measured on worlds written blind, and a first run is never rewritten

## Decision

Each held-out world is written by someone who has read only three files: the writing guide,
POLICY.md and MATERIALS.md. It is a small internet of `.example` sites, with an expected
outcome for every file.

- The refinery runs on it once. That first run (`reports/heldout/<set>/first_run.json`) is
  committed and never edited. `scripts/check_first_runs.py` fails CI if it, or the world, is
  edited later.
- Once anyone studies a set's failures to change the code, the set becomes a regression set
  (`STATUS: regression`), and a new blind set measures the result.

## Why

- A test written by the person who wrote the code tests what they thought of.
- The dev world (109 of 110) is designed alongside the code, so it shows how good the
  refinery *can* be. The blind first runs show how good it *is* on cases nobody tuned for:
  43/50, 50/56, 48/59, then set4.
