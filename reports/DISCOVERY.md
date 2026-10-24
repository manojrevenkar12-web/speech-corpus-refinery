# Source discovery

Each source scored on a sample of up to 4 audio files, processed exactly as a full ingest would process them.

| Source | Sampled | Kept | Held | Not fetched | Main rejections | Verdict |
|---|---:|---:|---:|---|---|---|
| audiobooks | 3 | 2 | 0 | none | protected 1 | ingest: 2 of 3 sampled files usable, about $0.02 per usable hour |
| archive | 4 | 0 | 1 | none | duplicate 2, bandwidth 1, synthetic_suspected 1 | review first: most of the sample is held as possibly synthetic |
| podcasts | 4 | 1 | 0 | none | music 1, duplicate 1, clipping 1 | ingest: 1 of 4 sampled files usable, about $0.03 per usable hour |
| voices | 4 | 0 | 0 | none | synthetic 4 | skip: nothing usable in the sample (mostly synthetic) |
| reserved | 2 | 0 | 0 | tdm 4 | not_speech 2 | skip: nothing usable in the sample (mostly not_speech) |
| private | 1 | 0 | 0 | robots 2 | not_speech 1 | skip: nothing usable in the sample (mostly not_speech) |
| pirate | 0 | 0 | 0 | blocked_domain 1 | none | skip: the site opts out (blocked_domain) |
| flaky | 4 | 0 | 0 | none | not_speech 4 | skip: nothing usable in the sample (mostly not_speech) |
