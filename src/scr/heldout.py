"""Held-out worlds: written by someone who has not seen the code (heldout/WRITING_SETS.md),
rendered, run once, and recorded. The first run of a set is kept as it was
(`reports/heldout/<set>/first_run.json` is never rewritten); later runs go to `latest.json`.
Once anyone studies a set's failures to change the code, its STATUS becomes `regression` and a
new blind set has to be written."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from . import config, db, evaluation
from .crawl.crawler import Crawler
from .pipeline import protect_all, work
from .store import LocalStore
from .world import spec
from .world.serve import WorldServer

HELDOUT = config.ROOT / "heldout"
REPORTS = config.ROOT / "reports" / "heldout"


def run(name: str, url: str, processes: int = 2, record: bool = True) -> dict[str, Any]:
    d = HELDOUT / name
    status = (d / "STATUS").read_text().strip() if (d / "STATUS").exists() else "blind"
    world = config.DATA_DIR / "heldout" / name
    spec.render(d / "world.yaml", world)
    blocked = json.loads((world / "rights_override.json").read_text())["blocked_domains"]
    os.environ["SCR_EXTRA_BLOCKED_DOMAINS"] = ",".join(blocked)
    config.load.cache_clear()
    try:
        db.close_all()
        db.reset(url)
        db.migrate(url)
        protect_all(url)
        store_root = config.DATA_DIR / "heldout_store" / name
        shutil.rmtree(store_root, ignore_errors=True)
        store = LocalStore(store_root)
        with WorldServer(world) as server:
            cr = Crawler(url, store=store, world=server.addr)
            for s in json.loads((world / "seeds.json").read_text()):
                cr.seed(s["source"], s["kind"], s["url"])
            cr.run(workers=4, deadline=900)
            log = server.log
        work(url, store, processes)
        ev = evaluation.evaluate(world, log, url)
    finally:
        os.environ.pop("SCR_EXTRA_BLOCKED_DOMAINS", None)
        config.load.cache_clear()
    ev["set"] = name
    ev["status"] = status
    out = REPORTS / name
    out.mkdir(parents=True, exist_ok=True)
    if record and not (out / "first_run.json").exists():
        (out / "first_run.json").write_text(json.dumps(ev, indent=1, default=str))
        (out / "FIRST_RUN.md").write_text(evaluation.markdown(ev, f"Held-out set {name}: first run"))
    (out / "latest.json").write_text(json.dumps(ev, indent=1, default=str))
    return ev
