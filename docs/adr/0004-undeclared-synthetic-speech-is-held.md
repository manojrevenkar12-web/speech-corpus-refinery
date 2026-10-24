# 4. Speech that only sounds synthetic is held for a person, not rejected

## Decision

Audio its source declares AI-generated (IPTC `trainedAlgorithmicMedia` in schema.org) is
rejected before decoding.

Audio that is undeclared but scores at least 0.65 on CED's AudioSet "Speech synthesizer" class
is *held*. It is not released until a reviewer keeps or rejects it in the console. The console
shows the spectrogram, the segments and the measurements, and takes keyboard decisions.

## Why

- The tag is not a synthetic-speech detector. It also fires on clean studio speech: the clean
  Valentini recording scores about 0.74. Rejecting on it would silently throw away the
  cleanest real recordings.
- It also misses voices it was not trained near: the Piper `amy` voice scores low, so two
  undeclared amy files in set1 were kept.
- So it is a triage signal. The measured trade-off, with the files behind it, is in
  docs/MEASUREMENTS.md.

## What would change it

A dedicated anti-spoofing model, evaluated on the held-out sets' TTS and real recordings,
could replace the tag. Until then, every held file is reviewed, and the Wilson interval on
reviewers' agreement shows how far the tag can be trusted.
