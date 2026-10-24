# How far each probe can be trusted

Every decision the refinery makes rests on a measurement: bandwidth, SNR, clipping, tags,
fingerprints. This page records how far each one can be trusted. The numbers come from
scripts in `scripts/` (raw rows in `reports/measurements/`) or from the held-out worlds'
reports.

## Clipping: share of samples near full scale

`python scripts/measure_clipping.py`

**Setup.** Ten LJSpeech clips, peak-normalised. Each was clipped by 0, 3, 6, 9 and 12 dB of gain,
plus one quiet copy. Each was stored as flac, mp3 128k, mp3 64k and ogg 96k at 44.1 kHz, making
240 files. The truth is the share of samples clipped before encoding; a file counts as clipped
above the policy's 0.05%.

| Test, after the 16 kHz resample the pipeline analyses | Wrong | False alarms | Missed | Wrong but within 2× of the limit |
|---|---:|---:|---:|---:|
| Runs of 3 samples at ≥ 0.98 (before set2) | 76 | 0 | 76 | 20 |
| Share of samples ≥ 0.85 of full scale | 10 | 10 | 0 | 6 |
| Share ≥ 0.88 | 6 | 6 | 0 | 6 |
| **Share ≥ 0.90 (used)** | **4** | 4 | 0 | **4** |
| Share ≥ 0.92 | 4 | 2 | 2 | 4 |
| Share ≥ 0.95 | 9 | 1 | 8 | 9 |

**Why the old test failed.** Lossy coding and resampling turn a flat top into ripple, and the
ripple overshoots full scale. A +12 dB clipped mp3 decodes with peaks up to 1.24 and almost no
runs of identical samples. Set2's two clipped mp3s measured exactly 0.

**Why the new test works.** Clipping still piles samples up *near* full scale, and that survives
the ripple. All four remaining errors are files within a factor of two of the limit.

**Limits.**
- Peak-normalised clean speech has under 0.03% of its samples at ≥ 0.9, against the 0.05% limit.
  So a file mastered hard to 0 dBFS with a brick-wall limiter would also count as clipped. In
  effect the probe treats heavy limiting as clipping.
- On the blind worlds since the change: set3 4 of 4 clipped files rejected; set4 2 of 2.

## SNR: speech frames over the quietest tenth

`python scripts/measure_snr.py`

**Setup.** 24 LJSpeech clips, excluding the protected ones. Each was mixed with rain, engine,
wind and vacuum noise from ESC-50 at 15, 20, 23, 25, 27, 30 and 35 dB, plus the clean clip,
and stored as mp3 128k: 696 files. The mix SNR is the clip's mean power over the noise's, as the
held-out worlds define it. Files mixed at exactly 25 dB are not judged, leaving 600 files.

**Which side of the 25 dB limit each estimator puts a file:**

| Estimator | Wrong |
|---|---:|
| **Pipeline: VAD speech frames over the quietest tenth of frames (used)** | **46 of 600** |
| Minimum statistics: noise floor per frequency band from its quiet moments (after Martin 2001) | 96 |
| WADA-SNR (Kim and Stern 2008), from the amplitude distribution, no pauses needed | 130 |

**Pipeline estimate minus mix SNR, in dB:**

| Mixed at | 15 | 20 | 23 | 25 | 27 | 30 | 35 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mean | +1.7 | +0.9 | +0.5 | +0.1 | −0.3 | −0.9 | −2.6 |
| Range | −2.9 to +6.1 | −4.3 to +5.3 | −5.2 to +5.0 | −5.9 to +4.8 | −6.8 to +4.6 | −8.7 to +4.2 | −12.7 to +3.1 |

**What this means.**
- Near the limit the estimate is unbiased on average, but a single file can be about 5 dB off.
  A file truly at 23 dB can pass, and one at 27 dB can fail.
- 31 of the 46 errors are in files with under 0.3 s of pause (275 of the 600). Without pauses,
  the quietest frames are speech, not noise. The two clean clips read below 25 dB are 1.9 s and
  2.6 s long with 0.02 s of pause: set2's "clean reading rejected for noise" exactly.
- Neither pause-free alternative helped, so the estimator stays. A short file without pauses
  is a known weak spot. Real sources (chapters, episodes) have pauses; very short clips are the
  case to watch.
- In the blind worlds the same error shows up in both directions:
  - helicopter noise mixed at 23.5 dB passed (set3);
  - a clean Valentini recording read lower than the same recording with rain added at 32 dB
    (set3);
  - an undeclared TTS file sits on the line, so its decision flipped between reruns (set1).

## Bandwidth: highest frequency within 50 dB of the peak (HiFiTTS-2)

The estimate comes from the mean power spectrum of the first 30 s at the file's native rate.
Across the held-out worlds, content cut at:
- **6.5–6.6 kHz** was read as reaching 7 kHz (set1, set3: kept, should be rejected);
- **9 kHz after a speed change** was read as 9.73 kHz (set3: `full` instead of `wide`);
- **6.0–6.3 kHz** was read correctly as too narrow (set2, set4).

Treat the estimate as **about ±0.7 kHz** near the 7 and 9.5 kHz lines. A low-pass filter's
transition band sits above the cut-off, and the 50 dB floor reaches into it.

## Synthetic speech: CED "Speech synthesizer" score ≥ 0.65 → held

- **Dev world:** the undeclared Piper `lessac` voice was held 12 of 12 times. One real clean
  studio recording (Valentini p287) also scores 0.74 and is held.
- **Blind worlds:**
  - set1: the undeclared Piper `amy` voice was not tagged (2 files kept), and a clean studio
    recording was held;
  - set2: 1 of 2 undeclared files held, and 1 real recording held;
  - set3: 1 of 2 undeclared files held;
  - set4: 0 of 2 undeclared files held (1 kept, 1 rejected for noise), and 1 real recording
    held.

It is a triage signal, not a detector. That is why it holds files for review rather than
rejecting them (ADR 0004). Declared AI-generated audio (IPTC `trainedAlgorithmicMedia`) is
rejected every time, before decoding.

## Music under speech

CED's music score over 10 s windows, plus a check of the pauses between speech regions.

Across the four blind worlds the line is sharp:

| Bed level under the speech | Files | Caught |
|---|---:|---:|
| 12 to 18 dB under | 4 | **4** |
| 24 to 36 dB under | 5 | **0** |

So the probe catches theme tunes and audible beds, and misses beds 24 dB or more under the
voice. A bed that quiet still teaches a TTS model to reproduce it. Catching those would need a
source-separation step, for example the stem model from music-model-gateway, run over the
pauses.

Clock ticks were once heard as music (set3). The pause check needs pauses of at least 0.15 s,
totalling at least 0.4 s.

## Fingerprints (landmark hashes at 8 kHz, with a ±10% speed search)

Every re-upload in the blind worlds was matched to its original. That covers re-encodes, gain
changes, added silence, added noise, excerpts (including every excerpt of a protected recording),
and copies 4–8% faster or slower. Where the wrong copy was kept, the cause was ranking, not
matching:
- SNR or bandwidth readings within their error (set3);
- before set4, a clean excerpt outranking the full recording. Coverage now comes first
  (ADR 0003).

`tests/test_units.py` asserts the matches on real speech: re-encode with offset, excerpt in ogg,
and ±7–8% speed through mp3. It also asserts that unrelated speech does not match.

## Cost

Measured CPU seconds per stage, priced at Cloud Run job rates (`config/pricing.yaml`):

- the dev world costs **$0.06–0.07 per usable hour** across reruns (measured CPU varies a little), with ASR the largest stage;
- 1,000 hours of audio a day needs about **3 vCPUs** running continuously.

This is measured on short files, where per-file overhead (model start-up, fingerprint lookup)
weighs more. Long audiobook chapters should cost less per hour. The per-source cost report
(`scr costs`) is the number to watch on real data.
