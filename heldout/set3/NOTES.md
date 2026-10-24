# set3: notes

Written blind, from WRITING_SETS.md, POLICY.md and MATERIALS.md only, after set2's changes.

The brief for this set asked the writer to cover, among the usual cases, the kinds of case
set2 had exposed:
- clipping in lossy formats;
- noise around 25 dB;
- quiet clean recordings.

It did not say what the refinery would do with them. Run once: **48 of 59 files got the right
decision**, and 0 requests broke a rights rule (`reports/heldout/set3/first_run.json`, never
rewritten). All four clipped files, in mp3, ogg and flac, were rejected. Its failures were then
studied, so set3 is now a regression set, and set4 was written blind to measure the result.

## What the first run found

| Miss | Cause | Change |
|---|---|---|
| A clean mp3 rejected as the duplicate of a clipped flac copy of the same recording | The flac outranked it on bitrate and demoted it at match time, then was itself rejected for clipping, so neither copy was kept | The better copy only records what it would replace; it demotes it once it is kept. A copy left rejected as the duplicate of a failed copy is re-queued (ADR 0003) |
| Both copies of the rye-bread recording kept | A copy demoted while it was still being analysed overwrote the demotion when it finished | `finish()` keeps a demotion that happened meanwhile |
| A file licensed `PDM-1.0` rejected as unlicensed | Not an SPDX or Creative Commons form of the Public Domain Mark. The writer flagged it as uncertain | None: unusual licence strings are not guessed at (ADR 0002) |

## After the changes (latest.json): still 48 of 59, with a different composition

The clipped/clean pair is now right. Exactly one rye-bread copy is kept, but not the one the
writer chose: a 9 kHz low-pass measures 9.73 kHz, so both copies are in the `full` tier and the
flac wins on bitrate. Measurement limits, not logic:

- **Valentini clean against the same recording with rain at 32 dB.** The "clean" recording has
  real room noise and measures 31.0 dB as a 64k ogg; the rain copy measures 33.6 dB. The
  estimator cannot separate them, so it keeps the rain copy.
- **Bandwidth within about ±0.7 kHz of a tier line** (6.6 kHz kept; 9 kHz read as 9.7 kHz).
- **Music.** A bed under speech was missed; clock ticks were heard as music.
- **Not speech.** Speech with insects under it was rejected as not speech.
- **Noise.** Helicopter noise mixed at 23.5 dB measured above 25 dB.
- **Synthetic speech.** One undeclared TTS file was not tagged as synthetic.
