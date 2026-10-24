import { motion as m, useReducedMotion } from "framer-motion";

import type { Loss } from "../../shared/api/types";
import { duration } from "../../shared/lib/format";
import { reasonOf } from "../../shared/lib/reasons";
import { motion, tapeDelay } from "../../shared/theme/motion";
import styles from "./HoursTape.module.css";

/**
 * Every analysed hour of audio, laid end to end: what was kept, then what each reason took.
 * Files rejected before decoding (licence, declared synthetic) have no measured hours and are
 * counted underneath instead.
 */
export function HoursTape({ total, kept, losses }: { total: number; kept: number; losses: Loss[] }) {
  const reduce = useReducedMotion();
  const timed = losses.filter((l) => l.hours > 0);
  const untimed = losses.filter((l) => l.hours === 0 && l.files > 0);
  const parts = [{ reason: "kept", hours: kept, files: 0 }, ...timed];
  const sum = parts.reduce((s, p) => s + p.hours, 0) || 1;
  return (
    <figure className={styles.figure}>
      <div className={styles.tape} role="img" aria-label={`${duration(kept)} kept of ${duration(total)} analysed`}>
        {parts.map((p, i) => {
          const r = reasonOf(p.reason === "kept" ? null : p.reason);
          return (
            <m.span
              key={p.reason}
              className={styles.part}
              data-family={p.reason === "synthetic_suspected" ? "held" : r.family}
              style={{ flexGrow: p.hours / sum }}
              initial={reduce ? false : { scaleX: 0, opacity: 0 }}
              animate={{ scaleX: 1, opacity: 1 }}
              transition={{ duration: motion.base, ease: motion.ease, delay: reduce ? 0 : tapeDelay(i) }}
              title={`${r.label}: ${duration(p.hours)}`}
            />
          );
        })}
      </div>
      <figcaption className={styles.legend}>
        <ol className={styles.list}>
          {parts.map((p) => {
            const r = reasonOf(p.reason === "kept" ? null : p.reason);
            return (
              <li key={p.reason} data-family={p.reason === "synthetic_suspected" ? "held" : r.family}>
                <span className={styles.swatch} aria-hidden />
                <span className={styles.label}>{r.label}</span>
                <span className={styles.hours}>{duration(p.hours)}</span>
                {p.files > 0 && <span className={styles.files}>{p.files} files</span>}
              </li>
            );
          })}
        </ol>
        {untimed.length > 0 && (
          <p className={styles.untimed}>
            Rejected before decoding, so no hours measured: {untimed.map((l) => `${reasonOf(l.reason).label.toLowerCase()} (${l.files} files)`).join(", ")}.
          </p>
        )}
      </figcaption>
    </figure>
  );
}
