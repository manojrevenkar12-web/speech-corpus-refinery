"""HTTP API for the review console: the funnel, sources and their cost, item decisions with
audio and spectrograms, the review queue (held files and spot checks), releases and takedowns.

Auth: `Authorization: Bearer <key>`, keys from SCR_API_KEYS as `key:role` with roles
viewer < reviewer < admin (keys at least 16 characters). SCR_AUTH=off for a local demo only.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import random
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import audit, config, cost, db, release, takedown
from .audio import decode as dec
from .store import Store
from .store import default as default_store

ROLES = {"viewer": 0, "reviewer": 1, "admin": 2}


def _keys() -> dict[str, str]:
    out = {}
    for pair in os.environ.get("SCR_API_KEYS", "").split(","):
        if ":" in pair:
            k, role = pair.strip().rsplit(":", 1)
            if role in ROLES and len(k) >= 16:
                out[k] = role
    return out


def require(role: str) -> Any:
    def dep(authorization: str = Header(default="")) -> str:
        if os.environ.get("SCR_AUTH") == "off":
            return "local"
        token = authorization.removeprefix("Bearer ").strip()
        for key, r in _keys().items():
            if hmac.compare_digest(key, token):
                if ROLES[r] < ROLES[role]:
                    raise HTTPException(403, f"needs the {role} role")
                return f"{r}:{key[:4]}"
        raise HTTPException(401, "missing or unknown API key")

    return dep


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson interval for a proportion: how sure a spot check is."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


class ReviewBody(BaseModel):
    item_id: int | None = None
    segment_id: int | None = None
    verdict: str = Field(pattern="^(agree|disagree)$")
    note: str = Field(default="", max_length=1000)


class ResolveBody(BaseModel):
    decision: str = Field(pattern="^(keep|reject)$")
    note: str = Field(default="", max_length=1000)


class TakedownBody(BaseModel):
    kind: str = Field(pattern="^(url|domain|speaker|item)$")
    value: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=3, max_length=1000)


def create_app(url: str | None = None, store: Store | None = None) -> FastAPI:
    app = FastAPI(title="speech-corpus-refinery", version="0.1.0")
    st = store or default_store()
    viewer = [Depends(require("viewer"))]

    def tx() -> Any:
        return db.tx(url)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        with tx() as c:
            c.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/overview", dependencies=viewer)
    def overview() -> dict[str, Any]:
        with tx() as c:
            urls = {f"{r['state']}:{r['reason'] or ''}".rstrip(":"): r["n"] for r in c.execute("SELECT state, reason, count(*) AS n FROM urls WHERE kind = 'audio' GROUP BY state, reason")}
            not_fetched = {r["reason"]: r["n"] for r in c.execute("SELECT reason, count(*) AS n FROM urls WHERE state = 'skipped' GROUP BY reason")}
            funnel_rows = c.execute(
                """SELECT i.state, i.reason, count(*) AS n, coalesce(sum(a.seconds), 0) AS secs
                   FROM items i LEFT JOIN analyses a ON a.item_id = i.id GROUP BY i.state, i.reason"""
            ).fetchall()
            kept = c.execute("SELECT coalesce(sum(s.end_s - s.start_s), 0) AS secs FROM segments s JOIN items i ON i.id = s.item_id WHERE i.state = 'kept' AND s.state = 'kept'").fetchone()
            seg_rej = c.execute(
                "SELECT s.reason, coalesce(sum(s.end_s - s.start_s), 0) AS secs FROM segments s JOIN items i ON i.id = s.item_id WHERE i.state = 'kept' AND s.state <> 'kept' GROUP BY s.reason"
            ).fetchall()
            requests = c.execute("SELECT count(*) AS n FROM fetches").fetchone()
            latest = c.execute("SELECT name, created_at, stats FROM releases ORDER BY id DESC LIMIT 1").fetchone()
            held = c.execute("SELECT count(*) AS n FROM items WHERE state = 'held'").fetchone()
            v = audit.verify(c)
            jobs = {f"{r['kind']}:{r['state']}": r["n"] for r in c.execute("SELECT kind, state, count(*) AS n FROM jobs GROUP BY kind, state")}
        files = sum(r["n"] for r in funnel_rows)
        secs = sum(float(r["secs"]) for r in funnel_rows)
        stages = []
        order = ["licence", "synthetic", "corrupt", "too_short", "takedown", "protected", "duplicate", "not_speech", "bandwidth", "music", "language", "synthetic_suspected", "noise", "clipping", "misaligned", "no_text"]
        by_reason: dict[str, dict[str, float]] = {}
        for r in funnel_rows:
            if r["state"] in ("rejected", "held", "withdrawn"):
                key = r["reason"] if r["state"] != "withdrawn" else "takedown"
                d = by_reason.setdefault(key or "other", {"files": 0, "hours": 0.0})
                d["files"] += r["n"]
                d["hours"] += float(r["secs"]) / 3600
        for r in seg_rej:
            d = by_reason.setdefault(f"segments:{r['reason']}", {"files": 0, "hours": 0.0})
            d["hours"] += float(r["secs"]) / 3600
        for k in sorted(by_reason, key=lambda k: order.index(k.split(":")[-1]) if k.split(":")[-1] in order else 99):
            stages.append({"reason": k, "files": by_reason[k]["files"], "hours": round(by_reason[k]["hours"], 4)})
        c_report = cost.report(url)
        return {
            "files": files,
            "audio_hours": round(secs / 3600, 4),
            "kept_hours": round(float(kept["secs"]) / 3600, 4) if kept else 0.0,
            "losses": stages,
            "audio_urls": urls,
            "not_fetched": not_fetched,
            "requests": requests["n"] if requests else 0,
            "held": held["n"] if held else 0,
            "jobs": jobs,
            "latest_release": latest,
            "audit": {"ok": v.ok, "entries": v.entries},
            "cost": c_report["total"],
        }

    @app.get("/api/sources", dependencies=viewer)
    def sources() -> list[dict[str, Any]]:
        rep = cost.report(url)
        scores: dict[str, Any] = {}
        p = config.ROOT / "reports" / "discovery.json"
        if p.exists():
            scores = {s["source"].removeprefix("probe:"): s for s in json.loads(p.read_text())}
        with tx() as c:
            seeds = {r["name"]: r for r in c.execute("SELECT name, kind, seed_url FROM sources")}
        out = []
        for name, s in rep["sources"].items():
            out.append({"name": name, **s, "kind": seeds.get(name, {}).get("kind"), "seed": seeds.get(name, {}).get("seed_url"), "discovery": scores.get(name)})
        return sorted(out, key=lambda s: -s["kept_hours"])

    @app.get("/api/items", dependencies=viewer)
    def items(state: str | None = None, reason: str | None = None, source: str | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        where, args = ["true"], []
        if state:
            where.append("i.state = %s")
            args.append(state)
        if reason:
            where.append("i.reason = %s")
            args.append(reason)
        if source:
            where.append("src.name = %s")
            args.append(source)
        q = f"""FROM items i JOIN urls u ON u.id = i.url_id JOIN sources src ON src.id = i.source_id LEFT JOIN analyses a ON a.item_id = i.id WHERE {' AND '.join(where)}"""
        with tx() as c:
            total = c.execute(f"SELECT count(*) AS n {q}", args).fetchone()
            rows = c.execute(
                f"""SELECT i.id, u.url, src.name AS source, i.state, i.reason, i.licence, i.title, a.seconds, a.bandwidth_hz, a.snr_db,
                           (i.detail->>'kept_seconds')::float AS kept_seconds {q} ORDER BY i.id LIMIT %s OFFSET %s""",
                [*args, limit, offset],
            ).fetchall()
        return {"total": total["n"] if total else 0, "items": rows}

    @app.get("/api/items/{item_id}", dependencies=viewer)
    def item(item_id: int) -> dict[str, Any]:
        with tx() as c:
            r = c.execute(
                """SELECT i.*, u.url, src.name AS source FROM items i JOIN urls u ON u.id = i.url_id JOIN sources src ON src.id = i.source_id WHERE i.id = %s""",
                (item_id,),
            ).fetchone()
            if r is None:
                raise HTTPException(404, "no such item")
            a = c.execute("SELECT * FROM analyses WHERE item_id = %s", (item_id,)).fetchone()
            segs = c.execute(
                "SELECT id, idx, start_s, end_s, text, asr, cer, snr_db, clipped_ratio, tier, speaker, state, reason FROM segments WHERE item_id = %s ORDER BY idx", (item_id,)
            ).fetchall()
            reviews = c.execute("SELECT reviewer, verdict, note, at, segment_id FROM reviews WHERE item_id = %s ORDER BY at", (item_id,)).fetchall()
            blob = c.execute("SELECT deleted_at FROM blobs WHERE sha256 = %s", (r["sha256"],)).fetchone()
        return {"item": r, "analysis": a, "segments": segs, "reviews": reviews, "audio_available": bool(blob and not blob["deleted_at"])}

    def _audio_path(item_id: int, tmp: Path) -> Path:
        with tx() as c:
            r = c.execute("SELECT i.sha256, b.deleted_at FROM items i JOIN blobs b ON b.sha256 = i.sha256 WHERE i.id = %s", (item_id,)).fetchone()
        if r is None:
            raise HTTPException(404, "no such item")
        if r["deleted_at"]:
            raise HTTPException(410, "the audio was deleted after a takedown")
        return st.get_file(r["sha256"], tmp / r["sha256"])

    @app.get("/api/items/{item_id}/audio", dependencies=viewer)
    def item_audio(item_id: int, start: float = Query(0.0, ge=0), end: float | None = Query(None, gt=0)) -> Response:
        with tempfile.TemporaryDirectory() as td:
            p = _audio_path(item_id, Path(td))
            seconds = None if end is None else max(0.05, end - start)
            if seconds and seconds > 600:
                raise HTTPException(422, "at most 10 minutes per request")
            y = dec.resample(p, 16000, start, seconds)
            out = Path(td) / "out.wav"
            dec.encode(y, 16000, out, codec="wav")
            return Response(out.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/items/{item_id}/spectrogram", dependencies=viewer)
    def spectrogram(item_id: int, width: int = Query(600, ge=50, le=2000), bands: int = Query(64, ge=16, le=128), seconds: float = Query(120.0, gt=0, le=600)) -> dict[str, Any]:
        """A log-frequency spectrogram (dB, 0 to 1 scaled) and the peak envelope, for drawing."""
        from scipy.signal import stft

        with tempfile.TemporaryDirectory() as td:
            p = _audio_path(item_id, Path(td))
            x = dec.resample(p, 16000, 0.0, seconds)
        if not len(x):
            return {"bands": [], "frames": [], "seconds": 0.0}
        f, _, z = stft(x, fs=16000, nperseg=512, noverlap=256, boundary=None)
        power_db = 10 * np.log10(np.abs(z) ** 2 + 1e-10)
        # mel-spaced bands, each read off the FFT bins by interpolation, so no band is empty
        mel = np.linspace(2595 * np.log10(1 + 60 / 700), 2595 * np.log10(1 + 8000 / 700), bands)
        centres = 700 * (10 ** (mel / 2595) - 1)
        rows = np.stack([np.interp(centres, f, power_db[:, j]) for j in range(power_db.shape[1])], axis=1)
        cols = np.array_split(np.arange(rows.shape[1]), min(width, rows.shape[1]))
        db_ = np.stack([rows[:, c].mean(axis=1) for c in cols], axis=1)
        top = db_.max()
        scaled = np.clip((db_ - (top - 80)) / 80, 0, 1)
        env_cols = np.array_split(np.abs(x), width)
        return {
            "seconds": len(x) / 16000,
            "bands": [round(float(v)) for v in centres],
            "frames": [[round(float(v), 3) for v in col] for col in scaled.T],
            "peaks": [round(float(c.max()), 3) if len(c) else 0.0 for c in env_cols],
        }

    @app.get("/api/review/queue", dependencies=viewer)
    def queue(kind: str = Query("held", pattern="^(held|kept|rejected)$"), n: int = Query(20, ge=1, le=100), seed: int = 0) -> list[dict[str, Any]]:
        """Held files first; then random spot checks of decisions, stratified by reason."""
        with tx() as c:
            if kind == "held":
                rows = c.execute("SELECT i.id, u.url, i.state, i.reason, i.detail FROM items i JOIN urls u ON u.id = i.url_id WHERE i.state = 'held' ORDER BY i.id LIMIT %s", (n,)).fetchall()
            else:
                rows = c.execute(
                    """SELECT i.id, u.url, i.state, i.reason, i.detail FROM items i JOIN urls u ON u.id = i.url_id
                       WHERE i.state = %s AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.item_id = i.id) AND i.sha256 IS NOT NULL
                       AND (i.reason IS NULL OR i.reason NOT IN ('licence', 'synthetic'))""",
                    (kind,),
                ).fetchall()
                rng = random.Random(seed)
                by: dict[str, list[dict[str, Any]]] = {}
                for r in rows:
                    by.setdefault(r["reason"] or "kept", []).append(r)
                picked: list[dict[str, Any]] = []
                while len(picked) < n and any(by.values()):
                    for k in sorted(by):
                        if by[k] and len(picked) < n:
                            picked.append(by[k].pop(rng.randrange(len(by[k]))))
                rows = picked
        return rows

    @app.post("/api/reviews")
    def review(body: ReviewBody, who: str = Depends(require("reviewer"))) -> dict[str, Any]:
        if (body.item_id is None) == (body.segment_id is None):
            raise HTTPException(422, "give item_id or segment_id")
        with tx() as c:
            item_id = body.item_id
            if body.segment_id is not None:
                r = c.execute("SELECT item_id FROM segments WHERE id = %s", (body.segment_id,)).fetchone()
                if r is None:
                    raise HTTPException(404, "no such segment")
                item_id = r["item_id"]
            elif c.execute("SELECT 1 FROM items WHERE id = %s", (item_id,)).fetchone() is None:
                raise HTTPException(404, "no such item")
            r2 = c.execute(
                "INSERT INTO reviews (item_id, segment_id, reviewer, verdict, note) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (item_id, body.segment_id, who, body.verdict, body.note),
            ).fetchone()
        return {"id": r2["id"] if r2 else None}

    @app.get("/api/reviews/summary", dependencies=viewer)
    def review_summary() -> list[dict[str, Any]]:
        """How often reviewers agree with each kind of decision, with a 95% Wilson interval."""
        with tx() as c:
            rows = c.execute(
                """SELECT coalesce(i.reason, i.state) AS decision, count(*) AS n, count(*) FILTER (WHERE r.verdict = 'agree') AS agree
                   FROM reviews r JOIN items i ON i.id = r.item_id GROUP BY 1 ORDER BY 1"""
            ).fetchall()
        return [{**r, "agree_interval": wilson(r["agree"], r["n"])} for r in rows]

    @app.post("/api/items/{item_id}/resolve")
    def resolve(item_id: int, body: ResolveBody, who: str = Depends(require("reviewer"))) -> dict[str, Any]:
        """A person decides a held file."""
        with tx() as c:
            r = c.execute("SELECT state FROM items WHERE id = %s FOR UPDATE", (item_id,)).fetchone()
            if r is None:
                raise HTTPException(404, "no such item")
            if r["state"] != "held":
                raise HTTPException(409, f"item is {r['state']}, not held")
            state, reason = ("kept", None) if body.decision == "keep" else ("rejected", "synthetic")
            c.execute(
                "UPDATE items SET state = %s, reason = %s, detail = detail || %s WHERE id = %s",
                (state, reason, json.dumps({"resolved_by": who, "resolution_note": body.note}), item_id),
            )
            audit.append(c, who, "review.resolve", {"item_id": item_id, "decision": body.decision, "note": body.note})
        return {"item_id": item_id, "state": state}

    @app.get("/api/releases", dependencies=viewer)
    def releases() -> list[dict[str, Any]]:
        with tx() as c:
            return c.execute("SELECT name, created_at, manifest_sha256, stats, parent FROM releases ORDER BY id DESC").fetchall()

    @app.get("/api/releases/{name}/files/{fname}", dependencies=viewer)
    def release_file(name: str, fname: str) -> FileResponse:
        if fname not in ("CARD.md", "AI_ACT_SUMMARY.md", "ATTRIBUTION.md", "ai_act_summary.json"):
            raise HTTPException(404, "no such file")
        p = config.DATA_DIR / "releases" / name / fname
        if not p.exists() or p.parent.parent != config.DATA_DIR / "releases":
            raise HTTPException(404, "no such release file")
        return FileResponse(p)

    @app.get("/api/releases/{a}/diff/{b}", dependencies=viewer)
    def release_diff(a: str, b: str) -> dict[str, Any]:
        try:
            return release.diff(a, b, url)
        except LookupError as e:
            raise HTTPException(404, f"no release {e}") from e

    @app.post("/api/takedowns/preview", dependencies=viewer)
    def td_preview(body: TakedownBody) -> dict[str, Any]:
        return takedown.preview(body.kind, body.value, url)

    @app.post("/api/takedowns")
    def td_execute(body: TakedownBody, who: str = Depends(require("admin"))) -> dict[str, Any]:
        tid = takedown.request(body.kind, body.value, body.reason, who, url)
        return {"id": tid, **takedown.execute(tid, st, who, url)}

    @app.get("/api/takedowns", dependencies=viewer)
    def td_list() -> list[dict[str, Any]]:
        with tx() as c:
            return c.execute("SELECT * FROM takedowns ORDER BY id DESC").fetchall()

    web = Path(os.environ.get("SCR_WEB_DIR", config.ROOT / "web" / "dist"))
    if (web / "index.html").exists():
        _mount_web(app, web)
    return app


def _mount_web(app: FastAPI, web: Path) -> None:
    from fastapi.staticfiles import StaticFiles

    if (web / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")
    root = web.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = (root / path).resolve()
        if path and f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html")


def app_from_env() -> FastAPI:  # pragma: no cover - wiring
    return create_app()

