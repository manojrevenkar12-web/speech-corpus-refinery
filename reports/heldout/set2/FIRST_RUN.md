# Held-out set set2: first run

50 of 56 files got the right decision (keep or not); 48 also got the right kind of reason. 17 kept, 15 should be.

| Expected | Files | Right decision | Right reason |
|---|---:|---:|---:|
| keep | 15 | 13 | 13 |
| reject:bandwidth | 3 | 3 | 3 |
| reject:blocked_domain | 3 | 3 | 3 |
| reject:clipping | 2 | 0 | 0 |
| reject:duplicate | 6 | 6 | 6 |
| reject:licence | 6 | 6 | 6 |
| reject:music | 2 | 0 | 0 |
| reject:noise | 3 | 3 | 2 |
| reject:not_speech | 4 | 4 | 4 |
| reject:protected | 3 | 3 | 3 |
| reject:robots | 2 | 2 | 2 |
| reject:synthetic | 4 | 4 | 3 |
| reject:tdm | 3 | 3 | 3 |

## Rights, from the server's own request log

- Requests: 101; user agents seen: `ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)`
- Requests to a blocked domain: 0
- Requests to paths robots.txt disallows: 0
- Requests to paths reserved in tdmrep.json: 0
- Files reserved by a TDM header or meta tag that were stored: 0

## Synthetic speech

- Declared (IPTC trainedAlgorithmicMedia in schema.org): 1 of 1 rejected
- Undeclared: 1 of 2 held for review, 1 rejected for another reason, 0 kept
- Real speech held by mistake: 1

## Transcripts of kept segments, against the true text

| Text source | Clips | Mean CER | Worst CER |
|---|---:|---:|---:|
| published | 4 | 0.0259 | 0.0604 |
| asr | 7 | 0.0888 | 0.2653 |

Kept segments cover 97% of the true speech in kept files.

## Wrong decisions

| File | Expected | Got |
|---|---|---|
| http://typeset-radio.example/episodes/ep02.mp3 | reject:music | kept |
| http://typeset-radio.example/episodes/ep03.mp3 | reject:music | kept |
| http://stacks-archive.example/download/sa-clipped/sa-clipped.mp3 | reject:clipping | kept |
| http://morningbriefing.example/audio/2026-10-01.flac | keep | held:synthetic_suspected |
| http://mediahub-studio.example/media/hot-mic.mp3 | reject:clipping | kept |
| http://campus-radio.example/shows/reading-hour.mp3 | keep | rejected:noise |

## Right decision, other reason

| File | Expected | Got |
|---|---|---|
| http://publicreads.example/audio/pr-tts-reader.mp3 | reject:synthetic | rejected:misaligned |
| http://morningbriefing.example/audio/2026-10-01-street.flac | reject:noise | rejected:duplicate |
