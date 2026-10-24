"""The whole run on the test world, as CI and `scr demo` do it: build the world, score each
source on a small sample, then crawl everything, process it on parallel workers, cut a release
and measure the result against the truth."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Any

from . import assets, config, cost, db, discover, evaluation, jobs, process, release
from .crawl.crawler import Crawler
from .store import LocalStore, Store
from .world import build as world_build
from .world.serve import WorldServer

REPORTS = config.ROOT / "reports"


def protect_all(url: str | None = None) -> int:
    n = 0
    for r in config.load("protected").get("recordings", []):
        a = next(x for x in assets.corpus_assets() if x.corpus == r["corpus"] and x.path == r["path"])
        process.protect(r["label"], a.local, url)
        n += 1
    return n


def _worker(url: str, store_root: str, threads: str) -> int:
    os.environ["SCR_MODEL_THREADS"] = threads
    store = LocalStore(Path(store_root))
    db.close_all()
    return jobs.work(["analyse"], lambda j: process.analyse(j.ref, store, url), url=url)


def work(url: str, store: LocalStore, processes: int = 2) -> int:
    if processes <= 1:
        return _worker(url, str(store.root), os.environ.get("SCR_MODEL_THREADS", "1"))
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes) as pool:
        return sum(pool.starmap(_worker, [(url, str(store.root), "1")] * processes))


def demo(
    world: Path | None = None,
    url: str | None = None,
    store_root: Path | None = None,
    processes: int = 2,
    sample: int = 4,
    out: Path = REPORTS,
    release_name: str = "v1",
) -> dict[str, Any]:
    url = url or config.database_url()
    world = world or config.DATA_DIR / "world"
    store_root = store_root or config.DATA_DIR / "store"
    timings: dict[str, float] = {}

    def step(name: str, t0: float) -> None:
        timings[name] = round(time.perf_counter() - t0, 1)

    t = time.perf_counter()
    if not (world / "truth.json").exists():
        world_build.build(world)
    step("world", t)
    seeds = json.loads((world / "seeds.json").read_text())
    out.mkdir(parents=True, exist_ok=True)

    with WorldServer(world) as server:
        # 1. discovery: each source scored on a small sample, in a scratch database
        t = time.perf_counter()
        db.reset(url)
        db.migrate(url)
        protect_all(url)
        scratch: Store = LocalStore(store_root / "probe")
        scores = [discover.probe(s["source"], s["kind"], s["url"], scratch, sample, url, server.addr) for s in seeds]
        step("discovery", t)
        (out / "discovery.json").write_text(json.dumps(scores, indent=1, default=str))
        (out / "DISCOVERY.md").write_text(_discovery_md(scores, sample))

        # 2. the full run
        db.close_all()
        db.reset(url)
        db.migrate(url)
        protect_all(url)
        store = LocalStore(store_root)
        t = time.perf_counter()
        cr = Crawler(url, store=store, world=server.addr)
        for s in seeds:
            cr.seed(s["source"], s["kind"], s["url"])
        crawl = cr.run(workers=4, deadline=900)
        step("crawl", t)
        log = server.log
    t = time.perf_counter()
    analysed = work(url, store, processes)
    step("process", t)
    t = time.perf_counter()
    rel_root = config.DATA_DIR / "releases"
    if (rel_root / release_name).exists():
        import shutil

        shutil.rmtree(rel_root / release_name)
    rel = release.build(release_name, store, rel_root, url)
    step("release", t)

    ev = evaluation.evaluate(world, log, url)
    costs = cost.report(url)
    (out / "evaluation.json").write_text(json.dumps(ev, indent=1, default=str))
    (out / "EVALUATION.md").write_text(evaluation.markdown(ev))
    (out / "costs.json").write_text(json.dumps(costs, indent=1, default=str))
    (out / "COSTS.md").write_text(_costs_md(costs))
    for f in ("CARD.md", "AI_ACT_SUMMARY.md", "ATTRIBUTION.md"):
        (out / f"release_{f}").write_text((rel_root / release_name / f).read_text())
    summary = {
        "timings_seconds": timings,
        "crawl": crawl.__dict__,
        "analysed": analysed,
        "release": {k: v for k, v in rel.items() if k != "dir"},
        "decisions_correct": f"{ev['decisions_correct']}/{ev['files']}",
        "compliance": ev["compliance"],
        "usd_per_kept_hour": costs["total"]["usd_per_kept_hour"],
    }
    (out / "run.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def _discovery_md(scores: list[dict[str, Any]], sample: int) -> str:
    out = [
        "# Source discovery",
        "",
        f"Each source scored on a sample of up to {sample} audio files, processed exactly as a full ingest would process them.",
        "",
        "| Source | Sampled | Kept | Held | Not fetched | Main rejections | Verdict |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for s in scores:
        rej = ", ".join(f"{k} {v}" for k, v in sorted(s["rejected_by_reason"].items(), key=lambda kv: -kv[1])) or "none"
        nf = ", ".join(f"{k} {v}" for k, v in s["not_fetched"].items()) or "none"
        out.append(
            f"| {s['source'].removeprefix('probe:')} | {s['sampled_files']} | {s['kept']} | {s['held']} | {nf} | {rej} | {s['verdict']} |"
        )
    return "\n".join(out) + "\n"


def _costs_md(c: dict[str, Any]) -> str:
    t = c["total"]
    out = [
        "# What usable audio costs",
        "",
        f"Measured CPU per stage, priced as Cloud Run jobs ({c['prices']}), plus crawl time and raw storage for a month.",
        "",
        f"- Audio analysed: {t['audio_hours']} h; kept: {t['kept_hours']} h; CPU: {t['cpu_seconds']} s ({t['realtime_factor']} CPU seconds per audio second)",
        f"- Cost: ${t['usd']:.4f} in total, ${t['usd_per_kept_hour']} per kept hour"
        if t["usd_per_kept_hour"]
        else f"- Cost: ${t['usd']:.4f}",
        f"- At this rate, 1,000 hours of audio a day needs about {t.get('vcpus_for_1000_hours_per_day')} vCPUs running continuously",
        "",
        "| Source | Files | Audio h | Kept h | Yield | CPU s | $ per kept hour |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in c["sources"].items():
        cph = f"{s['usd_per_kept_hour']:.2f}" if s["usd_per_kept_hour"] else "nothing kept"
        out.append(f"| {name} | {s['items']} | {s['audio_hours']} | {s['kept_hours']} | {s['yield']:.0%} | {s['cpu_seconds']} | {cph} |")
    out += ["", "CPU by stage (seconds): " + ", ".join(f"{k} {v}" for k, v in sorted(c["stages"].items(), key=lambda kv: -kv[1])), ""]
    return "\n".join(out)
