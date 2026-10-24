"""The crawler: a PostgreSQL frontier, one lease per host, rights checks before every request.

Politeness and correctness live in the database, so any number of crawler processes can run:
a worker leases a *host* (`FOR UPDATE SKIP LOCKED`), fetches one due URL from it, and releases
the host with `next_allowed_at` pushed by the larger of our minimum delay and the site's
Crawl-delay. Before a request:

1. blocked domain (config/rights.yaml): never contacted at all;
2. robots.txt (RFC 9309), refreshed every 24 h; 5xx means stay out;
3. TDMRep `/.well-known/tdmrep.json` rules for the path;
then, on the response, the `tdm-reservation` header (the body is not read) and, for HTML, the
`<meta name="tdm-reservation">` tag. Retries honour Retry-After and back off; redirects are
followed by hand so each hop passes the same checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .. import audit, config, db
from ..rights import licence as lic
from ..rights import robots as rb
from ..rights import tdmrep
from ..store import Store
from ..store import default as default_store
from . import connectors
from .http import client as make_client

MAX_DEPTH = 4


@dataclass
class Stats:
    fetched: int = 0
    audio: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    failed: int = 0
    retried: int = 0
    bytes: int = 0

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1


class Crawler:
    def __init__(
        self,
        url: str | None = None,
        store: Store | None = None,
        owner: str | None = None,
        world: str | None = None,
        audio_cap: int | None = None,
    ) -> None:
        self.db = url
        self.audio_cap = audio_cap  # discovery: stop queueing audio for a source after this many files
        self.store = store or default_store()
        self.s = config.settings()["crawl"]
        self.rights = config.rights()
        self.owner = owner or f"{socket.gethostname()}:{os.getpid()}"
        self.world = world
        self.stats = Stats()
        self._lock = threading.Lock()

    # ------------------------------------------------------------ frontier

    def seed(self, name: str, kind: str, url: str) -> int:
        with db.tx(self.db) as c:
            row = c.execute(
                "INSERT INTO sources (name, kind, seed_url) VALUES (%s, %s, %s) ON CONFLICT (name) DO UPDATE SET seed_url = EXCLUDED.seed_url RETURNING id",
                (name, kind, url),
            ).fetchone()
            assert row is not None
            sid = int(row["id"])
            ukind, parser = {
                "librivox": ("api", "librivox"),
                "internet_archive": ("api", "ia_search"),
                "rss": ("feed", "rss"),
                "html_index": ("page", "html"),
            }[kind]
            self._enqueue(c, url, ukind, sid, None, 0, {"parser": parser})
        return sid

    def _enqueue(self, c: Any, url: str, kind: str, source_id: int | None, parent: int | None, depth: int, meta: dict[str, Any]) -> None:
        host = urlsplit(url).netloc.lower()
        c.execute("INSERT INTO hosts (host) VALUES (%s) ON CONFLICT DO NOTHING", (host,))
        hostname = urlsplit(url).hostname or ""
        state, reason = ("skipped", "blocked_domain") if lic.blocked_domain(hostname, self.rights) else ("queued", None)
        if kind == "audio" and self.audio_cap is not None and source_id is not None:
            n = c.execute("SELECT count(*) AS n FROM urls WHERE source_id = %s AND kind = 'audio'", (source_id,)).fetchone()
            if n and n["n"] >= self.audio_cap:
                return
        if (
            state == "queued"
            and c.execute(
                """SELECT 1 FROM do_not_crawl WHERE (kind = 'url' AND %s LIKE pattern || '%%')
               OR (kind = 'domain' AND (%s = pattern OR %s LIKE '%%.' || pattern)) LIMIT 1""",
                (url, hostname, hostname),
            ).fetchone()
        ):
            state, reason = "skipped", "takedown"
        c.execute(
            """INSERT INTO urls (url, host, source_id, kind, state, reason, discovered_from, depth, meta)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING""",
            (url, host, source_id, kind, state, reason, parent, depth, json.dumps(meta)),
        )

    def _lease_host(self) -> str | None:
        with db.tx(self.db) as c:
            row = c.execute(
                """UPDATE hosts SET lease_until = now() + interval '120 seconds', lease_owner = %s
                   WHERE host = (
                     SELECT h.host FROM hosts h
                     WHERE h.next_allowed_at <= now() AND (h.lease_until IS NULL OR h.lease_until < now())
                       AND EXISTS (SELECT 1 FROM urls u WHERE u.host = h.host AND u.state = 'queued' AND u.next_try_at <= now())
                     ORDER BY h.next_allowed_at LIMIT 1 FOR UPDATE SKIP LOCKED)
                   RETURNING host""",
                (self.owner,),
            ).fetchone()
            return str(row["host"]) if row else None

    def _release(self, host: str, delay: float) -> None:
        with db.tx(self.db) as c:
            c.execute(
                "UPDATE hosts SET lease_until = NULL, lease_owner = NULL, next_allowed_at = now() + make_interval(secs => %s) WHERE host = %s AND lease_owner = %s",
                (delay, host, self.owner),
            )

    def pending(self) -> tuple[int, float | None]:
        with db.tx(self.db) as c:
            r = c.execute(
                "SELECT count(*) AS n, extract(epoch FROM min(next_try_at) - now()) AS wait FROM urls WHERE state = 'queued'"
            ).fetchone()
            assert r is not None
            return int(r["n"]), (float(r["wait"]) if r["wait"] is not None else None)

    # ------------------------------------------------------------ run

    def run(self, workers: int = 4, deadline: float = 900.0) -> Stats:
        stop = time.monotonic() + deadline
        with db.tx(self.db) as c:
            audit.append(c, self.owner, "crawl.start", {"workers": workers})

        def loop() -> None:
            http = make_client(self.s["user_agent"], float(self.s["timeout_seconds"]), self.world)
            try:
                while time.monotonic() < stop:
                    host = self._lease_host()
                    if host is None:
                        n, wait = self.pending()
                        if n == 0:
                            return
                        time.sleep(min(max(wait or 0.2, 0.05), 1.0))
                        continue
                    delay = float(self.s["min_delay_seconds"])
                    try:
                        delay = self._visit(http, host)
                    finally:
                        self._release(host, delay)
            finally:
                http.close()

        threads = [threading.Thread(target=loop, daemon=True) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with db.tx(self.db) as c:
            audit.append(c, self.owner, "crawl.end", self.stats.__dict__)
        return self.stats

    # ------------------------------------------------------------ one host visit

    def _host_rules(self, http: httpx.Client, host: str) -> tuple[rb.Robots, list[dict[str, Any]], float]:
        with db.tx(self.db) as c:
            h = c.execute("SELECT * FROM hosts WHERE host = %s", (host,)).fetchone()
        assert h is not None
        now = datetime.now(UTC)
        fresh = h["robots_fetched_at"] and (now - h["robots_fetched_at"]).total_seconds() < float(self.s["robots_cache_seconds"])
        scheme = "http" if host.endswith(".example") else "https"
        if fresh:
            robots = rb.from_response(h["robots_status"], h["robots_txt"] or "")
            rules = h["tdmrep"] or []
        else:
            status, text = self._get_text(http, f"{scheme}://{host}/robots.txt")
            robots = rb.from_response(status, text)
            rules = []
            if self.rights["respect"].get("tdmrep"):
                ts, tt = self._get_text(http, f"{scheme}://{host}/.well-known/tdmrep.json")
                rules = tdmrep.parse_file(tt) if ts == 200 else []
            delay = robots.crawl_delay(self.s["robots_token"])
            with db.tx(self.db) as c:
                c.execute(
                    """UPDATE hosts SET robots_status = %s, robots_txt = %s, robots_fetched_at = now(),
                       tdmrep = %s, tdmrep_fetched_at = now(), crawl_delay = %s WHERE host = %s""",
                    (status, text[:100_000], json.dumps(rules), delay, host),
                )
        delay = max(float(self.s["min_delay_seconds"]), robots.crawl_delay(self.s["robots_token"]) or 0.0)
        return robots, rules, delay

    def _get_text(self, http: httpx.Client, url: str) -> tuple[int | None, str]:
        """For robots.txt and tdmrep.json: follow up to five redirects (RFC 9309 2.3.1.2)."""
        for _ in range(5):
            try:
                r = http.get(url)
            except httpx.HTTPError:
                return None, ""
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            return r.status_code, r.text if r.status_code == 200 else ""
        return None, ""

    def _visit(self, http: httpx.Client, host: str) -> float:
        robots, rules, delay = self._host_rules(http, host)
        with db.tx(self.db) as c:
            u = c.execute(
                "SELECT * FROM urls WHERE host = %s AND state = 'queued' AND next_try_at <= now() ORDER BY depth, id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (host,),
            ).fetchone()
            if u is None:
                return delay
            c.execute("UPDATE urls SET attempts = attempts + 1, updated_at = now() WHERE id = %s", (u["id"],))
        try:
            self._fetch(http, u, robots, rules)
        except Exception as e:  # never leave a URL leased because of a bug in one handler
            self._finish(u, "failed", f"error: {type(e).__name__}: {str(e)[:200]}")
        return delay

    def _finish(self, u: dict[str, Any], state: str, reason: str | None, **cols: Any) -> None:
        sets = ", ".join(f"{k} = %s" for k in cols)
        with db.tx(self.db) as c:
            c.execute(
                f"UPDATE urls SET state = %s, reason = %s, updated_at = now(){', ' + sets if sets else ''} WHERE id = %s",
                (state, reason, *cols.values(), u["id"]),
            )
        if state == "skipped":
            with self._lock:
                self.stats.skip(reason or "")
        elif state == "failed":
            with self._lock:
                self.stats.failed += 1

    def _retry(self, u: dict[str, Any], why: str, retry_after: float | None = None) -> None:
        backoff = self.s["backoff_seconds"]
        if u["attempts"] + 1 >= int(self.s["max_attempts"]):
            self._finish(u, "failed", f"gave up: {why}")
            return
        wait = retry_after if retry_after is not None else float(backoff[min(u["attempts"], len(backoff) - 1)])
        with db.tx(self.db) as c:
            c.execute("UPDATE urls SET next_try_at = now() + make_interval(secs => %s), reason = %s WHERE id = %s", (wait, why, u["id"]))
        with self._lock:
            self.stats.retried += 1

    def _record(
        self,
        u: dict[str, Any],
        status: int | None,
        headers: dict[str, str],
        error: str = "",
        sha: str | None = None,
        size: int = 0,
        secs: float = 0.0,
    ) -> None:
        with db.tx(self.db) as c:
            c.execute(
                "INSERT INTO fetches (url_id, status, bytes, sha256, content_type, headers, error, seconds) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (u["id"], status, size, sha, headers.get("content-type"), json.dumps(headers), error[:500], secs),
            )

    def _fetch(self, http: httpx.Client, u: dict[str, Any], robots: rb.Robots, rules: list[dict[str, Any]]) -> None:
        url, token = u["url"], self.s["robots_token"]
        if self.rights["respect"].get("robots_txt") and not robots.allowed(url, token):
            self._finish(u, "skipped", "robots")
            return
        reservation = tdmrep.from_file(rules, url)
        if reservation:
            self._finish(u, "skipped", "tdm", meta=json.dumps({**u["meta"], "tdm": reservation.where}))
            return
        headers = {}
        if u["etag"]:
            headers["If-None-Match"] = u["etag"]
        t0 = time.monotonic()
        try:
            with http.stream("GET", url, headers=headers) as r:
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                if r.status_code in (301, 302, 303, 307, 308) and hdrs.get("location"):
                    # each hop goes back to the frontier: it gets the same rights checks and waits its turn
                    self._record(u, r.status_code, hdrs)
                    hops = int(u["meta"].get("redirect_hops", 0)) + 1
                    if hops > int(self.s["max_redirects"]):
                        self._finish(u, "failed", "too many redirects")
                        return
                    nxt = urljoin(url, hdrs["location"])
                    with db.tx(self.db) as c:
                        self._enqueue(c, nxt, u["kind"], u["source_id"], u["id"], u["depth"], {**u["meta"], "redirect_hops": hops})
                    self._finish(u, "done", "redirected")
                    return
                if r.status_code == 304:
                    self._record(u, 304, hdrs)
                    self._finish(u, "done", "not modified")
                    return
                if r.status_code == 429 or r.status_code >= 500:
                    self._record(u, r.status_code, hdrs)
                    self._retry(u, f"HTTP {r.status_code}", _retry_after(hdrs.get("retry-after")))
                    return
                if r.status_code >= 400:
                    self._record(u, r.status_code, hdrs)
                    self._finish(u, "failed", f"HTTP {r.status_code}")
                    return
                reservation = tdmrep.from_headers(hdrs, reservation)
                if reservation:
                    self._record(u, r.status_code, hdrs, "tdm-reservation header: body not read")
                    self._finish(u, "skipped", "tdm", meta=json.dumps({**u["meta"], "tdm": reservation.where}))
                    return
                declared = hdrs.get("content-length")
                if declared and int(declared) > int(self.s["max_bytes"]):
                    self._record(u, r.status_code, hdrs, "too large")
                    self._finish(u, "failed", "too large")
                    return
                tmp, sha, size = self._spool(r)
                secs = time.monotonic() - t0
        except httpx.TimeoutException:
            self._record(u, None, {}, "timeout", secs=time.monotonic() - t0)
            self._retry(u, "timeout")
            return
        except (httpx.RemoteProtocolError, httpx.ReadError) as e:
            self._record(u, None, {}, f"incomplete body: {e}", secs=time.monotonic() - t0)
            self._retry(u, "incomplete body")
            return
        except httpx.HTTPError as e:
            self._record(u, None, {}, str(e), secs=time.monotonic() - t0)
            self._retry(u, type(e).__name__)
            return
        except _TooLarge:
            self._record(u, None, {}, "too large")
            self._finish(u, "failed", "too large")
            return
        try:
            self._record(u, r.status_code, hdrs, sha=sha, size=size, secs=secs)
            with self._lock:
                self.stats.fetched += 1
                self.stats.bytes += size
            self._handle(u, url, hdrs, tmp, sha, size)
        finally:
            tmp.unlink(missing_ok=True)

    def _spool(self, r: httpx.Response) -> tuple[Path, str, int]:
        h = hashlib.sha256()
        size = 0
        fd, name = tempfile.mkstemp(prefix="scr-")
        cap = int(self.s["max_bytes"])
        with os.fdopen(fd, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                size += len(chunk)
                if size > cap:
                    raise _TooLarge()
                h.update(chunk)
                f.write(chunk)
        declared = r.headers.get("content-length")
        if declared and int(declared) != size:
            Path(name).unlink(missing_ok=True)
            raise httpx.RemoteProtocolError(f"got {size} of {declared} bytes")
        return Path(name), h.hexdigest(), size

    # ------------------------------------------------------------ what a response means

    def _handle(self, u: dict[str, Any], url: str, hdrs: dict[str, str], tmp: Path, sha: str, size: int) -> None:
        kind = u["kind"]
        if kind in ("audio", "text"):
            self.store.put_file(sha, tmp)
            with db.tx(self.db) as c:
                c.execute(
                    "INSERT INTO blobs (sha256, bytes, content_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (sha, size, hdrs.get("content-type")),
                )
                if kind == "text":
                    c.execute(
                        "UPDATE urls SET state = 'done', reason = NULL, etag = %s, meta = meta || %s WHERE id = %s",
                        (hdrs.get("etag"), json.dumps({"sha256": sha}), u["id"]),
                    )
                    return
                m = u["meta"]
                spdx = lic.normalise(m.get("licence"))
                row = c.execute(
                    """INSERT INTO items (url_id, source_id, sha256, licence, licence_evidence, attribution, synthetic_declared, title, text_url, meta)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url_id) DO UPDATE SET sha256 = EXCLUDED.sha256 RETURNING id""",
                    (
                        u["id"],
                        u["source_id"],
                        sha,
                        spdx,
                        m.get("licence_evidence", ""),
                        m.get("attribution", ""),
                        bool(m.get("synthetic_declared")),
                        m.get("title", ""),
                        m.get("text_url"),
                        json.dumps({"language": m.get("language"), "transcript": m.get("transcript", ""), "final_url": url}),
                    ),
                ).fetchone()
                assert row is not None
                c.execute("INSERT INTO jobs (kind, ref) VALUES ('analyse', %s) ON CONFLICT DO NOTHING", (row["id"],))
                c.execute("UPDATE urls SET state = 'done', reason = NULL, etag = %s WHERE id = %s", (hdrs.get("etag"), u["id"]))
                if m.get("text_url"):
                    self._enqueue(c, m["text_url"], "text", u["source_id"], u["id"], u["depth"] + 1, {})
            with self._lock:
                self.stats.audio += 1
            return
        body = tmp.read_bytes()
        if kind == "page":
            res = tdmrep.from_html(body.decode("utf-8", errors="replace"), tdmrep.Reservation(None))
            if res:
                self._finish(u, "skipped", "tdm", meta=json.dumps({**u["meta"], "tdm": "meta"}))
                return
        parser = u["meta"].get("parser") or connectors.parser_for(kind, url)
        found = connectors.PARSERS[parser](url, body) if parser in connectors.PARSERS else []
        with db.tx(self.db) as c:
            for f in found:
                if f.kind != "audio" and u["depth"] + 1 > MAX_DEPTH:
                    continue
                meta = dict(f.meta)
                if f.kind != "audio":
                    meta["parser"] = f.parser or connectors.parser_for(f.kind, f.url)
                self._enqueue(c, f.url, f.kind, u["source_id"], u["id"], u["depth"] + 1, meta)
            c.execute(
                "UPDATE urls SET state = 'done', reason = NULL, etag = %s, meta = meta || %s WHERE id = %s",
                (hdrs.get("etag"), json.dumps({"found": len(found)}), u["id"]),
            )


class _TooLarge(Exception):
    pass


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            return None
