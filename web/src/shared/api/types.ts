/** Shapes of the refinery API (src/scr/api.py). */

export interface Loss {
  reason: string;
  files: number;
  hours: number;
}

export interface CostTotal {
  audio_hours: number;
  kept_hours: number;
  cpu_seconds: number;
  usd: number;
  usd_per_kept_hour: number | null;
  realtime_factor: number | null;
  vcpus_for_1000_hours_per_day?: number;
}

export interface Overview {
  files: number;
  audio_hours: number;
  kept_hours: number;
  losses: Loss[];
  audio_urls: Record<string, number>;
  not_fetched: Record<string, number>;
  requests: number;
  held: number;
  jobs: Record<string, number>;
  latest_release: { name: string; created_at: string; stats: ReleaseStats } | null;
  audit: { ok: boolean; entries: number };
  cost: CostTotal;
}

export interface Discovery {
  source: string;
  sampled_files: number;
  kept: number;
  held: number;
  rejected_by_reason: Record<string, number>;
  not_fetched: Record<string, number>;
  verdict: string;
}

export interface Source {
  name: string;
  kind: string | null;
  seed: string | null;
  items: number;
  audio_hours: number;
  kept_hours: number;
  yield: number;
  cpu_seconds: number;
  usd: number;
  usd_per_kept_hour: number | null;
  decisions: Record<string, number>;
  discovery: Discovery | null;
}

export interface ItemRow {
  id: number;
  url: string;
  source: string;
  state: "new" | "kept" | "held" | "rejected" | "withdrawn";
  reason: string | null;
  licence: string;
  title: string;
  seconds: number | null;
  bandwidth_hz: number | null;
  snr_db: number | null;
  kept_seconds: number | null;
}

export interface Segment {
  id: number;
  idx: number;
  start_s: number;
  end_s: number;
  text: string;
  asr: string;
  cer: number | null;
  snr_db: number;
  clipped_ratio: number;
  tier: string | null;
  speaker: string | null;
  state: "kept" | "rejected" | "withdrawn";
  reason: string | null;
}

export interface ItemDetail {
  item: ItemRow & {
    licence_evidence: string;
    attribution: string;
    synthetic_declared: boolean;
    detail: Record<string, unknown>;
    sha256: string | null;
  };
  analysis: (Record<string, unknown> & { seconds?: number; bandwidth_hz?: number; snr_db?: number; native_rate?: number; codec?: string }) | null;
  segments: Segment[];
  reviews: Array<{ reviewer: string; verdict: string; note: string; at: string; segment_id: number | null }>;
  audio_available: boolean;
}

export interface Spectrogram {
  seconds: number;
  bands: number[];
  frames: number[][];
  peaks: number[];
}

export interface QueueRow {
  id: number;
  url: string;
  state: string;
  reason: string | null;
  detail: Record<string, unknown>;
}

export interface ReviewSummary {
  decision: string;
  n: number;
  agree: number;
  agree_interval: [number, number] | null;
}

export interface ReleaseStats {
  segments: number;
  hours: number;
  speakers: number;
  by_split: Record<string, number>;
  by_source: Record<string, number>;
  by_licence: Record<string, number>;
  by_tier: Record<string, number>;
  by_text_source: Record<string, number>;
  speakers_by_split: Record<string, number>;
}

export interface Release {
  name: string;
  created_at: string;
  manifest_sha256: string;
  stats: ReleaseStats;
  parent: string | null;
}

export interface TakedownImpact {
  items: number;
  segments: number;
  kept_hours: number;
  releases: string[];
}

export interface Takedown {
  id: number;
  kind: string;
  value: string;
  reason: string;
  requested_by: string;
  requested_at: string;
  executed_at: string | null;
  affected: { items: number; segments: number; releases: string[]; blobs_deleted: number } | null;
}
