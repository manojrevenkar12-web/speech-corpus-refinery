"""A work queue in PostgreSQL. Workers lease jobs with `FOR UPDATE SKIP LOCKED`, extend the lease
while they work, and finish or retry them. A worker that dies loses its lease and another one
picks the job up; handlers write their results in one transaction, so a job that runs twice
leaves one result."""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import db

LEASE_SECONDS = 300
MAX_ATTEMPTS = 3


@dataclass
class Job:
    id: int
    kind: str
    ref: int
    attempts: int


def owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def lease(kinds: list[str], who: str, url: str | None = None) -> Job | None:
    with db.tx(url) as c:
        r = c.execute(
            """UPDATE jobs SET state = 'running', attempts = attempts + 1, lease_owner = %s,
                      lease_until = now() + make_interval(secs => %s)
               WHERE id = (
                 SELECT id FROM jobs
                 WHERE kind = ANY(%s) AND not_before <= now()
                   AND (state = 'queued' OR (state = 'running' AND lease_until < now()))
                 ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
               RETURNING id, kind, ref, attempts""",
            (who, LEASE_SECONDS, kinds),
        ).fetchone()
        return Job(r["id"], r["kind"], r["ref"], r["attempts"]) if r else None


def extend(job: Job, who: str, url: str | None = None) -> bool:
    with db.tx(url) as c:
        r = c.execute(
            "UPDATE jobs SET lease_until = now() + make_interval(secs => %s) WHERE id = %s AND lease_owner = %s AND state = 'running' RETURNING id",
            (LEASE_SECONDS, job.id, who),
        ).fetchone()
        return r is not None


def done(job: Job, who: str, url: str | None = None) -> None:
    with db.tx(url) as c:
        c.execute(
            "UPDATE jobs SET state = 'done', finished_at = now(), last_error = NULL WHERE id = %s AND lease_owner = %s", (job.id, who)
        )


def failed(job: Job, who: str, error: str, url: str | None = None) -> bool:
    """Back to the queue with a delay, or dead after MAX_ATTEMPTS. Returns True when dead."""
    dead = job.attempts >= MAX_ATTEMPTS
    with db.tx(url) as c:
        c.execute(
            """UPDATE jobs SET state = %s, last_error = %s, lease_owner = NULL, lease_until = NULL,
                      not_before = now() + make_interval(secs => %s) WHERE id = %s AND lease_owner = %s""",
            ("dead" if dead else "queued", error[:1000], 5 * job.attempts, job.id, who),
        )
    return dead


def retry_due_within(kinds: list[str], seconds: float, url: str | None = None) -> bool:
    with db.tx(url) as c:
        r = c.execute(
            "SELECT 1 FROM jobs WHERE kind = ANY(%s) AND state = 'queued' AND not_before <= now() + make_interval(secs => %s) LIMIT 1",
            (kinds, seconds),
        ).fetchone()
        return r is not None


def counts(url: str | None = None) -> dict[str, int]:
    with db.tx(url) as c:
        return {f"{r['kind']}:{r['state']}": r["n"] for r in c.execute("SELECT kind, state, count(*) AS n FROM jobs GROUP BY kind, state")}


def work(
    kinds: list[str],
    handler: Callable[[Job], object],
    on_dead: Callable[[Job, str], None] | None = None,
    url: str | None = None,
    stop_when_empty: bool = True,
    max_jobs: int | None = None,
    retry_wait_seconds: float = 30.0,
) -> int:
    """Process jobs until none are due and no retry is due within `retry_wait_seconds` (a job
    backing off after a failure is waited for, not left behind). Returns the number handled."""
    who = owner()
    n = 0
    while max_jobs is None or n < max_jobs:
        job = lease(kinds, who, url)
        if job is None:
            if stop_when_empty and not retry_due_within(kinds, retry_wait_seconds, url):
                return n
            threading.Event().wait(1.0)
            continue
        stop = threading.Event()

        def beat(j: Job = job, ev: threading.Event = stop) -> None:
            while not ev.wait(LEASE_SECONDS / 5):
                extend(j, who, url)

        t = threading.Thread(target=beat, daemon=True)
        t.start()
        try:
            handler(job)
            done(job, who, url)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if failed(job, who, msg, url) and on_dead:
                on_dead(job, msg)
        finally:
            stop.set()
        n += 1
    return n


def stats_row(c: Any) -> dict[str, Any]:
    return dict(
        c.execute(
            "SELECT count(*) FILTER (WHERE state = 'queued') AS queued, count(*) FILTER (WHERE state = 'dead') AS dead FROM jobs"
        ).fetchone()
        or {}
    )
