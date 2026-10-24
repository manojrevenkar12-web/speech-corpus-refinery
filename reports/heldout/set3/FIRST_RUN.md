# Held-out set set3: first run

48 of 59 files got the right decision (keep or not); 46 also got the right kind of reason. 16 kept, 15 should be.

| Expected | Files | Right decision | Right reason |
|---|---:|---:|---:|
| keep | 15 | 10 | 10 |
| reject:bandwidth | 2 | 1 | 1 |
| reject:blocked_domain | 2 | 2 | 2 |
| reject:clipping | 4 | 4 | 4 |
| reject:duplicate | 6 | 4 | 3 |
| reject:licence | 5 | 5 | 5 |
| reject:music | 2 | 1 | 1 |
| reject:noise | 3 | 2 | 1 |
| reject:not_speech | 3 | 3 | 3 |
| reject:protected | 5 | 5 | 5 |
| reject:robots | 3 | 3 | 3 |
| reject:synthetic | 4 | 3 | 3 |
| reject:tdm | 5 | 5 | 5 |

## Rights, from the server's own request log

- Requests: 108; user agents seen: `ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)`
- Requests to a blocked domain: 0
- Requests to paths robots.txt disallows: 0
- Requests to paths reserved in tdmrep.json: 0
- Files reserved by a TDM header or meta tag that were stored: 0

## Synthetic speech

- Declared (IPTC trainedAlgorithmicMedia in schema.org): 1 of 1 rejected
- Undeclared: 1 of 2 held for review, 0 rejected for another reason, 1 kept
- Real speech held by mistake: 0

## Transcripts of kept segments, against the true text

| Text source | Clips | Mean CER | Worst CER |
|---|---:|---:|---:|
| published | 2 | 0.0798 | 0.0991 |
| asr | 7 | 0.0387 | 0.1806 |

Kept segments cover 98% of the true speech in kept files.

## Wrong decisions

| File | Expected | Got |
|---|---|---|
| http://branchline-voices.example/lines/steam-gala-preview.mp3 | reject:music | kept |
| http://branchline-voices.example/lines/carriage-reading.mp3 | reject:duplicate | kept |
| http://branchline-voices.example/lines/clock-room.flac | keep | rejected:music |
| http://kitchen-almanac.example/episodes/ep111-airfield-picnic.mp3 | reject:noise | kept |
| http://tramline-notes.example/audio/ep3-rye-bread-repeat.flac | reject:duplicate | kept |
| http://readaloud-circle.example/audio/f-insects.ogg | keep | rejected:not_speech |
| http://readaloud-circle.example/audio/f-clean-of-clipped.mp3 | keep | rejected:duplicate |
| http://townhall-library-tapes.example/download/e-quiet-30/e-quiet-30.flac | keep | rejected:licence |
| http://townhall-library-tapes.example/download/e-val-clean/e-val-clean.ogg | keep | rejected:duplicate |
| http://townhall-library-tapes.example/download/e-synth/e-synth.mp3 | reject:synthetic | kept |
| http://townhall-library-tapes.example/download/e-lowpass-6600/e-lowpass-6600.flac | reject:bandwidth | kept |

## Right decision, other reason

| File | Expected | Got |
|---|---|---|
| http://townhall-library-tapes.example/download/e-louder-copy/e-louder-copy.mp3 | reject:duplicate | rejected:not_speech |
| http://townhall-library-tapes.example/download/e-val-noisy/e-val-noisy.mp3 | reject:noise | rejected:duplicate |
