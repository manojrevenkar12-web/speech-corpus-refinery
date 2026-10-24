"""From one downloaded file to a decision and a set of segments.

Cheap checks run first so rejected files cost almost nothing: licence and declared synthetic
content are decided before decoding. Then decode, fingerprint (duplicates and the protected
evaluation set), signal and model probes, segmentation, ASR, alignment to published text and
speaker embeddings. Every decision records its reason and the measurements behind it; every
stage records the CPU it used, which is what the cost model reads.

Results for an item are written in one transaction, so a job that runs twice leaves one result.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import align, config, db
from .audio import decode as dec
from .audio import fingerprint as fp
from .audio import models, probes
from .rights import licence as lic
from .store import LocalStore, Store

# Reasons and the order they are checked in. Earlier reasons are cheaper or weightier.
ITEM_REASONS = ["licence", "synthetic", "corrupt", "too_short", "protected", "duplicate", "not_speech", "language", "bandwidth", "music"]
SEGMENT_REASONS = ["noise", "clipping", "misaligned", "no_text"]


@dataclass
class Costs:
    rows: list[tuple[str, float, float, float]] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str, audio_seconds: float = 0.0) -> Iterator[None]:
        c0, w0 = time.process_time(), time.perf_counter()
        try:
            yield
        finally:
            self.rows.append((name, time.process_time() - c0, time.perf_counter() - w0, audio_seconds))


@dataclass
class Segment:
    idx: int
    start: float
    end: float
    asr: str = ""
    text: str = ""
    cer: float | None = None
    snr_db: float = 0.0
    clipped: float = 0.0
    embedding: list[float] | None = None
    state: str = "kept"
    reason: str | None = None


def _music_in_pauses(x: np.ndarray, spans: list[models.Span], a_cfg: dict[str, Any]) -> float | None:
    """A music bed hides under speech but is exposed in the pauses. Join the pauses (away from
    speech edges), bring them to a speaking level, and ask the tagger. None when the pauses are
    too short or digitally silent."""
    rate, pad = 16000, 0.05
    bounds = [0.0, *[v for s in spans for v in (s.start, s.end)], len(x) / rate]
    gaps = [(bounds[i] + pad, bounds[i + 1] - pad) for i in range(0, len(bounds) - 1, 2)]
    parts = [x[int(a * rate) : int(b * rate)] for a, b in gaps if b - a >= 0.15]
    if not parts:
        return None
    y = np.concatenate(parts)[: rate * 30]
    if len(y) < int(0.4 * rate) or probes.dbfs(y) < float(a_cfg.get("pause_floor_dbfs", -65)):
        return None
    y = y * (10 ** (-20 / 20) / (np.sqrt(np.mean(np.square(y))) + 1e-12))
    return models.tags(np.clip(y, -1, 1).astype(np.float32))["music"]


def blob_path(store: Store, sha: str, tmpdir: Path) -> Path:
    if isinstance(store, LocalStore):
        return store.get_file(sha, tmpdir / sha)
    return store.get_file(sha, tmpdir / sha)


def merge_spans(spans: list[models.Span], s: dict[str, Any], total: float) -> list[tuple[float, float]]:
    """VAD regions into training segments: short regions join their neighbours across short
    gaps, nothing exceeds the maximum length, and each segment gets a little padding."""
    lo, hi, pad = float(s["min_seconds"]), float(s["max_seconds"]), float(s["pad_seconds"])
    out: list[list[float]] = []
    for sp in spans:
        if (
            out
            and (sp.start - out[-1][1] < 0.5)
            and (sp.end - out[-1][0] <= hi)
            and (out[-1][1] - out[-1][0] < lo or sp.end - sp.start < lo)
        ):
            out[-1][1] = sp.end
        else:
            out.append([sp.start, sp.end])
    return [(max(0.0, a - pad), min(total, b + pad)) for a, b in out if b - a >= lo]


def _published_text(c: Any, item: dict[str, Any], store: Store, tmp: Path) -> str:
    if item["meta"].get("transcript"):
        return str(item["meta"]["transcript"])
    if not item["text_url"]:
        return ""
    r = c.execute("SELECT meta FROM urls WHERE url = %s AND state = 'done'", (item["text_url"],)).fetchone()
    if not r or not r["meta"].get("sha256"):
        return ""
    return blob_path(store, r["meta"]["sha256"], tmp).read_text(errors="replace")


def analyse(item_id: int, store: Store, url: str | None = None) -> dict[str, Any]:
    cfg = config.settings()
    rights = config.rights()
    d, a_cfg, seg_cfg, dd = cfg["decide"], cfg["audio"], cfg["segment"], cfg["dedup"]
    chash = config.fingerprint(cfg, rights)
    costs = Costs()
    with db.tx(url) as c:
        item = c.execute("SELECT * FROM items WHERE id = %s", (item_id,)).fetchone()
    if item is None:
        raise LookupError(f"item {item_id}")

    def finish(
        state: str,
        reason: str | None,
        detail: dict[str, Any],
        analysis: dict[str, Any] | None = None,
        segments: list[Segment] | None = None,
    ) -> dict[str, Any]:
        with db.tx(url) as c:
            c.execute("DELETE FROM segments WHERE item_id = %s", (item_id,))
            if analysis is not None:
                cols = ["item_id", "config_hash", *analysis]
                c.execute(
                    f"INSERT INTO analyses ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    f"ON CONFLICT (item_id) DO UPDATE SET {', '.join(f'{k} = EXCLUDED.{k}' for k in cols[1:])}",
                    (item_id, chash, *[json.dumps(v) if isinstance(v, dict) else v for v in analysis.values()]),
                )
            for sg in segments or []:
                c.execute(
                    """INSERT INTO segments (item_id, idx, start_s, end_s, asr, text, cer, snr_db, clipped_ratio, bandwidth_hz, tier, embedding, state, reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        item_id,
                        sg.idx,
                        sg.start,
                        sg.end,
                        sg.asr,
                        sg.text,
                        sg.cer,
                        sg.snr_db,
                        sg.clipped,
                        (analysis or {}).get("bandwidth_hz"),
                        detail.get("tier"),
                        sg.embedding,
                        sg.state,
                        sg.reason,
                    ),
                )
            c.execute(
                "UPDATE items SET state = %s, reason = %s, detail = %s, decided_config = %s, decided_at = now() WHERE id = %s",
                (state, reason, json.dumps(detail, default=float), chash, item_id),
            )
            for name, cpu, wall, audio_s in costs.rows:
                c.execute(
                    "INSERT INTO costs (stage, item_id, source_id, cpu_seconds, wall_seconds, audio_seconds) VALUES (%s, %s, %s, %s, %s, %s)",
                    (name, item_id, item["source_id"], cpu, wall, audio_s),
                )
        return {"state": state, "reason": reason, **detail}

    # 1. rights and provenance: decided before any decoding
    with costs.stage("policy"):
        verdict = lic.decide(item["licence"], rights)
    if not verdict.allowed:
        return finish("rejected", "licence", {"licence": item["licence"], "why": verdict.reason, "evidence": item["licence_evidence"]})
    if item["synthetic_declared"] and not rights.get("allow_synthetic"):
        return finish("rejected", "synthetic", {"why": "the source declares the audio AI-generated (IPTC trainedAlgorithmicMedia)"})

    with tempfile.TemporaryDirectory(prefix="scr-item-") as td:
        tmp = Path(td)
        path = blob_path(store, item["sha256"], tmp)

        # 2. decode
        try:
            with costs.stage("decode"):
                au = dec.decode(path, int(a_cfg["analysis_rate"]), float(a_cfg["bandwidth_window_seconds"]))
        except dec.DecodeError as e:
            return finish("rejected", "corrupt", {"why": str(e)[:300]})
        seconds = au.seconds
        x = au.samples
        base: dict[str, Any] = {
            "codec": au.codec,
            "native_rate": au.native_rate,
            "channels": au.channels,
            "seconds": seconds,
            "pcm_sha256": hashlib.sha256(x.tobytes()).hexdigest(),
        }
        if seconds < float(a_cfg["min_item_seconds"]) or seconds > float(a_cfg["max_item_seconds"]):
            return finish("rejected", "too_short" if seconds < 1 else "corrupt", {"seconds": seconds}, base)

        # 3. cheap signal probes: bandwidth, speech regions, SNR (also used to pick the better duplicate)
        with costs.stage("bandwidth"):
            bw = probes.bandwidth(au.native, au.native_rate, float(a_cfg["bandwidth_floor_db"]))
        with costs.stage("vad", seconds):
            spans = models.vad(x)
        speech_s = sum(s.end - s.start for s in spans)
        mask = models.speech_mask(spans, seconds)
        snr_item = probes.snr(x, 16000, mask)
        base |= {
            "bandwidth_hz": bw,
            "speech_ratio": speech_s / seconds,
            "snr_db": snr_item.db,
            "snr_method": snr_item.method,
            "dbfs": probes.dbfs(x),
            "clipped_ratio": probes.clipped_ratio(x, float(a_cfg["clip_threshold"])),
        }

        # 4. fingerprint: the protected evaluation set, then duplicates (one dedup at a time)
        with costs.stage("fingerprint", seconds):
            fr = int(dd["fingerprint_rate"])
            pk = fp.peaks(dec.resample(path, fr), fr)
            marks = fp.hashes(pk)
            variants: list[tuple[float, list[tuple[int, int]]]] = []
            if seconds <= float(dd["speed_search_max_seconds"]):
                # a copy played at speed s lines up once its peaks are stretched back by s
                variants = [(s, fp.hashes(fp.at_speed(pk, s))) for s in speed_factors(float(dd["speed_max"]), float(dd["speed_step"]))]
            quality = quality_key(bw, snr_item.db, int(path.stat().st_size) / max(seconds, 1e-9))
            dup = _dedup(item_id, marks, variants, quality, dd, url)
        if dup.get("takedown"):
            return finish("rejected", "takedown", dup, base | {"match": dup})
        if dup.get("protected"):
            return finish("rejected", "protected", dup, base | {"match": dup})
        if dup.get("duplicate_of"):
            return finish("rejected", "duplicate", dup, base | {"canonical_of": dup["duplicate_of"], "match": dup})

        # 5. is it speech, wide enough, without music, in the right language?
        with costs.stage("tags", min(seconds, 120.0)):
            tags = models.tags(x[: 16000 * 120])
        base["tags"] = tags
        detail: dict[str, Any] = {
            "speech_ratio": round(speech_s / seconds, 3),
            "tags": {k: round(v, 3) for k, v in tags.items()},
            "bandwidth_hz": round(bw),
            "snr_db": round(snr_item.db, 1),
        }
        if speech_s / seconds < float(d["min_speech_ratio"]) or tags["speech"] < float(d["speech_tag_min"]):
            return finish("rejected", "not_speech", detail, base)
        if bw < float(d["min_bandwidth_hz"]):
            return finish("rejected", "bandwidth", detail | {"why": f"content stops at {bw:.0f} Hz in a {au.native_rate} Hz file"}, base)
        with costs.stage("tags", 0.0):
            pause_music = _music_in_pauses(x, spans, a_cfg)
        if pause_music is not None:
            detail["pause_music"] = round(pause_music, 3)
        if tags["music"] > float(d["music_tag_max"]) or (pause_music is not None and pause_music > float(d["pause_music_max"])):
            return finish("rejected", "music", detail, base)
        with costs.stage("language", min(speech_s, 30.0)):
            voiced = np.concatenate([x[int(s.start * 16000) : int(s.end * 16000)] for s in spans]) if spans else x
            lang = models.language(voiced[: 16000 * 30])
        base["language"] = lang
        detail["language"] = lang
        if d.get("language_must_match") and lang != cfg["target"]["language"]:
            return finish("rejected", "language", detail, base)
        tiers = d["tiers"]
        detail["tier"] = "full" if bw >= float(tiers["full"]) else "wide"
        held = tags["synthesizer"] >= float(d["synthetic_tag_review"])
        if held:
            # not a rejection: the tag also fires on clean studio speech, so a person decides
            detail["review"] = "synthetic_suspected"

        # 6. segments: ASR, alignment to the published text, quality, speaker embedding
        with db.tx(url) as c:
            text = _published_text(c, item, store, tmp)
            blocked_voices = [np.asarray(r["centroid"], np.float32) for r in c.execute("SELECT centroid FROM blocked_speakers")]
        book = align.Book(text) if text else None
        segs: list[Segment] = []
        cursor = 0
        for i, (s0, s1) in enumerate(merge_spans(spans, seg_cfg, seconds)):
            y = x[int(s0 * 16000) : int(s1 * 16000)]
            sg = Segment(i, s0, s1)
            ctx0, ctx1 = max(0, int((s0 - 5) * 16000)), min(len(x), int((s1 + 5) * 16000))
            sg.snr_db = probes.snr(x[ctx0:ctx1], 16000, mask[int(ctx0 / 160) : int(ctx1 / 160) + 1]).db
            sg.clipped = probes.clipped_ratio(y, float(a_cfg["clip_threshold"]))
            with costs.stage("asr", s1 - s0):
                sg.asr = models.transcribe(y, cfg["target"]["language"])
            if book is not None:
                al = book.align(sg.asr, cursor)
                if al is not None:
                    sg.text, sg.cer, cursor = al.text, al.cer, al.end_word
            else:
                sg.text = sg.asr
            with costs.stage("speaker", s1 - s0):
                sg.embedding = [round(float(v), 5) for v in models.embedding(y)]
            if blocked_voices and max(float(np.dot(v, np.asarray(sg.embedding, np.float32))) for v in blocked_voices) >= float(
                cfg["speakers"]["cluster_threshold"]
            ):
                sg.state, sg.reason = "rejected", "takedown"
            elif sg.snr_db < float(d["min_snr_db"]):
                sg.state, sg.reason = "rejected", "noise"
            elif sg.clipped > float(d["max_clipped_ratio"]):
                sg.state, sg.reason = "rejected", "clipping"
            elif book is not None and (sg.cer is None or sg.cer > float(d["max_alignment_cer"])):
                sg.state, sg.reason = "rejected", "misaligned"
            elif len(align.norm_words(sg.text)) < int(d["min_words"]):
                sg.state, sg.reason = "rejected", "no_text"
            segs.append(sg)
        kept = [s for s in segs if s.state == "kept"]
        detail |= {
            "segments": len(segs),
            "kept_segments": len(kept),
            "kept_seconds": round(sum(s.end - s.start for s in kept), 2),
            "text": "published" if book else "asr",
        }
        if not kept:
            reasons = [s.reason for s in segs if s.reason]
            why = max(set(reasons), key=reasons.count) if reasons else "not_speech"
            return finish("rejected", why, detail, base, segs)
        if held:
            return finish("held", "synthetic_suspected", detail, base, segs)
        return finish("kept", None, detail, base, segs)


def speed_factors(max_change: float, step: float) -> list[float]:
    """Stretch factors that undo a speed change of up to `max_change`, nearest first, both ways."""
    out: list[float] = []
    n = round(max_change / step)
    for k in range(1, n + 1):
        f = 1 + k * step
        out += [f, 1 / f]
    return out


def quality_key(bandwidth_hz: float, snr_db: float, bytes_per_second: float) -> tuple[float, float, float]:
    """Which of two copies is better: the higher bandwidth tier (full, wide, below), then SNR in
    5 dB steps, then bitrate. Tiers rather than raw hertz, because broadband noise widens the
    measured bandwidth of a worse copy."""
    tiers = config.settings()["decide"]["tiers"]
    tier = 2.0 if bandwidth_hz >= float(tiers["full"]) else 1.0 if bandwidth_hz >= float(tiers["wide"]) else 0.0
    return (tier, float(round(snr_db / 5.0)), float(bytes_per_second))


def _match(c: Any, queries: list[tuple[float, list[tuple[int, int]]]], dd: dict[str, Any]) -> tuple[list[tuple[float, fp.Match]], dict[int, dict[str, Any]]]:
    """Hits for the plain fingerprint and every speed variant, from one index lookup; for each
    indexed recording, the speed at which it matched best."""
    hashes = sorted({h for _, marks in queries for h, _ in marks})
    if not hashes:
        return [], {}
    rows = c.execute("SELECT h, fp_id, t FROM fp_hashes WHERE h = ANY(%s)", (hashes,)).fetchall()
    fids = list({r["fp_id"] for r in rows})
    if not fids:
        return [], {}
    meta = {
        r["id"]: r
        for r in c.execute(
            """SELECT f.id, f.item_id, f.protected, f.blocked_by, f.label, f.n, f.quality, i.state, i.reason
               FROM fp_items f LEFT JOIN items i ON i.id = f.item_id WHERE f.id = ANY(%s)""",
            (fids,),
        )
    }
    by_hash: dict[int, list[tuple[int, int]]] = {}
    for r in rows:
        by_hash.setdefault(r["h"], []).append((r["fp_id"], r["t"]))
    sizes = {k: v["n"] for k, v in meta.items()}
    best: dict[int, tuple[float, fp.Match]] = {}
    for speed, marks in queries:
        cands = [(h, fid, t) for h in {h for h, _ in marks} for fid, t in by_hash.get(h, ())]
        for m in fp.best_matches(marks, cands, sizes):
            need = float(dd["min_match_ratio"]) if speed == 1.0 else float(dd["speed_min_match_ratio"])
            if m.votes >= int(dd["min_matches"]) and m.ratio >= need and (m.other not in best or m.votes > best[m.other][1].votes):
                best[m.other] = (speed, m)
    return sorted(best.values(), key=lambda sm: -sm[1].votes), meta


def _dedup(
    item_id: int,
    marks: list[tuple[int, int]],
    variants: list[tuple[float, list[tuple[int, int]]]],
    quality: tuple[float, float, float],
    dd: dict[str, Any],
    url: str | None,
) -> dict[str, Any]:
    """Match against the protected set, takedowns and every earlier item; keep the better copy.

    `variants` are the same audio at other playback speeds, tried when the plain fingerprint
    finds nothing (landmark hashes do not survive a speed change). Serialised with an advisory
    lock, so two workers handling two copies at the same moment cannot both decide they are the
    first; quality is stored with the fingerprint, so a copy still being processed elsewhere can
    be compared. An earlier, worse copy that is still usable is withdrawn."""
    out: dict[str, Any] = {}
    with db.tx(url) as c:
        c.execute("SELECT pg_advisory_xact_lock(7331)")
        scored, meta = _match(c, [(1.0, marks), *variants], dd)
        hits = [m for _, m in scored]
        speed_of = {m.other: sp for sp, m in scored}

        def found(m: fp.Match) -> dict[str, Any]:
            return {"speed": round(speed_of[m.other], 4)} if speed_of[m.other] != 1.0 else {}

        blocked = [m for m in hits if meta[m.other]["blocked_by"]]
        if blocked:
            return {"takedown": True, "takedown_id": meta[blocked[0].other]["blocked_by"], "votes": blocked[0].votes, **found(blocked[0])}
        prot = [m for m in hits if meta[m.other]["protected"]]
        if prot:
            out = {
                "protected": True,
                "matches": [{"label": meta[m.other]["label"], "votes": m.votes, "ratio": round(m.ratio, 3), "offset_s": round(m.offset_seconds, 2), **found(m)} for m in prot],
            }
        else:
            for m in hits:
                o = meta[m.other]
                other = o["item_id"]
                if other is None or other == item_id or o["quality"] is None:
                    continue
                if o["state"] == "withdrawn" or (o["state"] == "rejected" and o["reason"] != "duplicate"):
                    continue  # an unusable copy does not stop this one
                if tuple(o["quality"]) >= quality:
                    out = {"duplicate_of": other, "votes": m.votes, "ratio": round(m.ratio, 3), "offset_s": round(m.offset_seconds, 2), **found(m)}
                    break
                # this copy is better: the earlier one becomes the duplicate
                c.execute(
                    "UPDATE items SET state = 'rejected', reason = 'duplicate', detail = detail || %s WHERE id = %s",
                    (json.dumps({"duplicate_of": item_id, "replaced_by_better_copy": True}), other),
                )
                c.execute("UPDATE segments SET state = 'withdrawn', reason = 'duplicate' WHERE item_id = %s", (other,))
        if not out.get("protected"):
            c.execute("DELETE FROM fp_items WHERE item_id = %s", (item_id,))
            r = c.execute("INSERT INTO fp_items (item_id, n, quality) VALUES (%s, %s, %s) RETURNING id", (item_id, len(marks), list(quality))).fetchone()
            assert r is not None
            with c.cursor().copy("COPY fp_hashes (h, fp_id, t) FROM STDIN") as cp:
                for h, t in marks:
                    cp.write_row((h, r["id"], t))
    return out


def protect(label: str, path: Path, url: str | None = None) -> int:
    """Add an evaluation recording to the protected set: no copy of it may enter training data."""
    rate = int(config.settings()["dedup"]["fingerprint_rate"])
    marks = fp.landmarks(dec.resample(path, rate), rate)
    with db.tx(url) as c:
        c.execute("DELETE FROM fp_items WHERE protected AND label = %s", (label,))
        r = c.execute("INSERT INTO fp_items (protected, label, n) VALUES (true, %s, %s) RETURNING id", (label, len(marks))).fetchone()
        assert r is not None
        with c.cursor().copy("COPY fp_hashes (h, fp_id, t) FROM STDIN") as cp:
            for h, t in marks:
                cp.write_row((h, r["id"], t))
    return len(marks)
