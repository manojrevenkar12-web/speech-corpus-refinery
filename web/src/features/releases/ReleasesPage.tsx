import { useReleases } from "../../shared/api/queries";
import type { Release } from "../../shared/api/types";
import { duration } from "../../shared/lib/format";
import { Mono, Stat } from "../../shared/ui/marks";
import { EmptyState, QueryView } from "../../shared/ui/states";
import styles from "./ReleasesPage.module.css";

function Breakdown({ title, data }: { title: string; data: Record<string, number> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className={styles.breakdown}>
      <h3 className={styles.h3}>{title}</h3>
      <ul>
        {Object.entries(data).map(([k, v]) => (
          <li key={k}>
            <span className={styles.key}>{k}</span>
            <span className={styles.track} aria-hidden>
              <span style={{ inlineSize: `${(v / total) * 100}%` }} />
            </span>
            <span className={styles.val}>{duration(v)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReleaseCard({ r }: { r: Release }) {
  const s = r.stats;
  return (
    <article className={styles.card}>
      <header className={styles.cardHead}>
        <h2 className={styles.name}>{r.name}</h2>
        <p className={styles.muted}>
          {new Date(r.created_at).toLocaleString()}
          {r.parent ? `, after ${r.parent}` : ""}
        </p>
        <Mono title="SHA-256 of manifest.parquet">{r.manifest_sha256}</Mono>
      </header>
      <div className={styles.stats}>
        <Stat value={duration(s.hours)} label={`${s.segments} segments`} tone="kept" />
        <Stat value={s.speakers} label="speakers, clustered from voice embeddings" />
      </div>
      <p className={styles.muted}>
        Splits are speaker-disjoint:{" "}
        {Object.entries(s.speakers_by_split)
          .map(([k, v]) => `${k} has ${v} speaker${v === 1 ? "" : "s"}`)
          .join(", ")}
        .
      </p>
      <div className={styles.grid}>
        <Breakdown title="By split" data={s.by_split} />
        <Breakdown title="By bandwidth tier" data={s.by_tier} />
        <Breakdown title="By licence" data={s.by_licence} />
        <Breakdown title="By transcript source" data={s.by_text_source} />
      </div>
    </article>
  );
}

export function ReleasesPage() {
  const q = useReleases();
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.h1}>Releases</h1>
        <p className={styles.muted}>
          Immutable snapshots of the kept segments, each with a manifest, a dataset card, attribution and the EU AI Act summary of training content.
        </p>
      </header>
      <QueryView query={q} what="releases" lines={6} isEmpty={(r) => r.length === 0} empty={<EmptyState title="No release yet">Run `scr release v1` once the work queue is empty.</EmptyState>}>
        {(rs) => (
          <div className={styles.list}>
            {rs.map((r) => (
              <ReleaseCard key={r.name} r={r} />
            ))}
          </div>
        )}
      </QueryView>
    </main>
  );
}
