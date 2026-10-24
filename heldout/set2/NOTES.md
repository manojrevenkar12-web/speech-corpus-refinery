# set2: notes

Written blind, from WRITING_SETS.md, POLICY.md and MATERIALS.md only, after set1's changes. Run
once: **50 of 56 files got the right decision**, and 0 requests broke a rights rule
(`reports/heldout/set2/first_run.json`, never rewritten). Its failures were then studied, so set2
is now a regression set, and set3 was written blind to measure the result.

## What the first run found

| Miss | Cause | Change |
|---|---|---|
| Two clipped mp3s (+9 and +12 dB) kept | The probe looked for runs of samples at ≥ 0.98. mp3 coding and the 16 kHz resample turn flat tops into ripple that overshoots full scale, so it measured exactly 0 | Clipping is now the share of samples at ≥ 0.9 of full scale. On 240 test files this went from 76 wrong to 4, all within a factor of two of the limit (docs/MEASUREMENTS.md, `scripts/measure_clipping.py`) |
| A clean 2.6 s reading rejected for noise (24.7 dB against 25) | The file has 0.02 s of pause, so the "quietest frames" the estimator calls noise are speech | None. WADA-SNR and a minimum-statistics noise floor were both measured and both did worse (docs/MEASUREMENTS.md). Documented as a limit of short files without pauses |
| Music beds 27 and 36 dB under the speech kept | Below what the tagger hears under speech, and the pauses are too short for the pause check | None: documented |
| A clean studio recording held as possibly synthetic | The "Speech synthesizer" tag fires on clean read speech | None: it is held, not rejected (ADR 0004) |

The policy did not settle six of the writer's judgement calls. The system's decision on each
agrees with the writer:
- CC BY 2.0 is not on the allow-list;
- a file's own CC0 overrides its site's NC-SA (that file, the 2.6 s reading above, then failed on noise);
- a declared AI file is rejected even when it is a real voice;
- under half speech is `not_speech`;
- JFK fails on bandwidth;
- a lowercase `scrbot` robots group applies to us.

## Wrong reason, right decision

- An undeclared TTS chapter with a published text was rejected as `misaligned`, because the
  speech did not match the book. The writer expected `synthetic`.
- A noisy re-upload was rejected as a `duplicate` of the clean copy. The writer expected `noise`.
  The policy says a copy we may not use does not count, but it does not say which reason wins.

## After the changes (latest.json)

52 of 56. Both clipped mp3s are rejected. Still wrong:
- the 27 and 36 dB music beds;
- the clean 2.6 s reading rejected for noise;
- the clean studio recording held for review.
