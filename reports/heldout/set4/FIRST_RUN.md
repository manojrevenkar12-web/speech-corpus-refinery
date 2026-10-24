# Held-out set set4: first run

50 of 55 files got the right decision (keep or not); 48 also got the right kind of reason. 14 kept, 13 should be.

| Expected | Files | Right decision | Right reason |
|---|---:|---:|---:|
| keep | 13 | 11 | 11 |
| reject:bandwidth | 4 | 4 | 4 |
| reject:blocked_domain | 2 | 2 | 2 |
| reject:clipping | 2 | 2 | 2 |
| reject:duplicate | 5 | 4 | 4 |
| reject:licence | 6 | 6 | 6 |
| reject:music | 3 | 2 | 2 |
| reject:noise | 2 | 2 | 1 |
| reject:not_speech | 5 | 5 | 5 |
| reject:protected | 4 | 4 | 4 |
| reject:robots | 2 | 2 | 2 |
| reject:synthetic | 4 | 3 | 2 |
| reject:tdm | 3 | 3 | 3 |

## Rights, from the server's own request log

- Requests: 108; user agents seen: `ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)`
- Requests to a blocked domain: 0
- Requests to paths robots.txt disallows: 0
- Requests to paths reserved in tdmrep.json: 0
- Files reserved by a TDM header or meta tag that were stored: 0

## Synthetic speech

- Declared (IPTC trainedAlgorithmicMedia in schema.org): 2 of 2 rejected
- Undeclared: 0 of 2 held for review, 1 rejected for another reason, 1 kept
- Real speech held by mistake: 1

## Transcripts of kept segments, against the true text

| Text source | Clips | Mean CER | Worst CER |
|---|---:|---:|---:|
| published | 1 | 0.0548 | 0.0548 |
| asr | 13 | 0.1406 | 0.6242 |

Kept segments cover 91% of the true speech in kept files.

## Wrong decisions

| File | Expected | Got |
|---|---|---|
| http://readaloud-library.example/audio/ral-ugly-ones.mp3 | keep | rejected:duplicate |
| http://riverside-radio.example/shows/read-sentences.wav | keep | held:synthetic_suspected |
| http://reading-room-podcast.example/media/public/ep03-outro.mp3 | reject:synthetic | kept |
| http://reading-room-podcast.example/media/public/ep05-quote.mp3 | reject:duplicate | kept |
| http://greenway-walks.example/guides/mill-intro.mp3 | reject:music | kept |

## Right decision, other reason

| File | Expected | Got |
|---|---|---|
| http://community-sound-archive.example/download/csa-voice-memo/csa-voice-memo.mp3 | reject:synthetic | rejected:noise |
| http://riverside-radio.example/shows/street-sentences.wav | reject:noise | rejected:duplicate |
