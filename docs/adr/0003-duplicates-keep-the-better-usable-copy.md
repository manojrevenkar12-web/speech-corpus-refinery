# 3. Duplicates: keep the better copy, but only once it is known to be usable

## Decision

Every analysed file is fingerprinted with landmark hashes (Wang 2003) at 8 kHz:
- in one index lookup, it is searched at its own speed and at ±10% in 0.5% steps;
- against our protected evaluation recordings, which reject it;
- against taken-down recordings, which reject it;
- against every earlier copy.

When copies match, the better one is kept: the higher bandwidth tier, then SNR in 5 dB steps,
then bitrate (POLICY.md). A copy we may not use does not count.

The better copy only *records* the worse copies it would replace. They are demoted when it is
kept, or when a reviewer clears it. If it is rejected for another reason, any copy already
rejected as its duplicate goes back to the queue, to be judged on its own.

## Why

- **Tiers, not raw hertz.** Broadband noise (rain) widens a noisy copy's measured bandwidth past
  a clean one's. Held-out set1 found this.
- **Demote late.** Demoting at match time lost both copies whenever the better-looking copy
  failed later. Held-out set3 found this with a clipped lossless transfer: it outranked a clean
  mp3 on bitrate, demoted it, then was rejected for clipping. Workers run in parallel, so it can
  happen in either order. Hence both rules: demote only on keep, and re-queue on failure
  (tests/test_db.py).
- **Speed by rescaling, not resampling.** Stretching the peaks, rather than decoding the file
  40 more times, keeps the speed search at a few seconds of CPU per file.
