# Evaluation on the test world

109 of 110 files got the right decision (keep or not); 103 also got the right kind of reason. 3 kept, 4 should be.

| Expected | Files | Right decision | Right reason |
|---|---:|---:|---:|
| keep | 4 | 3 | 3 |
| reject:bandwidth | 10 | 10 | 6 |
| reject:blocked_domain | 3 | 3 | 3 |
| reject:clipping | 1 | 1 | 1 |
| reject:corrupt | 1 | 1 | 1 |
| reject:duplicate | 2 | 2 | 2 |
| reject:fetch | 1 | 1 | 1 |
| reject:licence | 8 | 8 | 8 |
| reject:music | 1 | 1 | 1 |
| reject:noise | 1 | 1 | 0 |
| reject:not_speech | 47 | 47 | 46 |
| reject:protected | 1 | 1 | 1 |
| reject:robots | 2 | 2 | 2 |
| reject:synthetic | 24 | 24 | 24 |
| reject:tdm | 4 | 4 | 4 |

## Rights, from the server's own request log

- Requests: 336; user agents seen: `ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)`
- Requests to a blocked domain: 0
- Requests to paths robots.txt disallows: 0
- Requests to paths reserved in tdmrep.json: 0
- Files reserved by a TDM header or meta tag that were stored: 0

## Synthetic speech

- Declared (IPTC trainedAlgorithmicMedia in schema.org): 12 of 12 rejected
- Undeclared: 12 of 12 held for review, 0 rejected for another reason, 0 kept
- Real speech held by mistake: 1

## Transcripts of kept segments, against the true text

| Text source | Clips | Mean CER | Worst CER |
|---|---:|---:|---:|
| published | 16 | 0.0159 | 0.0991 |
| asr | 3 | 0.1371 | 0.2555 |

Kept segments cover 97% of the true speech in kept files.

## Wrong decisions

| File | Expected | Got |
|---|---|---|
| http://archive.example/download/p287-read-speech/p287_clean.flac | keep | held:synthetic_suspected |

## Right decision, other reason

| File | Expected | Got |
|---|---|---|
| http://archive.example/download/p287-read-speech-cafe/p287_noisy.flac | reject:noise | rejected:duplicate |
| http://archive.example/download/voice-messages-lucas/lucas.wav | reject:bandwidth | rejected:not_speech |
| http://archive.example/download/field-1-30039-A-26-laughing/1-30039-A-26.flac | reject:not_speech | rejected:noise |
| http://reserved.example/open/take4.flac | reject:bandwidth | rejected:not_speech |
| http://reserved.example/open/take5.flac | reject:bandwidth | rejected:not_speech |
| http://private.example/recordings/public/r0.flac | reject:bandwidth | rejected:not_speech |
