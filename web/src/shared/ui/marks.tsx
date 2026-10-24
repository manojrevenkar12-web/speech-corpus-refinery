import type { ReactNode } from "react";

import { reasonOf } from "../lib/reasons";
import styles from "./marks.module.css";

/** A decision reason as a small coloured label (colour by family, words always present). */
export function Reason({ reason, state }: { reason: string | null | undefined; state?: string }) {
  const r = state === "kept" || (!reason && state !== "withdrawn") ? reasonOf(null) : reasonOf(reason ?? "takedown");
  const family = state === "held" ? "held" : r.family;
  return (
    <span className={styles.reason} data-family={family}>
      {r.label}
    </span>
  );
}

export function Mono({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <code className={styles.mono} title={title}>
      {children}
    </code>
  );
}

export function Stat({ value, label, tone }: { value: ReactNode; label: string; tone?: "kept" | "rejected" | "held" | "rights" }) {
  return (
    <div className={styles.stat} data-tone={tone}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}
