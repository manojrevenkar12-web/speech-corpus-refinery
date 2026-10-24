# What usable audio costs

Measured CPU per stage, priced as Cloud Run jobs (https://cloud.google.com/run/pricing ; https://cloud.google.com/storage/pricing), plus crawl time and raw storage for a month.

- Audio analysed: 0.272 h; kept: 0.0359 h; CPU: 59.8 s (0.061 CPU seconds per audio second)
- Cost: $0.0021 in total, $0.0583 per kept hour
- At this rate, 1,000 hours of audio a day needs about 2.5 vCPUs running continuously

| Source | Files | Audio h | Kept h | Yield | CPU s | $ per kept hour |
|---|---:|---:|---:|---:|---:|---:|
| archive | 60 | 0.1634 | 0.0 | 0% | 14.4 | nothing kept |
| audiobooks | 3 | 0.0496 | 0.0297 | 60% | 22.9 | 0.02 |
| flaky | 5 | 0.0056 | 0.0 | 0% | 0.3 | nothing kept |
| pirate | 0 | 0.0 | 0.0 | 0% | 0 | nothing kept |
| podcasts | 17 | 0.0466 | 0.0062 | 13% | 21.6 | 0.09 |
| private | 1 | 0.0018 | 0.0 | 0% | 0.2 | nothing kept |
| reserved | 2 | 0.0051 | 0.0 | 0% | 0.3 | nothing kept |
| voices | 12 | 0.0 | 0.0 | 0% | 0.0 | nothing kept |

CPU by stage (seconds): asr 28.23, language 8.26, speaker 7.92, vad 6.3, tags 4.45, fingerprint 1.99, bandwidth 1.94, decode 0.66, policy 0.0
