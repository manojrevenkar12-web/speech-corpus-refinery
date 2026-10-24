# What usable audio costs

Measured CPU per stage, priced as Cloud Run jobs (https://cloud.google.com/run/pricing ; https://cloud.google.com/storage/pricing), plus crawl time and raw storage for a month.

- Audio analysed: 0.268 h; kept: 0.0359 h; CPU: 71.9 s (0.0745 CPU seconds per audio second)
- Cost: $0.0024 in total, $0.0655 per kept hour
- At this rate, 1,000 hours of audio a day needs about 3.1 vCPUs running continuously

| Source | Files | Audio h | Kept h | Yield | CPU s | $ per kept hour |
|---|---:|---:|---:|---:|---:|---:|
| archive | 60 | 0.1634 | 0.0 | 0% | 22.7 | nothing kept |
| audiobooks | 3 | 0.0496 | 0.0297 | 60% | 25.9 | 0.02 |
| flaky | 5 | 0.0056 | 0.0 | 0% | 0.6 | nothing kept |
| pirate | 0 | 0.0 | 0.0 | 0% | 0 | nothing kept |
| podcasts | 17 | 0.0426 | 0.0062 | 15% | 22.1 | 0.09 |
| private | 1 | 0.0018 | 0.0 | 0% | 0.1 | nothing kept |
| reserved | 2 | 0.0051 | 0.0 | 0% | 0.4 | nothing kept |
| voices | 12 | 0.0 | 0.0 | 0% | 0.0 | nothing kept |

CPU by stage (seconds): asr 26.57, fingerprint 16.09, language 8.0, speaker 7.51, vad 6.4, tags 4.69, bandwidth 1.96, decode 0.65, policy 0.0
