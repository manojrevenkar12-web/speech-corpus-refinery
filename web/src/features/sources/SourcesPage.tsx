import { Link } from "react-router-dom";

import { useSources } from "../../shared/api/queries";
import type { Source } from "../../shared/api/types";
import { duration, pct, usd } from "../../shared/lib/format";
import { reasonOf } from "../../shared/lib/reasons";
import { Mono } from "../../shared/ui/marks";
import { EmptyState, QueryView } from "../../shared/ui/states";
import styles from "./SourcesPage.module.css";

/** Each source's decisions as one stacked bar of file counts, coloured by family. */
function Decisions({ s }: { s: Source }) {
  const total = Object.values(s.decisions).reduce((a, b) => a + b, 0) || 1;
  const parts = Object.entries(s.decisions).sort((a, b) => b[1] - a[1]);
  return (
    <div className={styles.bar} role="img" aria-label={parts.map(([k, v]) => `${v} ${reasonOf(k === "kept" ? null : k.split(":")[1] ?? k).label}`).join(", ")}>
      {parts.map(([k, v]) => {
        const [state, reason] = k.split(":");
        const fam = state === "kept" ? "kept" : state === "held" ? "held" : reasonOf(reason ?? state).family;
        return <span key={k} data-family={fam} style={{ flexGrow: v / total }} title={`${v} ${reasonOf(state === "kept" ? null : reason ?? state).label}`} />;
      })}
    </div>
  );
}

function verdictTone(v: string | undefined): string {
  if (!v) return "none";
  return v.startsWith("ingest") ? "kept" : v.startsWith("review") ? "held" : "rejected";
}

export function SourcesPage() {
  const q = useSources();
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.h1}>Sources</h1>
        <p className={styles.lede}>
          What each source gave, what it cost and what a sample said before ingesting it. A source whose files are mostly rejected costs more per usable hour even when
          each file is cheap.
        </p>
      </header>
      <QueryView query={q} what="sources" lines={8} isEmpty={(s) => s.length === 0} empty={<EmptyState title="No sources yet">Add one with `scr seed`, or score a candidate first with `scr discover`.</EmptyState>}>
        {(sources) => (
          <div className={styles.scroll}>
            <table className={styles.table}>
              <caption className="visually-hidden">Sources</caption>
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Sample verdict</th>
                  <th scope="col" className={styles.num}>
                    Usable
                  </th>
                  <th scope="col" className={styles.num}>
                    Yield
                  </th>
                  <th scope="col" className={styles.num}>
                    Per usable hour
                  </th>
                  <th scope="col">Decisions</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.name}>
                    <th scope="row">
                      <Link to={`/items?source=${encodeURIComponent(s.name)}`}>{s.name}</Link>
                      {s.seed && <Mono title={s.seed}>{s.seed}</Mono>}
                    </th>
                    <td>
                      <span className={styles.verdict} data-tone={verdictTone(s.discovery?.verdict)}>
                        {s.discovery?.verdict ?? "not scored"}
                      </span>
                    </td>
                    <td className={styles.num}>{duration(s.kept_hours)}</td>
                    <td className={styles.num}>{pct(s.yield)}</td>
                    <td className={styles.num}>{usd(s.usd_per_kept_hour)}</td>
                    <td className={styles.bars}>
                      <Decisions s={s} />
                      <span className={styles.count}>{s.items} files</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </main>
  );
}
