# set1: notes

Written blind (from WRITING_SETS.md, POLICY.md and MATERIALS.md only) and run once:
**43 of 50 files got the right decision** (`reports/heldout/set1/first_run.json`, not rewritten).
Its failures were then studied, so set1 is now a regression set (`STATUS: regression`) and set2
was written by someone else, blind, to measure the system after the changes below.

## What the first run found

| Miss | Cause | Change |
|---|---|---|
| Item licence in an RSS feed ignored (1 wrong, 2 wrong reasons) | Test-harness bug: the renderer wrote only the channel `<podcast:license>` | Renderer writes item-level licences |
| Synthetic-speech counts in the report | Test-harness bug: "declared" was guessed from the host name | Truth records `declared` |
| Wrong copy of a duplicate kept (2 wrong) | Rain under the re-upload is broadband, so its measured bandwidth was wider than the clean original's | Copies compared by bandwidth *tier*, then SNR, then bitrate (POLICY.md updated) |
| A copy played 10% faster kept | Landmark fingerprints do not survive a speed change, and speed was not searched | Peaks rescaled for ±10% in 0.5% steps, both directions, in one index lookup |
| Music bed 30 dB under speech kept | The tagger cannot hear it under speech | Pauses are also checked for music. This file's pauses are too short (0.45 s), so it is still missed |
| Second TTS voice (amy), undeclared, kept | The AudioSet "Speech synthesizer" tag does not fire on it | None possible without a synthetic-speech detector: documented |
| Content cut at 6.5 kHz kept against a 7 kHz minimum | Within the bandwidth estimator's resolution | None: documented as about ±0.5 kHz |

The policy did not settle three of the writer's judgement calls. The system agrees with all three:

- an unusable (NC) better copy does not displace a usable one;
- a sped-up copy is a duplicate;
- a page's meta reservation covers the audio on that page.

## After the changes (latest.json)

46 of 50 on the latest rerun (45 on some earlier reruns). Still wrong:
- the 30 dB music bed;
- one undeclared amy file;
- the 6.5 kHz file;
- one clean studio recording held as possibly synthetic.

The second undeclared amy file sits on the 25 dB noise line, so its decision has flipped
between reruns: rejected for noise (right decision, wrong reason) or kept. docs/MEASUREMENTS.md
gives the estimator's error near the limit.
