import { useLayoutEffect, useRef, useState } from "react";

import { useItem, useSpectrogram } from "../../shared/api/queries";
import type { ItemDetail } from "../../shared/api/types";
import { fileOf, hostOf, pct, seconds } from "../../shared/lib/format";
import { usePlayer } from "../../shared/lib/usePlayer";
import { Mono, Reason } from "../../shared/ui/marks";
import { EmptyState, ErrorState, QueryView, Skeleton } from "../../shared/ui/states";
import styles from "./ItemPanel.module.css";
import { SpectrogramView } from "./Spectrogram";

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => e && setW(Math.max(200, Math.round(e.contentRect.width / 100) * 100)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function Measures({ d }: { d: ItemDetail }) {
  const a = d.analysis;
  const det = d.item.detail as Record<string, unknown>;
  const tags = (det.tags ?? a?.tags ?? {}) as Record<string, number>;
  const rows: Array<[string, string]> = [
    ["Licence", `${d.item.licence}${d.item.licence_evidence ? `, from ${d.item.licence_evidence}` : ""}`],
    ["Credit", d.item.attribution || "none given"],
  ];
  if (a) {
    rows.push(["Audio", `${seconds(a.seconds)} of ${String(a.codec ?? "")} at ${a.native_rate ?? "?"} Hz`]);
    rows.push(["Bandwidth", `content up to ${Math.round(Number(a.bandwidth_hz ?? 0))} Hz${det.tier ? ` (${String(det.tier)} tier)` : ""}`]);
    rows.push(["Signal to noise", `${Number(a.snr_db ?? 0).toFixed(1)} dB`]);
    rows.push(["Speech", `${pct(Number(a.speech_ratio ?? 0))} of the file; tagger ${pct(tags.speech)} speech, ${pct(tags.music)} music, ${pct(tags.synthesizer)} synthesizer`]);
  }
  if (typeof det.why === "string") rows.push(["Why", det.why]);
  return (
    <dl className={styles.measures}>
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Spec({ d }: { d: ItemDetail }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const q = useSpectrogram(d.audio_available ? d.item.id : null, width);
  const player = usePlayer();
  return (
    <div ref={ref} className={styles.spec}>
      {!d.audio_available ? (
        <EmptyState title="No audio to show">{d.item.sha256 ? "The audio was deleted after a takedown." : "Nothing was downloaded for this file."}</EmptyState>
      ) : q.isPending ? (
        <Skeleton lines={6} label="Loading the spectrogram" />
      ) : q.isError ? (
        <ErrorState error={q.error} what="the spectrogram" onRetry={() => void q.refetch()} />
      ) : (
        <>
          <SpectrogramView spec={q.data} segments={d.segments} playing={player.playing} onPlay={(s) => void player.play(s.id, d.item.id, s.start_s, s.end_s)} />
          {player.error && <p role="alert" className={styles.error}>{player.error}</p>}
          <Segments d={d} player={player} />
        </>
      )}
    </div>
  );
}

function Segments({ d, player }: { d: ItemDetail; player: ReturnType<typeof usePlayer> }) {
  if (!d.segments.length) return <p className={styles.muted}>The file was decided before it was cut into segments.</p>;
  return (
    <div className={styles.scroll}>
      <table className={styles.segs}>
        <caption className="visually-hidden">Segments</caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="visually-hidden">Play</span>
            </th>
            <th scope="col">Time</th>
            <th scope="col">Transcript</th>
            <th scope="col">SNR</th>
            <th scope="col">Decision</th>
          </tr>
        </thead>
        <tbody>
          {d.segments.map((s) => (
            <tr key={s.id} data-state={s.state}>
              <td>
                <button type="button" className={styles.play} onClick={() => void player.play(s.id, d.item.id, s.start_s, s.end_s)} aria-pressed={player.playing === s.id}>
                  {player.playing === s.id ? "Stop" : "Play"}
                </button>
              </td>
              <td className={styles.time}>
                {seconds(s.start_s)} to {seconds(s.end_s)}
              </td>
              <td>
                <p>{s.text || <em className={styles.muted}>no transcript</em>}</p>
                {s.cer !== null && s.text !== s.asr && <p className={styles.asr}>Heard: {s.asr}</p>}
              </td>
              <td className={styles.num}>{s.snr_db.toFixed(0)} dB</td>
              <td>
                <Reason reason={s.reason} state={s.state} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Everything known about one file: where it came from, what was measured, how it sounds. */
export function ItemPanel({ id }: { id: number }) {
  const q = useItem(id);
  return (
    <QueryView query={q} what={`file ${id}`} lines={10}>
      {(d) => (
        <article className={styles.panel}>
          <header className={styles.head}>
            <div>
              <h2 className={styles.title}>{fileOf(d.item.url)}</h2>
              <p className={styles.where}>
                {hostOf(d.item.url)}, source {d.item.source}
              </p>
              <Mono title={d.item.url}>{d.item.url}</Mono>
            </div>
            <Reason reason={d.item.reason} state={d.item.state} />
          </header>
          <Measures d={d} />
          <Spec d={d} />
        </article>
      )}
    </QueryView>
  );
}
