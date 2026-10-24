import { useEffect, useRef, useState } from "react";

import type { Segment, Spectrogram as Spec } from "../../shared/api/types";
import { seconds as fmtSeconds } from "../../shared/lib/format";
import styles from "./Spectrogram.module.css";

const STOPS = ["--spec-0", "--spec-1", "--spec-2", "--spec-3", "--spec-4", "--spec-5"];

function hex(c: string): [number, number, number] {
  const v = c.trim().replace("#", "");
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}

/** 0..1 to a colour on the inferno-like ramp defined by the --spec-* tokens. */
export function ramp(stops: Array<[number, number, number]>, t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i] as [number, number, number];
  const b = stops[i + 1] as [number, number, number];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/**
 * The file as a reviewer hears it: a log-frequency spectrogram with the pipeline's segments drawn
 * over it (kept in teal, rejected in magenta). Selecting a segment plays it.
 */
export function SpectrogramView({
  spec,
  segments,
  playing,
  onPlay,
}: {
  spec: Spec;
  segments: Segment[];
  playing: number | null;
  onPlay: (s: Segment) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx || !spec.frames.length) {
      if (el && !ctx) setFailed(true);
      return;
    }
    const css = getComputedStyle(el);
    const stops = STOPS.map((s) => hex(css.getPropertyValue(s) || "#000000"));
    const w = spec.frames.length;
    const h = spec.frames[0]?.length ?? 0;
    el.width = w;
    el.height = h;
    const img = ctx.createImageData(w, h);
    spec.frames.forEach((col, x) => {
      col.forEach((v, band) => {
        const y = h - 1 - band;
        const [r, g, b] = ramp(stops, v);
        const o = (y * w + x) * 4;
        img.data[o] = r;
        img.data[o + 1] = g;
        img.data[o + 2] = b;
        img.data[o + 3] = 255;
      });
    });
    ctx.putImageData(img, 0, 0);
  }, [spec]);

  const total = spec.seconds || 1;
  const ticks = Array.from({ length: 6 }, (_, i) => (total * i) / 5);
  return (
    <figure className={styles.figure}>
      <div className={styles.frame}>
        {failed ? (
          <p className={styles.fallback}>This browser cannot draw the spectrogram; the segments below still play.</p>
        ) : (
          <canvas ref={canvas} className={styles.canvas} role="img" aria-label={`Spectrogram, ${fmtSeconds(total)}, 60 Hz to 8 kHz`} />
        )}
        <div className={styles.lanes}>
          {segments
            .filter((s) => s.start_s < total)
            .map((s) => (
              <button
                key={s.id}
                type="button"
                className={styles.seg}
                data-state={s.state}
                data-playing={playing === s.id || undefined}
                style={{ left: `${(s.start_s / total) * 100}%`, width: `${(Math.min(s.end_s, total) - s.start_s) / total * 100}%` }}
                onClick={() => onPlay(s)}
                aria-label={`Play segment ${s.idx + 1}, ${fmtSeconds(s.start_s)} to ${fmtSeconds(s.end_s)}, ${s.state}${s.reason ? `: ${s.reason}` : ""}`}
              />
            ))}
        </div>
      </div>
      <div className={styles.axis} aria-hidden>
        {ticks.map((t) => (
          <span key={t}>{fmtSeconds(t)}</span>
        ))}
      </div>
    </figure>
  );
}
