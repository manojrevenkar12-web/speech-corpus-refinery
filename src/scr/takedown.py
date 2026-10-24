"""Takedowns: a rights holder or a speaker asks for their recordings to go. One request
withdraws everything derived from them, deletes the stored audio, lists the releases that
contained it (whoever trained on those must be told), and keeps them out of the future:
the URL or domain is never crawled again, the recording's fingerprint rejects re-uploads, and a
speaker's voice embedding rejects new segments in that voice."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import numpy as np

from . import audit, db
from .store import Store

KINDS = ("url", "domain", "speaker", "item")


def request(kind: str, value: str, reason: str, by: str, url: str | None = None) -> int:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not value.strip() or not reason.strip():
        raise ValueError("value and reason are required")
    with db.tx(url) as c:
        r = c.execute(
            "INSERT INTO takedowns (kind, value, reason, requested_by) VALUES (%s, %s, %s, %s) RETURNING id",
            (kind, value.strip(), reason.strip(), by),
        ).fetchone()
        assert r is not None
        audit.append(c, by, "takedown.request", {"id": r["id"], "kind": kind, "value": value, "reason": reason})
        return int(r["id"])


def preview(kind: str, value: str, url: str | None = None) -> dict[str, Any]:
    with db.tx(url) as c:
        items, segs = _resolve(c, kind, value)
        rel = _releases(c, segs)
        hours = c.execute(
            "SELECT coalesce(sum(end_s - start_s), 0) / 3600 AS h FROM segments WHERE id = ANY(%s) AND state = 'kept'", (segs,)
        ).fetchone()
    return {"items": len(items), "segments": len(segs), "kept_hours": round(float(hours["h"]) if hours else 0.0, 4), "releases": rel}


def _resolve(c: Any, kind: str, value: str) -> tuple[list[int], list[int]]:
    if kind == "url":
        rows = c.execute(
            "SELECT i.id FROM items i JOIN urls u ON u.id = i.url_id WHERE u.url = %s OR i.meta->>'final_url' = %s", (value, value)
        ).fetchall()
    elif kind == "domain":
        d = value.lower().lstrip(".")
        rows = [
            r
            for r in c.execute("SELECT i.id, u.url FROM items i JOIN urls u ON u.id = i.url_id")
            if (h := (urlsplit(r["url"]).hostname or "")) == d or h.endswith("." + d)
        ]
    elif kind == "item":
        rows = c.execute("SELECT id FROM items WHERE id = %s", (int(value),)).fetchall()
    else:  # speaker: only that voice's segments go, the rest of the recording stays
        segs = [r["id"] for r in c.execute("SELECT id FROM segments WHERE speaker = %s", (value,))]
        return [], segs
    items = [int(r["id"]) for r in rows]
    segs = [int(r["id"]) for r in c.execute("SELECT id FROM segments WHERE item_id = ANY(%s)", (items,))] if items else []
    return items, segs


def _releases(c: Any, segs: list[int]) -> list[str]:
    if not segs:
        return []
    return [
        r["name"]
        for r in c.execute(
            "SELECT DISTINCT r.name, r.id FROM release_segments rs JOIN releases r ON r.id = rs.release_id WHERE rs.segment_id = ANY(%s) ORDER BY r.id",
            (segs,),
        )
    ]


def execute(takedown_id: int, store: Store, by: str, url: str | None = None) -> dict[str, Any]:
    with db.tx(url) as c:
        t = c.execute("SELECT * FROM takedowns WHERE id = %s FOR UPDATE", (takedown_id,)).fetchone()
        if t is None:
            raise LookupError(f"takedown {takedown_id}")
        if t["executed_at"]:
            return dict(t["affected"])
        items, segs = _resolve(c, t["kind"], t["value"])
        releases = _releases(c, segs)
        tag = f"takedown:{takedown_id}"
        if segs:
            c.execute("UPDATE segments SET state = 'withdrawn', reason = %s WHERE id = ANY(%s)", (tag, segs))
        deleted: list[str] = []
        if items:
            c.execute("UPDATE items SET state = 'withdrawn', reason = %s WHERE id = ANY(%s)", (tag, items))
            c.execute("UPDATE fp_items SET blocked_by = %s WHERE item_id = ANY(%s)", (takedown_id, items))
            for r in c.execute(
                """SELECT DISTINCT i.sha256 FROM items i WHERE i.id = ANY(%s)
                   AND NOT EXISTS (SELECT 1 FROM items o WHERE o.sha256 = i.sha256 AND o.state <> 'withdrawn' AND o.id <> ALL(%s))""",
                (items, items),
            ).fetchall():
                deleted.append(r["sha256"])
        if t["kind"] in ("url", "domain"):
            c.execute(
                "INSERT INTO do_not_crawl (pattern, kind, takedown_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (t["value"].lower() if t["kind"] == "domain" else t["value"], t["kind"], takedown_id),
            )
        if t["kind"] == "speaker" and segs:
            emb = np.array([r["embedding"] for r in c.execute("SELECT embedding FROM segments WHERE id = ANY(%s)", (segs,))], np.float32)
            centroid = emb.mean(axis=0)
            centroid /= np.linalg.norm(centroid) + 1e-9
            c.execute("INSERT INTO blocked_speakers (centroid, takedown_id) VALUES (%s, %s)", ([float(v) for v in centroid], takedown_id))
        affected = {"items": len(items), "segments": len(segs), "releases": releases, "blobs_deleted": len(deleted)}
        c.execute("UPDATE takedowns SET executed_at = now(), affected = %s WHERE id = %s", (json.dumps(affected), takedown_id))
        audit.append(c, by, "takedown.execute", {"id": takedown_id, **affected})
    for sha in deleted:  # after commit: a crash here leaves a withdrawn item with its blob, never the reverse
        store.delete(sha)
        with db.tx(url) as c:
            c.execute("UPDATE blobs SET deleted_at = now(), deleted_reason = %s WHERE sha256 = %s", (f"takedown:{takedown_id}", sha))
    return affected
