"""A hash-chained audit trail in PostgreSQL (append-only by trigger): crawl runs, decisions
batches, releases, takedowns. Each entry hashes the previous one, so an edit anywhere breaks
every later link."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import psycopg

GENESIS = "0" * 64


def _hash(prev: str, actor: str, event: str, data: dict[str, Any]) -> str:
    blob = json.dumps({"prev": prev, "actor": actor, "event": event, "data": data}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def append(c: psycopg.Connection[Any], actor: str, event: str, data: dict[str, Any]) -> str:
    c.execute("LOCK TABLE audit IN SHARE ROW EXCLUSIVE MODE")
    row = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else GENESIS
    h = _hash(prev, actor, event, data)
    c.execute(
        "INSERT INTO audit (actor, event, data, prev, hash) VALUES (%s, %s, %s, %s, %s)",
        (actor, event, json.dumps(data, default=str), prev, h),
    )
    return h


@dataclass
class Verification:
    ok: bool
    entries: int
    broken_at: int | None = None


def verify(c: psycopg.Connection[Any]) -> Verification:
    prev, n = GENESIS, 0
    for r in c.execute("SELECT seq, actor, event, data, prev, hash FROM audit ORDER BY seq"):
        n += 1
        if r["prev"] != prev or _hash(prev, r["actor"], r["event"], r["data"]) != r["hash"]:
            return Verification(False, n, r["seq"])
        prev = r["hash"]
    return Verification(True, n)
