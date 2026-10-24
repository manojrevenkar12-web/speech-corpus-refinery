import type { ItemDetail, ItemRow, Overview, QueueRow, Release, ReviewSummary, Source, Spectrogram, Takedown, TakedownImpact } from "./types";

const KEY = "scr.apiKey";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export function storedKey(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function storeKey(key: string): void {
  try {
    if (key) sessionStorage.setItem(KEY, key);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the key lasts for this page */
  }
}

export function authHeaders(): Record<string, string> {
  const k = storedKey();
  return k ? { Authorization: `Bearer ${k}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [k, v] of Object.entries(authHeaders())) headers.set(k, v);
  if (init?.body) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "The API did not answer. Check that `scr serve` is running.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

const q = (o: Record<string, string | number | undefined>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");

export const api = {
  overview: () => request<Overview>("/api/overview"),
  sources: () => request<Source[]>("/api/sources"),
  items: (p: { state?: string; reason?: string; source?: string; limit?: number; offset?: number }) =>
    request<{ total: number; items: ItemRow[] }>(`/api/items?${q(p)}`),
  item: (id: number) => request<ItemDetail>(`/api/items/${id}`),
  spectrogram: (id: number, width: number) => request<Spectrogram>(`/api/items/${id}/spectrogram?width=${width}`),
  queue: (kind: "held" | "kept" | "rejected", n = 20) => request<QueueRow[]>(`/api/review/queue?kind=${kind}&n=${n}`),
  review: (body: { item_id?: number; segment_id?: number; verdict: "agree" | "disagree"; note?: string }) =>
    request<{ id: number }>("/api/reviews", { method: "POST", body: JSON.stringify(body) }),
  reviewSummary: () => request<ReviewSummary[]>("/api/reviews/summary"),
  resolve: (id: number, decision: "keep" | "reject", note = "") =>
    request<{ item_id: number; state: string }>(`/api/items/${id}/resolve`, { method: "POST", body: JSON.stringify({ decision, note }) }),
  releases: () => request<Release[]>("/api/releases"),
  takedowns: () => request<Takedown[]>("/api/takedowns"),
  previewTakedown: (body: { kind: string; value: string; reason: string }) =>
    request<TakedownImpact>("/api/takedowns/preview", { method: "POST", body: JSON.stringify(body) }),
  executeTakedown: (body: { kind: string; value: string; reason: string }) =>
    request<{ id: number } & TakedownImpact>("/api/takedowns", { method: "POST", body: JSON.stringify(body) }),
};

/** Audio comes as a blob so the API key travels in a header, not in a URL. */
export async function audioUrl(id: number, start?: number, end?: number): Promise<string> {
  const res = await fetch(`/api/items/${id}/audio?${q({ start, end })}`, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, res.status === 410 ? "The audio was deleted after a takedown." : `HTTP ${res.status}`);
  return URL.createObjectURL(await res.blob());
}
