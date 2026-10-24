"""End to end on the dev world: crawl, analyse in parallel worker processes, release, evaluate,
then take a recording down and check its re-upload is refused. About seven minutes."""

import json

import pyarrow.parquet as pq
import pytest

from scr import audit, db, evaluation, process, release, takedown
from scr.crawl.crawler import Crawler
from scr.pipeline import protect_all, work
from scr.store import LocalStore

from .conftest import WorldServer, needs_db, needs_models

pytestmark = [needs_db, needs_models, pytest.mark.slow]


@pytest.fixture(scope="module")
def run(world_root, tmp_path_factory):
    from .conftest import TEST_DB

    db.close_all()
    db.reset(TEST_DB)
    db.migrate(TEST_DB)
    protect_all(TEST_DB)
    root = tmp_path_factory.mktemp("e2e")
    store = LocalStore(root / "store")
    with WorldServer(world_root) as server:
        cr = Crawler(TEST_DB, store=store, world=server.addr)
        for s in json.loads((world_root / "seeds.json").read_text()):
            cr.seed(s["source"], s["kind"], s["url"])
        cr.run(workers=4, deadline=900)
        log = list(server.log)
    work(TEST_DB, store, processes=2)
    ev = evaluation.evaluate(world_root, log, TEST_DB)
    rel = release.build("e2e", store, root / "releases", TEST_DB)
    yield {"url": TEST_DB, "store": store, "ev": ev, "release": rel, "root": root}
    db.close_all()


def test_decisions_match_the_policy(run):
    ev = run["ev"]
    assert ev["files"] == 110
    assert ev["decisions_correct"] >= 109, [r for r in ev["rows"] if not r["decision_ok"]] if "rows" in ev else ev


def test_no_request_broke_a_rule(run):
    c = run["ev"]["compliance"]
    assert c["requests_to_blocked_domains"] == 0
    assert c["requests_disallowed_by_robots"] == 0
    assert c["requests_to_tdm_reserved_paths_in_tdmrep_json"] == 0
    assert c["reserved_files_stored"] == 0


def test_every_job_finished_and_the_audit_chain_holds(run):
    with db.tx(run["url"]) as c:
        states = {r["state"] for r in c.execute("SELECT DISTINCT state FROM jobs")}
        assert audit.verify(c).ok
    assert states == {"done"}


def test_the_release_is_attributed_speaker_disjoint_and_immutable(run):
    out = run["root"] / "releases" / "e2e"
    m = pq.read_table(out / "manifest.parquet").to_pylist()
    assert len(m) == run["release"]["segments"] > 0
    assert all(r["licence"] and r["attribution"] for r in m)
    splits: dict[str, set[str]] = {}
    for r in m:
        splits.setdefault(r["speaker"], set()).add(r["split"])
    assert all(len(v) == 1 for v in splits.values())  # speaker-disjoint
    for f in ("CARD.md", "ATTRIBUTION.md", "AI_ACT_SUMMARY.md", "ai_act_summary.json"):
        assert (out / f).exists()
    with pytest.raises(FileExistsError):
        release.build("e2e", run["store"], run["root"] / "releases", run["url"])


def test_analysing_a_file_twice_leaves_one_result_and_releases_stay_intact(run):
    url = run["url"]
    with db.tx(url) as c:
        item = c.execute("SELECT id FROM items WHERE state = 'kept' ORDER BY id LIMIT 1").fetchone()["id"]
        before = c.execute("SELECT count(*) AS n FROM segments WHERE item_id = %s", (item,)).fetchone()["n"]
    assert process.analyse(item, run["store"], url)["unchanged"] is True  # same settings: nothing redone
    with db.tx(url) as c:
        after = c.execute("SELECT count(*) AS n FROM segments WHERE item_id = %s", (item,)).fetchone()["n"]
        state = c.execute("SELECT state FROM items WHERE id = %s", (item,)).fetchone()["state"]
    assert after == before and state == "kept"
    # under new settings it is analysed again; the released segments stay, withdrawn, and new ones follow
    with db.tx(url) as c:
        c.execute("UPDATE items SET decided_config = 'older-settings' WHERE id = %s", (item,))
    process.analyse(item, run["store"], url)
    with db.tx(url) as c:
        rows = c.execute("SELECT idx, state, reason FROM segments WHERE item_id = %s ORDER BY idx", (item,)).fetchall()
        released = c.execute(
            "SELECT count(*) AS n FROM release_segments rs JOIN segments s ON s.id = rs.segment_id WHERE s.item_id = %s", (item,)
        ).fetchone()["n"]
    assert [r["reason"] for r in rows[:before]] == ["reanalysed"] * before and released == before
    assert len(rows) == 2 * before and {r["state"] for r in rows[before:]} == {"kept"}


def test_after_a_takedown_a_reupload_is_refused_by_fingerprint(run):
    url, store = run["url"], run["store"]
    original = "http://audiobooks.example/download/printing_02_morris_64kb.mp3"
    reupload = "http://archive.example/download/printing-of-books-ch2-reupload/chapter2.mp3"
    tid = takedown.request("url", original, "Narrator asked for removal", "admin:test", url)
    out = takedown.execute(tid, store, "admin:test", url)
    assert out["items"] == 1 and out["releases"] == ["e2e"] and out["blobs_deleted"] == 1
    with db.tx(url) as c:
        rid = c.execute("SELECT i.id FROM items i JOIN urls u ON u.id = i.url_id WHERE u.url = %s", (reupload,)).fetchone()["id"]
        c.execute("UPDATE items SET state = 'new' WHERE id = %s", (rid,))  # as if it had just been uploaded again
    process.analyse(rid, store, url)
    with db.tx(url) as c:
        r = c.execute("SELECT state, reason FROM items WHERE id = %s", (rid,)).fetchone()
    assert (r["state"], r["reason"]) == ("rejected", "takedown")
