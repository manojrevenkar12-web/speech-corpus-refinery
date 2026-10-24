/** Every decision reason, in words a reviewer understands, and its family (which sets its colour). */
export type Family = "kept" | "rights" | "licence" | "provenance" | "content" | "quality" | "fetch";

export const REASONS: Record<string, { label: string; family: Family }> = {
  kept: { label: "Kept", family: "kept" },
  robots: { label: "robots.txt disallows", family: "rights" },
  tdm: { label: "TDM rights reserved", family: "rights" },
  blocked_domain: { label: "Blocked domain", family: "rights" },
  takedown: { label: "Taken down", family: "rights" },
  licence: { label: "Licence not usable", family: "licence" },
  synthetic: { label: "Declared synthetic", family: "provenance" },
  synthetic_suspected: { label: "Possibly synthetic, held", family: "provenance" },
  protected: { label: "Our evaluation recording", family: "provenance" },
  duplicate: { label: "Duplicate of a better copy", family: "provenance" },
  not_speech: { label: "Not speech", family: "content" },
  too_short: { label: "Too short", family: "content" },
  language: { label: "Other language", family: "content" },
  bandwidth: { label: "Not enough bandwidth", family: "quality" },
  music: { label: "Music under speech", family: "quality" },
  noise: { label: "Too noisy", family: "quality" },
  clipping: { label: "Clipped", family: "quality" },
  misaligned: { label: "Speech does not match the text", family: "quality" },
  no_text: { label: "No transcript", family: "quality" },
  corrupt: { label: "Not decodable audio", family: "fetch" },
  fetch: { label: "Could not download", family: "fetch" },
};

export function reasonOf(key: string | null | undefined): { label: string; family: Family } {
  if (!key) return REASONS.kept as { label: string; family: Family };
  const bare = key.startsWith("segments:") ? key.slice("segments:".length) : key;
  const r = REASONS[bare] ?? { label: bare.replace(/_/g, " "), family: "quality" as Family };
  return key.startsWith("segments:") ? { ...r, label: `${r.label} (segments)` } : r;
}
