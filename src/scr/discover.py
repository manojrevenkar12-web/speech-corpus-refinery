"""Scoring a new source before committing to it: crawl a small sample, process it exactly as a
full ingest would, and report what a full ingest would yield and cost.

The report answers the questions a data lead asks: may we use it (robots.txt, TDM
reservations, licences), is it speech we want (decisions by reason), is it new (duplicates of
what we hold), and what will a usable hour cost."""

from __future__ import annotations

from typing import Any

from . import cost, db, jobs, process
from .crawl.crawler import Crawler
from .store import Store


def probe(
    name: str, kind: str, seed: str, store: Store, sample: int = 10, url: str | None = None, world: str | None = None, workers: int = 1
) -> dict[str, Any]:
    source = f"probe:{name}"
    cr = Crawler(url, store=store, world=world, audio_cap=sample)
    sid = cr.seed(source, kind, seed)
    cr.run(workers=2, deadline=600)
    with db.tx(url) as c:
        ids = [
            r["id"]
            for r in c.execute(
                "SELECT i.id FROM items i JOIN jobs j ON j.ref = i.id AND j.kind = 'analyse' WHERE i.source_id = %s AND j.state = 'queued'",
                (sid,),
            )
        ]
    for item_id in ids:
        process.analyse(item_id, store, url)
        with db.tx(url) as c:
            c.execute("UPDATE jobs SET state = 'done', finished_at = now() WHERE kind = 'analyse' AND ref = %s", (item_id,))
    return report(source, url)


def report(source: str, url: str | None = None) -> dict[str, Any]:
    with db.tx(url) as c:
        s = c.execute("SELECT id FROM sources WHERE name = %s", (source,)).fetchone()
        if s is None:
            raise LookupError(source)
        sid = s["id"]
        urls = {
            f"{r['state']}:{r['reason'] or ''}".rstrip(":"): r["n"]
            for r in c.execute(
                "SELECT state, reason, count(*) AS n FROM urls WHERE source_id = %s AND kind = 'audio' GROUP BY state, reason", (sid,)
            )
        }
        pages_blocked = {
            r["reason"]: r["n"]
            for r in c.execute("SELECT reason, count(*) AS n FROM urls WHERE source_id = %s AND state = 'skipped' GROUP BY reason", (sid,))
        }
        items = c.execute("SELECT state, reason, licence FROM items WHERE source_id = %s", (sid,)).fetchall()
    costs = cost.report(url, source).get("sources", {}).get(source, {})
    n = len(items)
    kept = sum(1 for i in items if i["state"] == "kept")
    held = sum(1 for i in items if i["state"] == "held")
    reasons: dict[str, int] = {}
    for i in items:
        if i["state"] in ("rejected", "held"):
            reasons[i["reason"]] = reasons.get(i["reason"], 0) + 1
    licences: dict[str, int] = {}
    for i in items:
        licences[i["licence"]] = licences.get(i["licence"], 0) + 1
    opted_out = sum(v for k, v in pages_blocked.items() if k in ("robots", "tdm", "blocked_domain", "takedown"))
    if n == 0 and opted_out:
        verdict = (
            "skip: the site opts out (" + ", ".join(k for k in pages_blocked if k in ("robots", "tdm", "blocked_domain", "takedown")) + ")"
        )
    elif n == 0:
        verdict = "skip: no audio found"
    elif reasons.get("licence", 0) == n:
        verdict = "skip: no file has a licence we may use"
    elif kept == 0 and held == 0:
        top = max(reasons, key=lambda k: reasons[k])
        verdict = f"skip: nothing usable in the sample (mostly {top})"
    elif held > kept:
        verdict = "review first: most of the sample is held as possibly synthetic"
    else:
        cph = costs.get("usd_per_kept_hour")
        verdict = f"ingest: {kept} of {n} sampled files usable" + (f", about ${cph:.2f} per usable hour" if cph else "")
    return {
        "source": source,
        "sampled_files": n,
        "kept": kept,
        "held": held,
        "rejected_by_reason": reasons,
        "licences": licences,
        "audio_urls": urls,
        "not_fetched": pages_blocked,
        "yield": costs.get("yield"),
        "usd_per_kept_hour": costs.get("usd_per_kept_hour"),
        "verdict": verdict,
    }


def jobs_pending(url: str | None = None) -> int:
    return sum(v for k, v in jobs.counts(url).items() if k.endswith(":queued"))
