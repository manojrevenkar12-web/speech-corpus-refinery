import { useSearchParams } from "react-router-dom";

import { useItems } from "../../shared/api/queries";
import { count, fileOf, hostOf, seconds } from "../../shared/lib/format";
import { REASONS } from "../../shared/lib/reasons";
import { Reason } from "../../shared/ui/marks";
import { EmptyState, QueryView } from "../../shared/ui/states";
import { ItemPanel } from "../review/ItemPanel";
import styles from "./ItemsPage.module.css";

const STATES = ["", "kept", "held", "rejected", "withdrawn"];

export function ItemsPage() {
  const [params, setParams] = useSearchParams();
  const state = params.get("state") ?? "";
  const reason = params.get("reason") ?? "";
  const source = params.get("source") ?? "";
  const open = params.get("item");
  const offset = Number(params.get("offset") ?? 0);
  const q = useItems({ state, reason, source, offset });
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k !== "item" && k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  return (
    <div className={styles.page}>
      <section className={styles.listCol}>
        <h1 className={styles.h1}>Files</h1>
        <div className={styles.filters}>
          <label>
            <span>State</span>
            <select value={state} onChange={(e) => set("state", e.target.value)}>
              {STATES.map((s) => (
                <option key={s} value={s}>
                  {s || "any"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Reason</span>
            <select value={reason} onChange={(e) => set("reason", e.target.value)}>
              <option value="">any</option>
              {Object.entries(REASONS)
                .filter(([k]) => k !== "kept")
                .map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
            </select>
          </label>
          {source && (
            <button type="button" className={styles.clear} onClick={() => set("source", "")}>
              Source: {source} (clear)
            </button>
          )}
        </div>
        <QueryView query={q} what="files" lines={10} isEmpty={(d) => d.total === 0} empty={<EmptyState title="No file matches">Choose another state or reason.</EmptyState>}>
          {(d) => (
            <>
              <p className={styles.count}>
                {count(d.total, "file")}{d.total > d.items.length ? `, ${offset + 1} to ${offset + d.items.length} shown` : ""}
              </p>
              <ul className={styles.list}>
                {d.items.map((it) => (
                  <li key={it.id}>
                    <button type="button" className={styles.row} aria-current={String(it.id) === open} onClick={() => set("item", String(it.id))}>
                      <span className={styles.file}>{fileOf(it.url)}</span>
                      <span className={styles.meta}>
                        {hostOf(it.url)}
                        {it.seconds ? `, ${seconds(it.seconds)}` : ""}
                      </span>
                      <Reason reason={it.reason} state={it.state} />
                    </button>
                  </li>
                ))}
              </ul>
              <div className={styles.pager}>
                <button type="button" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - 50)))}>
                  Previous 50
                </button>
                <button type="button" disabled={offset + d.items.length >= d.total} onClick={() => set("offset", String(offset + 50))}>
                  Next 50
                </button>
              </div>
            </>
          )}
        </QueryView>
      </section>
      <main className={styles.detail}>{open ? <ItemPanel key={open} id={Number(open)} /> : <EmptyState title="Choose a file">See its licence, measurements, spectrogram and segments, and listen to it.</EmptyState>}</main>
    </div>
  );
}
