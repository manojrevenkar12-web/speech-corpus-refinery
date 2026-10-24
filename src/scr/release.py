"""A release: the kept segments, frozen. Speakers are clustered across all sources and the
splits are speaker-disjoint, so no voice is in both train and test. Audio is written at the
target rate as FLAC in WebDataset tar shards; a Parquet manifest records every segment's
source, licence, attribution and measurements. Each release also carries a dataset card,
ATTRIBUTION.md for licences that require it, and the public summary of training content that
the EU AI Act asks providers of general-purpose AI models to publish (Article 53(1)(d), AI
Office template of 24 July 2025)."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import audit, config, db
from .audio import decode as dec
from .rights import licence as lic
from .store import Store

ELIGIBLE = """
  SELECT s.id, s.item_id, s.idx, s.start_s, s.end_s, s.text, s.asr, s.cer, s.snr_db, s.bandwidth_hz, s.tier, s.embedding,
         i.sha256, i.licence, i.licence_evidence, i.attribution, i.title, i.source_id, u.url, src.name AS source
  FROM segments s JOIN items i ON i.id = s.item_id JOIN urls u ON u.id = i.url_id JOIN sources src ON src.id = i.source_id
  WHERE s.state = 'kept' AND i.state = 'kept'
  ORDER BY s.item_id, s.idx
"""


def cluster_speakers(emb: np.ndarray, threshold: float) -> list[int]:
    """Average-linkage clustering on cosine similarity: segments closer than `threshold` share a
    speaker label."""
    if len(emb) == 0:
        return []
    if len(emb) == 1:
        return [0]
    from scipy.cluster.hierarchy import fcluster, linkage

    z = linkage(emb, method="average", metric="cosine")
    return [int(v) - 1 for v in fcluster(z, t=1 - threshold, criterion="distance")]


def assign_splits(hours: dict[str, float], fractions: dict[str, float]) -> dict[str, str]:
    """Speakers to splits, largest first, each to the split furthest below its target share."""
    total = sum(hours.values()) or 1.0
    got = {k: 0.0 for k in fractions}
    out = {}
    for spk, h in sorted(hours.items(), key=lambda kv: (-kv[1], kv[0])):
        split = max(fractions, key=lambda k: (fractions[k] - got[k] / total, k == "train"))
        out[spk] = split
        got[split] += h
    return out


def build(name: str, store: Store, out_root: Path | None = None, url: str | None = None, actor: str = "scr") -> dict[str, Any]:
    cfg = config.settings()
    rel_cfg, spk_cfg = cfg["release"], cfg["speakers"]
    rate = int(cfg["target"]["sample_rate"])
    out = (out_root or config.DATA_DIR / "releases") / name
    if out.exists():
        raise FileExistsError(f"release {name} exists; releases are immutable")
    with db.tx(url) as c:
        if c.execute("SELECT 1 FROM releases WHERE name = %s", (name,)).fetchone():
            raise FileExistsError(f"release {name} exists; releases are immutable")
        rows = c.execute(ELIGIBLE).fetchall()
        parent = c.execute("SELECT name FROM releases ORDER BY id DESC LIMIT 1").fetchone()
    out.mkdir(parents=True)

    # speakers across sources, then speaker-disjoint splits
    emb = np.array([r["embedding"] for r in rows], dtype=np.float32) if rows else np.zeros((0, 256), np.float32)
    labels = cluster_speakers(emb, float(spk_cfg["cluster_threshold"]))
    spk_ids = [f"spk{lab:04d}" for lab in labels]
    hours: dict[str, float] = defaultdict(float)
    for r, s in zip(rows, spk_ids, strict=True):
        hours[s] += (r["end_s"] - r["start_s"]) / 3600
    splits = assign_splits(dict(hours), spk_cfg["split"])

    # audio shards
    manifest: list[dict[str, Any]] = []
    shard_n, shard_s = 0, 0.0
    tar: tarfile.TarFile | None = None
    shard_max = float(rel_cfg["shard_seconds"])
    with tempfile.TemporaryDirectory(prefix="scr-rel-") as td:
        blobs: dict[str, Path] = {}
        for r, spk in zip(rows, spk_ids, strict=True):
            if tar is None or shard_s >= shard_max:
                if tar:
                    tar.close()
                tar = tarfile.open(out / f"shard-{shard_n:05d}.tar", "w")  # noqa: SIM115 - shards rotate; closed below
                shard_n += 1
                shard_s = 0.0
            if r["sha256"] not in blobs:
                blobs[r["sha256"]] = store.get_file(r["sha256"], Path(td) / r["sha256"])
            y = dec.resample(blobs[r["sha256"]], rate, r["start_s"], r["end_s"] - r["start_s"])
            flac = Path(td) / "seg.flac"
            dec.encode(y, rate, flac, codec="flac")
            key = f"{r['item_id']:08d}_{r['idx']:04d}"
            dur = r["end_s"] - r["start_s"]
            rec = {
                "key": key,
                "segment_id": r["id"],
                "split": splits[spk],
                "speaker": spk,
                "seconds": round(dur, 3),
                "text": r["text"],
                "text_source": "published" if r["cer"] is not None else "asr",
                "alignment_cer": r["cer"],
                "snr_db": round(r["snr_db"], 1),
                "bandwidth_hz": round(r["bandwidth_hz"] or 0),
                "tier": r["tier"],
                "source": r["source"],
                "url": r["url"],
                "start_s": round(r["start_s"], 3),
                "licence": r["licence"],
                "attribution": r["attribution"],
                "item_sha256": r["sha256"],
            }
            for suffix, data in (("flac", flac.read_bytes()), ("json", json.dumps(rec, ensure_ascii=False).encode())):
                info = tarfile.TarInfo(f"{key}.{suffix}")
                info.size = len(data)
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
            shard_s += dur
            manifest.append(rec | {"shard": f"shard-{shard_n - 1:05d}.tar"})
        if tar:
            tar.close()

    table = pa.Table.from_pylist(manifest) if manifest else pa.table({"key": pa.array([], pa.string())})
    pq.write_table(table, out / "manifest.parquet")
    man_sha = hashlib.sha256((out / "manifest.parquet").read_bytes()).hexdigest()
    stats = _stats(manifest)
    with db.tx(url) as c:
        summary = ai_act_summary(c, name, manifest)
    (out / "ai_act_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "AI_ACT_SUMMARY.md").write_text(_summary_md(summary))
    (out / "ATTRIBUTION.md").write_text(_attribution(manifest))
    (out / "CARD.md").write_text(_card(name, stats, summary))
    for f in sorted(out.iterdir()):
        store.put_bytes(f"releases/{name}/{f.name}", f.read_bytes())
    with db.tx(url) as c:
        r = c.execute(
            "INSERT INTO releases (name, config_hash, manifest_sha256, stats, parent) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (name, config.fingerprint(cfg, config.rights()), man_sha, json.dumps(stats), parent["name"] if parent else None),
        ).fetchone()
        assert r is not None
        with c.cursor().copy("COPY release_segments (release_id, segment_id, split) FROM STDIN") as cp:
            for m in manifest:
                cp.write_row((r["id"], m["segment_id"], m["split"]))
        for row, spk in zip(rows, spk_ids, strict=True):
            c.execute("UPDATE segments SET speaker = %s WHERE id = %s", (spk, row["id"]))
        audit.append(c, actor, "release", {"name": name, "manifest_sha256": man_sha, "segments": len(manifest), "hours": stats["hours"]})
    return {"name": name, "dir": str(out), "manifest_sha256": man_sha, **stats}


def _stats(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    hrs = lambda rows: round(sum(m["seconds"] for m in rows) / 3600, 4)  # noqa: E731
    by = lambda key: {k: hrs([m for m in manifest if m[key] == k]) for k in sorted({m[key] for m in manifest})}  # noqa: E731
    return {
        "segments": len(manifest),
        "hours": hrs(manifest),
        "speakers": len({m["speaker"] for m in manifest}),
        "by_split": by("split"),
        "by_source": by("source"),
        "by_licence": by("licence"),
        "by_tier": by("tier"),
        "by_text_source": by("text_source"),
        "speakers_by_split": {s: len({m["speaker"] for m in manifest if m["split"] == s}) for s in sorted({m["split"] for m in manifest})},
    }


def ai_act_summary(c: Any, name: str, manifest: list[dict[str, Any]]) -> dict[str, Any]:
    """The dataset's part of the public summary of training content (AI Office template):
    general information, data sources (including the top domains of web-scraped content), and
    processing (opt-outs honoured, filters applied)."""
    s = config.settings()
    seconds = sum(m["seconds"] for m in manifest)
    by_domain: Counter[str] = Counter()
    for m in manifest:
        by_domain[urlsplit(m["url"]).netloc] += m["seconds"]
    domains = [d for d, _ in by_domain.most_common()]
    top_n = max(1, -(-len(domains) // 10))  # top 10% of domains, at least one
    window: dict[str, Any] = c.execute("SELECT min(at) AS first, max(at) AS last FROM fetches").fetchone() or {}
    skipped = {r["reason"]: r["n"] for r in c.execute("SELECT reason, count(*) AS n FROM urls WHERE state = 'skipped' GROUP BY reason")}
    takedowns = c.execute("SELECT count(*) AS n FROM takedowns WHERE executed_at IS NOT NULL").fetchone() or {"n": 0}
    rejected = {
        r["reason"]: r["n"]
        for r in c.execute("SELECT reason, count(*) AS n FROM items WHERE state IN ('rejected', 'held') GROUP BY reason")
    }
    return {
        "release": name,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "general": {
            "modality": "audio (speech)",
            "language": s["target"]["language"],
            "size": {"hours": round(seconds / 3600, 3), "segments": len(manifest), "speakers": len({m["speaker"] for m in manifest})},
        },
        "sources": {
            "web_crawled": {
                "crawler": s["crawl"]["user_agent"],
                "collection_period": {"from": window.get("first"), "to": window.get("last")},
                "top_domains": [{"domain": d, "share": round(by_domain[d] / max(seconds, 1e-9), 4)} for d in domains[:top_n]],
                "domains": len(domains),
            },
            "licences": {
                k: round(sum(m["seconds"] for m in manifest if m["licence"] == k) / 3600, 4)
                for k in sorted({m["licence"] for m in manifest})
            },
            "synthetic_content": "excluded: declared AI-generated audio is rejected, suspected synthetic speech is held for review",
        },
        "processing": {
            "opt_outs": {
                "robots_txt": "RFC 9309, product token " + s["crawl"]["robots_token"],
                "tdmrep": "W3C TDMRep: /.well-known/tdmrep.json, tdm-reservation header, meta tag",
                "blocked_domains": len(config.rights().get("blocked_domains", [])),
                "urls_not_fetched": skipped,
            },
            "takedowns_executed": int(takedowns["n"]),
            "filters": sorted(rejected),
            "items_rejected_by_reason": rejected,
        },
    }


def _summary_md(s: dict[str, Any]) -> str:
    g, src, p = s["general"], s["sources"], s["processing"]
    lines = [
        f"# Public summary of training content: {s['release']}",
        "",
        "Dataset contribution to the summary required by Article 53(1)(d) of the EU AI Act, following the AI Office template.",
        "",
        "## General information",
        f"- Modality: {g['modality']}; language: {g['language']}",
        f"- Size: {g['size']['hours']} hours in {g['size']['segments']} segments from {g['size']['speakers']} speakers",
        "",
        "## Data sources",
        f"- Web-crawled by `{src['web_crawled']['crawler']}` between {src['web_crawled']['collection_period']['from']} and {src['web_crawled']['collection_period']['to']}",
        f"- Top domains (top 10% of {src['web_crawled']['domains']}): "
        + ", ".join(f"{d['domain']} ({d['share']:.0%})" for d in src["web_crawled"]["top_domains"]),
        "- Licences (hours): " + ", ".join(f"{k} {v}" for k, v in src["licences"].items()),
        f"- Synthetic content: {src['synthetic_content']}",
        "",
        "## Processing",
        f"- Opt-outs honoured: robots.txt ({p['opt_outs']['robots_txt']}); {p['opt_outs']['tdmrep']}; {p['opt_outs']['blocked_domains']} blocked domains",
        "- URLs not fetched because of an opt-out: "
        + (", ".join(f"{k}: {v}" for k, v in p["opt_outs"]["urls_not_fetched"].items()) or "none"),
        f"- Takedowns executed: {p['takedowns_executed']}",
        "- Items excluded, by reason: " + ", ".join(f"{k}: {v}" for k, v in p["items_rejected_by_reason"].items()),
        "",
    ]
    return "\n".join(lines)


def _attribution(manifest: list[dict[str, Any]]) -> str:
    need = {k for k, v in config.rights()["allowed_licences"].items() if (v or {}).get("attribution")}
    rows = sorted({(m["licence"], m["attribution"], m["url"]) for m in manifest if m["licence"] in need})
    out = [
        "# Attribution",
        "",
        "Recordings in this release whose licences require attribution.",
        "",
        "| Licence | Credit | Source |",
        "|---|---|---|",
    ]
    out += [f"| {lc} | {a} | {u} |" for lc, a, u in rows]
    return "\n".join(out) + "\n"


def _card(name: str, stats: dict[str, Any], summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# Dataset card: {name}",
            "",
            f"{stats['hours']} hours, {stats['segments']} segments, {stats['speakers']} speakers (clustered from speaker embeddings).",
            "",
            "Splits are speaker-disjoint: "
            + ", ".join(f"{k} {v} h ({stats['speakers_by_split'].get(k, 0)} speakers)" for k, v in stats["by_split"].items())
            + ".",
            "",
            "Bandwidth tiers (HiFiTTS-2 method): "
            + ", ".join(f"{k} {v} h" for k, v in stats["by_tier"].items())
            + ". `full` is usable at 22.05 kHz, `wide` at 16 kHz.",
            "",
            "Transcripts: "
            + ", ".join(f"{k} {v} h" for k, v in stats["by_text_source"].items())
            + ". `published` text is the source's own text matched to the audio; `asr` is Whisper output and less reliable.",
            "",
            "Licences: " + ", ".join(f"{k} {v} h" for k, v in stats["by_licence"].items()) + ". See ATTRIBUTION.md.",
            "",
            "Opt-outs, filters and takedowns: see AI_ACT_SUMMARY.md.",
            "",
        ]
    )


def diff(a: str, b: str, url: str | None = None) -> dict[str, Any]:
    with db.tx(url) as c:
        ids = {}
        for n in (a, b):
            r = c.execute("SELECT id FROM releases WHERE name = %s", (n,)).fetchone()
            if r is None:
                raise LookupError(n)
            ids[n] = {x["segment_id"] for x in c.execute("SELECT segment_id FROM release_segments WHERE release_id = %s", (r["id"],))}
        removed = sorted(ids[a] - ids[b])
        why = (
            {
                r["id"]: r["reason"]
                for r in c.execute("SELECT id, coalesce(reason, state) AS reason FROM segments WHERE id = ANY(%s)", (removed,))
            }
            if removed
            else {}
        )
    return {
        "added": len(ids[b] - ids[a]),
        "removed": len(removed),
        "removed_by_reason": dict(Counter(why.values())),
        "kept": len(ids[a] & ids[b]),
    }


def licence_ok(spdx: str) -> bool:
    return lic.decide(spdx, config.rights()).allowed
