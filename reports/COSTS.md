# What usable audio costs

Measured CPU per stage, priced as Cloud Run jobs (https://cloud.google.com/run/pricing ; https://cloud.google.com/storage/pricing), plus crawl time and raw storage for a month.

- Audio analysed: 0.268 h; kept: 0.0359 h; CPU: 71.1 s (0.0737 CPU seconds per audio second)
- Cost: $0.0023 in total, $0.065 per kept hour
- At this rate, 1,000 hours of audio a day needs about 3.1 vCPUs running continuously

| Source | Files | Audio h | Kept h | Yield | CPU s | $ per kept hour |
|---|---:|---:|---:|---:|---:|---:|
| archive | 60 | 0.1634 | 0.0 | 0% | 22.8 | nothing kept |
| audiobooks | 3 | 0.0496 | 0.0297 | 60% | 25.1 | 0.02 |
| flaky | 5 | 0.0056 | 0.0 | 0% | 0.5 | nothing kept |
| pirate | 0 | 0.0 | 0.0 | 0% | 0 | nothing kept |
| podcasts | 17 | 0.0426 | 0.0062 | 15% | 22.0 | 0.09 |
| private | 1 | 0.0018 | 0.0 | 0% | 0.3 | nothing kept |
| reserved | 2 | 0.0051 | 0.0 | 0% | 0.4 | nothing kept |
| voices | 12 | 0.0 | 0.0 | 0% | 0.0 | nothing kept |

CPU by stage (seconds): asr 27.05, fingerprint 15.05, language 8.29, speaker 7.49, vad 6.16, tags 4.44, bandwidth 1.98, decode 0.66, policy 0.0
