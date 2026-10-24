import { type FormEvent, useState } from "react";

import { api } from "../../shared/api/client";
import { useExecuteTakedown, useTakedowns } from "../../shared/api/queries";
import type { TakedownImpact } from "../../shared/api/types";
import { duration } from "../../shared/lib/format";
import { EmptyState, ErrorState, QueryView } from "../../shared/ui/states";
import styles from "./TakedownsPage.module.css";

const KINDS: Array<[string, string, string]> = [
  ["url", "One URL", "https://example.org/episodes/12.mp3"],
  ["domain", "A whole domain", "example.org"],
  ["speaker", "A voice", "spk0003"],
  ["item", "One file by id", "42"],
];

function Request() {
  const [kind, setKind] = useState("url");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [impact, setImpact] = useState<TakedownImpact | null>(null);
  const [previewErr, setPreviewErr] = useState<unknown>(null);
  const exec = useExecuteTakedown();
  const body = { kind, value, reason };
  const preview = async (e: FormEvent) => {
    e.preventDefault();
    setPreviewErr(null);
    try {
      setImpact(await api.previewTakedown(body));
    } catch (err) {
      setPreviewErr(err);
    }
  };
  return (
    <form className={styles.form} onSubmit={preview}>
      <h2 className={styles.h2}>Take something down</h2>
      <fieldset className={styles.kinds}>
        <legend>What to remove</legend>
        {KINDS.map(([k, label]) => (
          <label key={k}>
            <input type="radio" name="kind" value={k} checked={kind === k} onChange={() => (setKind(k), setImpact(null))} />
            {label}
          </label>
        ))}
      </fieldset>
      <label className={styles.field}>
        <span>Value</span>
        <input required value={value} placeholder={KINDS.find((x) => x[0] === kind)?.[2]} onChange={(e) => (setValue(e.target.value), setImpact(null))} />
      </label>
      <label className={styles.field}>
        <span>Reason, as the requester gave it</span>
        <textarea required minLength={3} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button type="submit" className={styles.secondary}>
        Show what it would remove
      </button>
      {previewErr !== null && <ErrorState error={previewErr} what="the impact" />}
      {impact && (
        <div className={styles.impact} role="status">
          <p>
            Withdraws {impact.items} files and {impact.segments} segments ({duration(impact.kept_hours)} of kept speech), deletes their stored audio and blocks re-ingestion.
          </p>
          <p>{impact.releases.length ? `Contained in releases ${impact.releases.join(", ")}: whoever trained on them must be told.` : "No release contains them yet."}</p>
          <button type="button" className={styles.danger} disabled={exec.isPending || impact.items + impact.segments === 0} onClick={() => exec.mutate(body, { onSuccess: () => (setImpact(null), setValue(""), setReason("")) })}>
            Take it down
          </button>
          {exec.error && <ErrorState error={exec.error} what="the takedown" />}
        </div>
      )}
    </form>
  );
}

export function TakedownsPage() {
  const q = useTakedowns();
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.h1}>Takedowns</h1>
        <p className={styles.muted}>Requests from rights holders and speakers. Every takedown is in the audit trail and in the next release's summary.</p>
      </header>
      <Request />
      <section>
        <h2 className={styles.h2}>Done so far</h2>
        <QueryView query={q} what="takedowns" lines={4} isEmpty={(t) => t.length === 0} empty={<EmptyState title="No takedowns yet" />}>
          {(ts) => (
            <ul className={styles.done}>
              {ts.map((t) => (
                <li key={t.id}>
                  <p>
                    <strong>
                      #{t.id} {t.kind} {t.value}
                    </strong>{" "}
                    by {t.requested_by}, {new Date(t.requested_at).toLocaleString()}
                  </p>
                  <p className={styles.muted}>{t.reason}</p>
                  {t.affected && (
                    <p className={styles.muted}>
                      Withdrew {t.affected.items} files and {t.affected.segments} segments, deleted {t.affected.blobs_deleted} stored files
                      {t.affected.releases.length ? `; was in ${t.affected.releases.join(", ")}` : ""}.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </QueryView>
      </section>
    </main>
  );
}
