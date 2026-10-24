# Held-out set set1: first run

43 of 50 files got the right decision (keep or not); 39 also got the right kind of reason. 20 kept, 17 should be.

| Expected | Files | Right decision | Right reason |
|---|---:|---:|---:|
| keep | 17 | 15 | 15 |
| reject:bandwidth | 3 | 2 | 1 |
| reject:blocked_domain | 3 | 3 | 3 |
| reject:clipping | 1 | 1 | 1 |
| reject:duplicate | 3 | 1 | 1 |
| reject:licence | 2 | 2 | 2 |
| reject:music | 2 | 1 | 1 |
| reject:noise | 1 | 1 | 1 |
| reject:not_speech | 4 | 4 | 3 |
| reject:protected | 5 | 5 | 5 |
| reject:robots | 2 | 2 | 2 |
| reject:synthetic | 4 | 3 | 1 |
| reject:tdm | 3 | 3 | 3 |

## Rights, from the server's own request log

- Requests: 95; user agents seen: `ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)`
- Requests to a blocked domain: 0
- Requests to paths robots.txt disallows: 0
- Requests to paths reserved in tdmrep.json: 0
- Files reserved by a TDM header or meta tag that were stored: 0

## Synthetic speech

- Declared (IPTC trainedAlgorithmicMedia in schema.org): 0 of 0 rejected
- Undeclared: 0 of 4 held for review, 1 kept
- Real speech held by mistake: 0

## Transcripts of kept segments, against the true text

| Text source | Clips | Mean CER | Worst CER |
|---|---:|---:|---:|
| published | 2 | 0.013 | 0.026 |
| asr | 12 | 0.1184 | 0.3882 |

Kept segments cover 94% of the true speech in kept files.

## Wrong decisions

| File | Expected | Got |
|---|---|---|
| http://lectures.example/talks/printing-origins.flac | keep | rejected:duplicate |
| http://newsdesk.example/episodes/104.mp3 | reject:music | kept |
| http://newsdesk.example/episodes/105.mp3 | reject:synthetic | kept |
| http://newsdesk.example/episodes/rebroadcast-printing.mp3 | reject:duplicate | kept |
| http://talkback.example/shows/reading.wav | keep | rejected:licence |
| http://campus-radio.example/readings/ugly-letters.flac | reject:bandwidth | kept |
| http://stacks.example/download/stacks-reupload-fast/stacks-reupload-fast.ogg | reject:duplicate | kept |

## Right decision, other reason

| File | Expected | Got |
|---|---|---|
| http://talkback.example/shows/caller-digits.wav | reject:bandwidth | rejected:licence |
| http://talkback.example/shows/rain-interlude.wav | reject:not_speech | rejected:licence |
| http://stacks.example/download/stacks-river-lecture/stacks-river-lecture.mp3 | reject:synthetic | rejected:noise |
| http://audiobooks.example/audio/lv-tts-chapter.mp3 | reject:synthetic | rejected:misaligned |
