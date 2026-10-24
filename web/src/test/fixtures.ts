import type { ItemDetail, ItemRow, Overview, QueueRow, Release, ReviewSummary, Source, Spectrogram, Takedown } from "../shared/api/types";

export const overview: Overview = {
  files: 100,
  audio_hours: 0.272,
  kept_hours: 0.036,
  losses: [
    { reason: "licence", files: 8, hours: 0 },
    { reason: "duplicate", files: 5, hours: 0.04 },
    { reason: "not_speech", files: 47, hours: 0.08 },
    { reason: "synthetic_suspected", files: 12, hours: 0.026 },
    { reason: "segments:noise", files: 0, hours: 0.002 },
  ],
  audio_urls: { done: 100, "skipped:robots": 2 },
  not_fetched: { robots: 2, tdm: 4, blocked_domain: 1 },
  requests: 194,
  held: 12,
  jobs: { "analyse:done": 100 },
  latest_release: { name: "v1", created_at: "2026-10-24T17:00:00Z", stats: { segments: 29, hours: 0.036, speakers: 1, by_split: { train: 0.036 }, by_source: {}, by_licence: {}, by_tier: {}, by_text_source: {}, speakers_by_split: { train: 1 } } },
  audit: { ok: true, entries: 3 },
  cost: { audio_hours: 0.272, kept_hours: 0.036, cpu_seconds: 60, usd: 0.002, usd_per_kept_hour: 0.068, realtime_factor: 0.077, vcpus_for_1000_hours_per_day: 3.2 },
};

export const sources: Source[] = [
  { name: "audiobooks", kind: "librivox", seed: "http://audiobooks.example/api", items: 3, audio_hours: 0.05, kept_hours: 0.03, yield: 0.6, cpu_seconds: 22, usd: 0.0006, usd_per_kept_hour: 0.02, decisions: { kept: 2, "rejected:protected": 1 }, discovery: { source: "probe:audiobooks", sampled_files: 3, kept: 2, held: 0, rejected_by_reason: { protected: 1 }, not_fetched: {}, verdict: "ingest: 2 of 3 sampled files usable" } },
  { name: "voices", kind: "html_index", seed: "http://voices.example/", items: 12, audio_hours: 0, kept_hours: 0, yield: 0, cpu_seconds: 0, usd: 0, usd_per_kept_hour: null, decisions: { "rejected:synthetic": 12 }, discovery: null },
];

export const items: ItemRow[] = [
  { id: 7, url: "http://audiobooks.example/download/ch1.mp3", source: "audiobooks", state: "kept", reason: null, licence: "LicenseRef-PublicDomain", title: "Chapter 1", seconds: 55.1, bandwidth_hz: 11779, snr_db: 35.6, kept_seconds: 51 },
  { id: 9, url: "http://podcasts.example/media/aind-000.mp3", source: "podcasts", state: "held", reason: "synthetic_suspected", licence: "CC-BY-4.0", title: "AI news 1", seconds: 7.7, bandwidth_hz: 7730, snr_db: 34.7, kept_seconds: 7.6 },
];

export const detail: ItemDetail = {
  item: { ...items[1]!, licence_evidence: "podcast:license on the channel", attribution: "ai-news-daily", synthetic_declared: false, detail: { tier: "wide", tags: { speech: 0.46, music: 0, synthesizer: 0.82 } }, sha256: "ab".repeat(32) },
  analysis: { seconds: 7.7, bandwidth_hz: 7730, snr_db: 34.7, native_rate: 44100, codec: "mp3", speech_ratio: 0.99 },
  segments: [
    { id: 31, idx: 0, start_s: 0, end_s: 3.5, text: "In the only sense with which we are concerned,", asr: "in the only sense with which we are concerned", cer: 0.0, snr_db: 35, clipped_ratio: 0, tier: "wide", speaker: null, state: "kept", reason: null },
    { id: 32, idx: 1, start_s: 3.7, end_s: 7.6, text: "differs from most", asr: "differs from most", cer: null, snr_db: 12, clipped_ratio: 0, tier: "wide", speaker: null, state: "rejected", reason: "noise" },
  ],
  reviews: [],
  audio_available: true,
};

export const spectrogram: Spectrogram = { seconds: 7.7, bands: [60, 120], frames: [[0.1, 0.9], [0.5, 0.2]], peaks: [0.2, 0.4] };

export const queue: QueueRow[] = [
  { id: 9, url: "http://podcasts.example/media/aind-000.mp3", state: "held", reason: "synthetic_suspected", detail: {} },
  { id: 10, url: "http://podcasts.example/media/aind-001.mp3", state: "held", reason: "synthetic_suspected", detail: {} },
];

export const summary: ReviewSummary[] = [{ decision: "noise", n: 4, agree: 3, agree_interval: [0.3, 0.95] }];

export const releases: Release[] = [
  { name: "v1", created_at: "2026-10-24T17:00:00Z", manifest_sha256: "cd".repeat(32), parent: null, stats: { segments: 29, hours: 0.036, speakers: 1, by_split: { train: 0.036 }, by_source: { audiobooks: 0.03 }, by_licence: { "CC-BY-4.0": 0.006 }, by_tier: { full: 0.036 }, by_text_source: { published: 0.03 }, speakers_by_split: { train: 1 } } },
];

export const takedowns: Takedown[] = [];
