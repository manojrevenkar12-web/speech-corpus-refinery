import { Link } from "react-router-dom";

import { useOverview } from "../../shared/api/queries";
import { count, duration, usd } from "../../shared/lib/format";
import { reasonOf } from "../../shared/lib/reasons";
import { Stat } from "../../shared/ui/marks";
import { EmptyState, QueryView } from "../../shared/ui/states";
import { HoursTape } from "./HoursTape";
import styles from "./OverviewPage.module.css";

export function OverviewPage() {
  const q = useOverview();
  return (
    <main className={styles.page}>
      <QueryView
        query={q}
        what="the corpus overview"
        lines={8}
        isEmpty={(o) => o.files === 0}
        empty={<EmptyState title="Nothing crawled yet">Seed a source and run `scr crawl`, then `scr work`. Files appear here as they are decided.</EmptyState>}
      >
        {(o) => (
          <>
            <header className={styles.hero}>
              <h1 className={styles.headline}>
                <span className={styles.big}>{duration(o.kept_hours)}</span> usable speech from {duration(o.audio_hours)} analysed
              </h1>
              <p className={styles.sub}>
                {count(o.files, "file")} decided, {usd(o.cost.usd_per_kept_hour)} per usable hour at Cloud Run prices.
                {o.held > 0 && (
                  <>
                    {" "}
                    <Link to="/review">{o.held} held for review</Link>.
                  </>
                )}
              </p>
            </header>
            <section className={styles.section} aria-label="Where the hours went">
              <HoursTape total={o.audio_hours} kept={o.kept_hours} losses={o.losses} />
            </section>
            <div className={styles.grid}>
              <section className={styles.card}>
                <h2 className={styles.h2}>Never fetched</h2>
                <p className={styles.lede}>Opt-outs and blocks, honoured before any request for the file.</p>
                {Object.keys(o.not_fetched).length ? (
                  <div className={styles.stats}>
                    {Object.entries(o.not_fetched).map(([k, v]) => (
                      <Stat key={k} value={v} label={reasonOf(k).label} tone="rights" />
                    ))}
                  </div>
                ) : (
                  <p className={styles.muted}>Every discovered URL was allowed.</p>
                )}
              </section>
              <section className={styles.card}>
                <h2 className={styles.h2}>Work and cost</h2>
                <div className={styles.stats}>
                  <Stat value={`${o.cost.realtime_factor ?? 0}`} label="CPU seconds per audio second" />
                  <Stat value={o.cost.vcpus_for_1000_hours_per_day ?? "n/a"} label="vCPUs for 1,000 hours a day" />
                  <Stat value={o.requests} label="HTTP requests made" />
                </div>
              </section>
              <section className={styles.card}>
                <h2 className={styles.h2}>Latest release</h2>
                {o.latest_release ? (
                  <div className={styles.stats}>
                    <Stat value={o.latest_release.name} label={new Date(o.latest_release.created_at).toLocaleString()} tone="kept" />
                    <Stat value={duration(o.latest_release.stats.hours)} label={`${o.latest_release.stats.segments} segments`} />
                    <Stat value={o.latest_release.stats.speakers} label="speakers" />
                  </div>
                ) : (
                  <p className={styles.muted}>No release yet. Run `scr release v1` when the queue is empty.</p>
                )}
              </section>
              <section className={styles.card}>
                <h2 className={styles.h2}>Audit trail</h2>
                <p className={o.audit.ok ? styles.ok : styles.bad}>
                  {o.audit.ok ? `Intact: ${o.audit.entries} entries, every hash links to the one before.` : "Broken: an entry was changed. See the runbook."}
                </p>
              </section>
            </div>
          </>
        )}
      </QueryView>
    </main>
  );
}
