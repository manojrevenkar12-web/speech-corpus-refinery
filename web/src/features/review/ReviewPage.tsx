import { AnimatePresence, motion as m } from "framer-motion";
import { useCallback, useEffect, useState } from "react";

import { useQueue, useResolve, useReview, useReviewSummary } from "../../shared/api/queries";
import type { QueueRow } from "../../shared/api/types";
import { fileOf, hostOf } from "../../shared/lib/format";
import { reasonOf } from "../../shared/lib/reasons";
import { motion } from "../../shared/theme/motion";
import { Reason } from "../../shared/ui/marks";
import { EmptyState, ErrorState, QueryView } from "../../shared/ui/states";
import { ItemPanel } from "./ItemPanel";
import styles from "./ReviewPage.module.css";

type Kind = "held" | "kept" | "rejected";
const TABS: Array<[Kind, string, string]> = [
  ["held", "Held for review", "Files that may be synthetic speech. Nothing held is released until a person decides."],
  ["rejected", "Check rejections", "A random sample of rejected files, one per reason in turn. Do you agree with the reason?"],
  ["kept", "Check kept files", "A random sample of kept files. Would you train on them?"],
];

function Actions({ kind, row, onDone }: { kind: Kind; row: QueueRow; onDone: () => void }) {
  const resolve = useResolve();
  const review = useReview();
  const busy = resolve.isPending || review.isPending;
  const err = resolve.error ?? review.error;
  const act = useCallback(
    (what: "keep" | "reject" | "agree" | "disagree") => {
      if (busy) return;
      if (what === "keep" || what === "reject") resolve.mutate({ id: row.id, decision: what }, { onSuccess: onDone });
      else review.mutate({ item_id: row.id, verdict: what }, { onSuccess: onDone });
    },
    [busy, resolve, review, row.id, onDone],
  );
  useEffect(() => {
    const keys: Record<string, "keep" | "reject" | "agree" | "disagree"> = kind === "held" ? { k: "keep", r: "reject" } : { a: "agree", d: "disagree" };
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.metaKey || e.ctrlKey) return;
      const v = keys[e.key.toLowerCase()];
      if (v) act(v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [kind, act]);
  return (
    <div className={styles.actions} aria-busy={busy}>
      {kind === "held" ? (
        <>
          <button type="button" className={styles.keep} onClick={() => act("keep")} disabled={busy}>
            Keep it <kbd>K</kbd>
          </button>
          <button type="button" className={styles.reject} onClick={() => act("reject")} disabled={busy}>
            Reject as synthetic <kbd>R</kbd>
          </button>
        </>
      ) : (
        <>
          <button type="button" className={styles.keep} onClick={() => act("agree")} disabled={busy}>
            Agree <kbd>A</kbd>
          </button>
          <button type="button" className={styles.reject} onClick={() => act("disagree")} disabled={busy}>
            Disagree <kbd>D</kbd>
          </button>
        </>
      )}
      {err && <ErrorState error={err} what="your decision" />}
    </div>
  );
}

function Summary() {
  const q = useReviewSummary();
  return (
    <QueryView query={q} what="review results" lines={3} isEmpty={(r) => r.length === 0} empty={<p className={styles.muted}>No spot checks yet.</p>}>
      {(rows) => (
        <table className={styles.summary}>
          <caption>How often reviewers agree with each decision (95% Wilson interval)</caption>
          <tbody>
            {rows.map((r) => (
              <tr key={r.decision}>
                <th scope="row">{reasonOf(r.decision === "kept" ? null : r.decision).label}</th>
                <td>
                  {r.agree} of {r.n}
                </td>
                <td className={styles.muted}>{r.agree_interval ? `${Math.round(r.agree_interval[0] * 100)} to ${Math.round(r.agree_interval[1] * 100)}%` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </QueryView>
  );
}

export function ReviewPage() {
  const [kind, setKind] = useState<Kind>("held");
  const q = useQueue(kind);
  const [idx, setIdx] = useState(0);
  const [done, setDone] = useState<number[]>([]);
  const rows = (q.data ?? []).filter((r) => !done.includes(r.id));
  const current = rows[Math.min(idx, rows.length - 1)];
  const next = useCallback(() => {
    if (current) setDone((d) => [...d, current.id]);
  }, [current]);
  useEffect(() => {
    setIdx(0);
    setDone([]);
  }, [kind]);

  return (
    <div className={styles.page}>
      <aside className={styles.rail}>
        <h1 className={styles.h1}>Review</h1>
        <div role="tablist" aria-label="Queue" className={styles.tabs}>
          {TABS.map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => setKind(k)}>
              {label}
            </button>
          ))}
        </div>
        <p className={styles.muted}>{TABS.find((t) => t[0] === kind)?.[2]}</p>
        <QueryView
          query={q}
          what="the review queue"
          lines={6}
          isEmpty={() => rows.length === 0}
          empty={<EmptyState title={kind === "held" ? "Nothing is held" : "Nothing left to check"}>{kind === "held" ? "Every suspicious file has been decided." : "Every file in this sample has a review."}</EmptyState>}
        >
          {() => (
            <ol className={styles.list} aria-label="Files in the queue">
              {rows.map((r, i) => (
                <li key={r.id}>
                  <button type="button" className={styles.row} aria-current={r.id === current?.id} onClick={() => setIdx(i)}>
                    <span className={styles.file}>{fileOf(r.url)}</span>
                    <span className={styles.host}>{hostOf(r.url)}</span>
                    <Reason reason={r.reason} state={r.state} />
                  </button>
                </li>
              ))}
            </ol>
          )}
        </QueryView>
        <Summary />
      </aside>
      <main className={styles.main}>
        {q.isError ? (
          <ErrorState error={q.error} what="the review queue" onRetry={() => void q.refetch()} />
        ) : current ? (
          <AnimatePresence mode="wait">
            <m.div
              key={current.id}
              className={styles.stage}
              initial={{ opacity: 0, y: motion.rise }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: motion.base, ease: motion.ease }}
            >
              <Actions kind={kind} row={current} onDone={next} />
              <ItemPanel id={current.id} />
            </m.div>
          </AnimatePresence>
        ) : (
          !q.isPending && <EmptyState title="Choose a queue">Held files first: they block a release until decided.</EmptyState>
        )}
      </main>
    </div>
  );
}
