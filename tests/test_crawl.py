"""The crawler against the test world: rights, politeness, retries and what it stores."""

import itertools
import json
from collections import Counter

import pytest

from scr import audit, db
from scr.crawl.crawler import Crawler
from scr.store import LocalStore

from .conftest import WorldServer, needs_db, needs_models

pytestmark = [needs_db, needs_models]


@pytest.fixture
def crawled(fresh_db, world_root, fast_settings, tmp_path):
    seeds = json.loads((world_root / "seeds.json").read_text())
    with WorldServer(world_root) as server:
        cr = Crawler(fresh_db, store=LocalStore(tmp_path / "store"), world=server.addr)
        for s in seeds:
            cr.seed(s["source"], s["kind"], s["url"])
        stats = cr.run(workers=4, deadline=240)
        log = list(server.log)
    return fresh_db, stats, log, world_root, tmp_path / "store"


def test_crawl_respects_rights_and_stores_only_what_it_may(crawled):
    url, stats, log, root, _ = crawled
    truth = {t["url"]: t for t in json.loads((root / "truth.json").read_text())}
    requested = {(e["host"], e["path"]) for e in log}
    # a blocked domain is never contacted, not even for robots.txt
    assert not [e for e in log if e["host"] == "pirate.example"]
    # robots.txt: nothing under /recordings/members/, but /recordings/public/ is fetched
    assert not [p for h, p in requested if h == "private.example" and p.startswith("/recordings/members/")]
    assert ("private.example", "/recordings/public/r0.flac") in requested
    # TDMRep file reservation: no request at all; header reservation: requested, body not stored
    assert not [p for h, p in requested if h == "reserved.example" and p.startswith("/studio/")]
    with db.tx(url) as c:
        items = {r["url"]: r for r in c.execute("SELECT u.url, i.* FROM items i JOIN urls u ON u.id = i.url_id")}
        urls = {r["url"]: r for r in c.execute("SELECT * FROM urls")}
    assert not [u for u in items if "/press/" in u or "/studio/" in u]
    # header reservation on /press/: the page is requested, its body is not used, so its audio is never discovered
    take2 = urls["http://reserved.example/press/take2.html"]
    assert take2["reason"] == "tdm" and take2["meta"]["tdm"] == "header"
    assert "http://reserved.example/press/take2.flac" not in urls
    # every audio file the world expects us to download, and nothing else
    fetchable = {u for u, t in truth.items() if not t["blocked_by"]}
    assert set(items) == fetchable
    # every request identifies the crawler
    assert {e["ua"] for e in log} == {
        "ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)"
    }
    assert stats.skipped.get("blocked_domain", 0) == 0  # blocked at enqueue time, recorded below
    assert urls["http://pirate.example/index.html"]["state"] == "skipped"


def test_crawl_recovers_from_server_failures(crawled):
    url, stats, _, _, _ = crawled
    with db.tx(url) as c:
        urls = {r["url"]: r for r in c.execute("SELECT * FROM urls")}
        fetches = Counter(r["url"] for r in c.execute("SELECT u.url FROM fetches f JOIN urls u ON u.id = f.url_id"))
    base = "http://flaky.example/files/"
    for name in ("rate-limited.flac", "unavailable.flac", "slow.flac", "truncated.flac"):
        assert urls[base + name]["state"] == "done", (name, urls[base + name])
    assert fetches[base + "rate-limited.flac"] == 3 and fetches[base + "truncated.flac"] == 2
    loop = [u for u in urls.values() if u["url"].startswith(base + "loop.flac")]
    assert len(loop) == 6 and [u["reason"] for u in loop].count("too many redirects") == 1
    assert not [u for u in loop if u["state"] == "done" and u["reason"] != "redirected"]
    assert stats.retried >= 4


def test_one_request_at_a_time_per_host(crawled):
    _, _, log, _, _ = crawled
    by_host: dict[str, list[float]] = {}
    for e in log:
        by_host.setdefault(e["host"], []).append(e["t"])
    # robots.txt and tdmrep.json are fetched back to back on first contact; after that, the
    # gap between requests to one host respects the minimum delay (0.05 s in the test settings)
    for host, ts in by_host.items():
        gaps = [b - a for a, b in itertools.pairwise(ts[2:])]
        assert all(g >= 0.04 for g in gaps), (host, min(gaps))


def test_items_carry_licence_evidence_and_blobs_are_content_addressed(crawled):
    url, _, _, _, store = crawled
    with db.tx(url) as c:
        rows = {
            r["url"]: r
            for r in c.execute(
                "SELECT u.url, i.licence, i.licence_evidence, i.synthetic_declared, i.sha256, i.text_url FROM items i JOIN urls u ON u.id = i.url_id"
            )
        }
        assert audit.verify(c).ok
    ch1 = rows["http://audiobooks.example/download/printing_01_morris_64kb.mp3"]
    assert ch1["licence"] == "LicenseRef-PublicDomain" and "LibriVox" in ch1["licence_evidence"]
    assert ch1["text_url"] == "http://audiobooks.example/texts/printing.txt"
    assert rows["http://podcasts.example/media/lnr-001.mp3"]["licence"] == "CC-BY-NC-4.0"
    assert rows["http://archive.example/download/jfk-inaugural-excerpt/jfk.flac"]["licence"] == "CC-PDM-1.0"
    assert all(r["synthetic_declared"] for u, r in rows.items() if u.startswith("http://voices.example/"))
    assert not any(r["synthetic_declared"] for u, r in rows.items() if "ai-news" in u or "aind-" in u)  # undeclared
    for r in rows.values():
        assert (store / "blobs" / r["sha256"][:2] / r["sha256"]).exists()
