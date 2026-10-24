# set4: notes

Written blind, from WRITING_SETS.md, POLICY.md and MATERIALS.md only, after set3's changes. The
brief asked for a spread across all the policy's rules, and for duplicate groups whose copies
differ in more than one way. Run once: **50 of 55 files got the right decision**, and 0 requests
broke a rights rule (`reports/heldout/set4/first_run.json`, never rewritten). That first run is
the most recent blind measurement of the refinery.

Its failures were then studied, and one change was made, so set4 is now a regression set. The
next blind set (set5) should be written from heldout/WRITING_SETS.md by someone who has seen
neither the code nor these notes.

## What the first run found

| Miss | Cause | Change |
|---|---|---|
| A full 12 s recording rejected as the duplicate of a 6 s quote from it | The quote's SNR was slightly higher; ranking did not consider how much of the recording each copy holds | Coverage first: a copy with under 80% of the other's speech never replaces it (POLICY.md, ADR 0003) |
| The 6 s quote kept | Same cause. The writer expected `duplicate`, and the policy now says so | Same change |
| A music bed 24 dB under the speech kept | Every bed 24 dB or more under the voice has been missed in all four worlds | None: documented (docs/MEASUREMENTS.md) |
| An undeclared TTS outro kept | The synthesizer tag did not fire | None: documented (ADR 0004) |
| A clean studio recording held as possibly synthetic | The tag fires on clean read speech | None: held, not lost |

The writer's judgement calls the refinery agrees with:
- an unusable copy (clipped, music bed, wrong licence) gets its own reason, not `duplicate`;
- a file containing any protected clip is rejected whole;
- CC BY 2.0 is not usable;
- a file's own licence beats its site's;
- audio linked only from a meta-reserved page is never fetched.

## After the change (latest.json)

{{SET4_AFTER}}
