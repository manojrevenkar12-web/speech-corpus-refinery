/** Durations and money, written the way a data lead reads them. */
export function duration(hours: number): string {
  const s = hours * 3600;
  if (s < 60) return `${s.toFixed(0)} s`;
  if (s < 3600) return `${(s / 60).toFixed(1)} min`;
  return `${hours.toFixed(1)} h`;
}

export function seconds(s: number | null | undefined): string {
  if (s === null || s === undefined) return "";
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "nothing kept";
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
}

export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "" : `${Math.round(v * 100)}%`;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function fileOf(url: string): string {
  const parts = url.split("/");
  return parts[parts.length - 1] || url;
}
