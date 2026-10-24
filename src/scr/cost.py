"""What usable audio costs, per source: measured CPU per stage turned into Cloud Run job prices
(config/pricing.yaml), plus storage, divided by the hours that survive every filter. A source
whose files are mostly rejected costs more per usable hour even though each file is cheap,
which is what the discovery report weighs."""

from __future__ import annotations

from typing import Any

from . import config, db


def _compute_usd(cpu_s: float, p: dict[str, Any]) -> float:
    j = p["cloud_run_job"]
    return cpu_s * float(j["vcpu_second"]) + (cpu_s / float(j["vcpu"])) * float(j["gib"]) * float(j["gib_second"])


def report(url: str | None = None, source_prefix: str = "") -> dict[str, Any]:
    p = config.pricing()
    with db.tx(url) as c:
        sources = c.execute("SELECT id, name FROM sources WHERE name LIKE %s ORDER BY name", (source_prefix + "%",)).fetchall()
        out: dict[str, Any] = {"currency": p["currency"], "prices": p["source"], "sources": {}, "stages": {}}
        tot = {"cpu_s": 0.0, "audio_h": 0.0, "kept_h": 0.0, "usd": 0.0, "bytes": 0}
        for s in sources:
            sid = s["id"]
            cpu = {
                r["stage"]: float(r["cpu"])
                for r in c.execute("SELECT stage, sum(cpu_seconds) AS cpu FROM costs WHERE source_id = %s GROUP BY stage", (sid,))
            }
            crawl_wall = c.execute(
                "SELECT coalesce(sum(f.seconds), 0) AS s FROM fetches f JOIN urls u ON u.id = f.url_id WHERE u.source_id = %s", (sid,)
            ).fetchone()
            audio = c.execute(
                """SELECT count(*) AS items, coalesce(sum(a.seconds), 0) AS secs, coalesce(sum(b.bytes), 0) AS bytes
                   FROM items i LEFT JOIN analyses a ON a.item_id = i.id LEFT JOIN blobs b ON b.sha256 = i.sha256 AND b.deleted_at IS NULL WHERE i.source_id = %s""",
                (sid,),
            ).fetchone()
            kept = c.execute(
                "SELECT coalesce(sum(s.end_s - s.start_s), 0) AS secs FROM segments s JOIN items i ON i.id = s.item_id WHERE i.source_id = %s AND i.state = 'kept' AND s.state = 'kept'",
                (sid,),
            ).fetchone()
            decisions = {
                f"{r['state']}:{r['reason'] or ''}".rstrip(":"): r["n"]
                for r in c.execute("SELECT state, reason, count(*) AS n FROM items WHERE source_id = %s GROUP BY state, reason", (sid,))
            }
            assert audio is not None and kept is not None and crawl_wall is not None
            cpu_s = sum(cpu.values())
            # the crawler is I/O-bound: price its wall time as one 1-vCPU, 0.5 GiB task
            crawl_usd = float(crawl_wall["s"]) * (float(p["cloud_run_job"]["vcpu_second"]) + 0.5 * float(p["cloud_run_job"]["gib_second"]))
            storage_usd = int(audio["bytes"]) / 2**30 * float(p["storage"]["standard_gib_month"])
            usd = _compute_usd(cpu_s, p) + crawl_usd + storage_usd
            kept_h = float(kept["secs"]) / 3600
            audio_h = float(audio["secs"]) / 3600
            out["sources"][s["name"]] = {
                "items": int(audio["items"]),
                "audio_hours": round(audio_h, 4),
                "kept_hours": round(kept_h, 4),
                "yield": round(kept_h / audio_h, 3) if audio_h else 0.0,
                "cpu_seconds": round(cpu_s, 1),
                "usd": round(usd, 6),
                "usd_per_kept_hour": round(usd / kept_h, 4) if kept_h else None,
                "decisions": decisions,
            }
            for k, v in cpu.items():
                out["stages"][k] = round(out["stages"].get(k, 0.0) + v, 2)
            tot["cpu_s"] += cpu_s
            tot["audio_h"] += audio_h
            tot["kept_h"] += kept_h
            tot["usd"] += usd
            tot["bytes"] += int(audio["bytes"])
        audio_s = float((c.execute("SELECT coalesce(sum(seconds), 0) AS s FROM analyses").fetchone() or {"s": 0})["s"])
    out["total"] = {
        "audio_hours": round(tot["audio_h"], 4),
        "kept_hours": round(tot["kept_h"], 4),
        "cpu_seconds": round(tot["cpu_s"], 1),
        "usd": round(tot["usd"], 6),
        "usd_per_kept_hour": round(tot["usd"] / tot["kept_h"], 4) if tot["kept_h"] else None,
        "realtime_factor": round(tot["cpu_s"] / audio_s, 4) if audio_s else None,  # CPU seconds per second of audio analysed
    }
    if out["total"]["realtime_factor"]:
        # how many vCPUs keep up with a given intake, at the measured CPU per audio second
        rtf = out["total"]["realtime_factor"]
        out["total"]["vcpus_for_1000_hours_per_day"] = round(1000 * 3600 * rtf / 86400, 1)
    return out
