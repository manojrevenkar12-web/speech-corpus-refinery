"""PostgreSQL behaviour without models: the job queue, the audit chain, takedowns and the API's roles."""

from __future__ import annotations

import json
import threading

import psycopg
import pytest
from fastapi.testclient import TestClient

from scr import audit, db, jobs, takedown
from scr.api import create_app
from scr.crawl.crawler import Crawler
from scr.store import LocalStore

from .conftest import TEST_DB, needs_db

pytestmark = needs_db

SHA = ["%064x" % (i + 1) for i in range(4)]


def _seed(url: str, store: LocalStore, tmp_path) -> dict[str, int]:
    """Two hosts, three files, segments in a release: enough to take things down."""
    ids: dict[str, int] = {}
    with db.tx(url) as c:
        src = c.execute(
            "INSERT INTO sources (name, kind, seed_url) VALUES ('club', 'rss', 'http://club.example/feed.xml') RETURNING id"
        ).fetchone()["id"]
        for host in ("club.example", "cdn.club.example", "other.example"):
            c.execute("INSERT INTO hosts (host) VALUES (%s)", (host,))
        for n, (u, sha) in enumerate(
            [
                ("http://club.example/m/ep_1.mp3", SHA[0]),
                ("http://cdn.club.example/m/ep2.mp3", SHA[1]),
                ("http://other.example/a.flac", SHA[2]),
            ]
        ):
            blob = tmp_path / f"b{n}"
            blob.write_bytes(sha.encode())
            store.put_file(sha, blob)
            c.execute("INSERT INTO blobs (sha256, bytes) VALUES (%s, 64)", (sha,))
            uid = c.execute(
                "INSERT INTO urls (url, host, source_id, kind, state) VALUES (%s, %s, %s, 'audio', 'done') RETURNING id",
                (u, u.split("/")[2], src),
            ).fetchone()["id"]
            iid = c.execute(
                "INSERT INTO items (url_id, source_id, sha256, licence, state) VALUES (%s, %s, %s, 'CC-BY-4.0', 'kept') RETURNING id",
                (uid, src, sha),
            ).fetchone()["id"]
            c.execute("INSERT INTO fp_items (item_id, n) VALUES (%s, 0)", (iid,))
            for k in range(2):
                c.execute(
                    """INSERT INTO segments (item_id, idx, start_s, end_s, speaker, embedding, state)
                       VALUES (%s, %s, %s, %s, %s, %s, 'kept')""",
                    (iid, k, k * 5.0, k * 5.0 + 4.0, "spk-a" if n < 2 else "spk-b", [1.0, 0.0, 0.0] if n < 2 else [0.0, 1.0, 0.0]),
                )
            ids[u] = iid
        rel = c.execute(
            "INSERT INTO releases (name, config_hash, manifest_sha256, stats) VALUES ('v1', 'x', 'y', '{}') RETURNING id"
        ).fetchone()["id"]
        c.execute("INSERT INTO release_segments SELECT %s, id, 'train' FROM segments", (rel,))
    return ids


# ------------------------------------------------------------------ job queue


def _enqueue(url: str, n: int) -> None:
    with db.tx(url) as c:
        for i in range(n):
            c.execute("INSERT INTO jobs (kind, ref) VALUES ('analyse', %s)", (i,))


def test_concurrent_workers_never_take_the_same_job(fresh_db):
    _enqueue(fresh_db, 40)
    seen: list[int] = []
    lock = threading.Lock()

    def handler(job: jobs.Job) -> None:
        with lock:
            seen.append(job.ref)

    threads = [threading.Thread(target=jobs.work, args=(["analyse"], handler), kwargs={"url": fresh_db}) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == list(range(40))
    assert jobs.counts(fresh_db) == {"analyse:done": 40}


def test_a_crashed_workers_job_is_picked_up_after_its_lease_expires(fresh_db):
    _enqueue(fresh_db, 1)
    lost = jobs.lease(["analyse"], "worker-that-dies", fresh_db)
    assert lost is not None and jobs.lease(["analyse"], "other", fresh_db) is None  # leased
    with db.tx(fresh_db) as c:
        c.execute("UPDATE jobs SET lease_until = now() - interval '1 second'")
    again = jobs.lease(["analyse"], "other", fresh_db)
    assert again is not None and again.id == lost.id and again.attempts == 2
    jobs.done(lost, "worker-that-dies", fresh_db)  # the dead worker's late write is fenced out
    assert jobs.counts(fresh_db) == {"analyse:running": 1}
    assert not jobs.extend(lost, "worker-that-dies", fresh_db)
    jobs.done(again, "other", fresh_db)
    assert jobs.counts(fresh_db) == {"analyse:done": 1}


def test_failing_jobs_back_off_then_go_dead(fresh_db):
    _enqueue(fresh_db, 1)
    dead: list[str] = []
    for _ in range(jobs.MAX_ATTEMPTS):
        with db.tx(fresh_db) as c:
            c.execute("UPDATE jobs SET not_before = now()")
        jobs.work(["analyse"], lambda j: 1 / 0, on_dead=lambda j, e: dead.append(e), url=fresh_db)
    assert jobs.counts(fresh_db) == {"analyse:dead": 1} and dead == ["ZeroDivisionError: division by zero"]


# ------------------------------------------------------------------ audit


def test_the_audit_log_is_a_hash_chain_that_cannot_be_edited(fresh_db):
    with db.tx(fresh_db) as c:
        for i in range(3):
            audit.append(c, "tester", "event", {"i": i})
        assert audit.verify(c).ok and audit.verify(c).entries == 3
    for stmt in ("UPDATE audit SET data = '{\"i\": 9}' WHERE seq = 2", "DELETE FROM audit WHERE seq = 1"):
        with pytest.raises(psycopg.Error), db.tx(fresh_db) as c:
            c.execute(stmt)
    # even with the trigger disabled by a superuser, tampering shows
    with db.tx(fresh_db) as c:
        c.execute("ALTER TABLE audit DISABLE TRIGGER USER")
        c.execute("UPDATE audit SET data = '{\"i\": 9}' WHERE seq = 2")
        c.execute("ALTER TABLE audit ENABLE TRIGGER USER")
        v = audit.verify(c)
    assert not v.ok and v.broken_at == 2


# ------------------------------------------------------------------ takedowns


def test_a_domain_takedown_withdraws_deletes_lists_releases_and_stops_crawling(fresh_db, tmp_path):
    store = LocalStore(tmp_path / "store")
    ids = _seed(fresh_db, store, tmp_path)
    p = takedown.preview("domain", "club.example", fresh_db)
    assert p == {"items": 2, "segments": 4, "kept_hours": round(16 / 3600, 4), "releases": ["v1"]}
    tid = takedown.request("domain", "club.example", "Rights holder asked", "admin:test", fresh_db)
    out = takedown.execute(tid, store, "admin:test", fresh_db)
    assert out == {"items": 2, "segments": 4, "releases": ["v1"], "blobs_deleted": 2}
    assert takedown.execute(tid, store, "admin:test", fresh_db) == out  # idempotent
    assert not store.exists(SHA[0]) and not store.exists(SHA[1]) and store.exists(SHA[2])
    with db.tx(fresh_db) as c:
        states = {r["id"]: r["state"] for r in c.execute("SELECT id, state FROM items")}
        blocked = {r["item_id"] for r in c.execute("SELECT item_id FROM fp_items WHERE blocked_by IS NOT NULL")}
        assert audit.verify(c).ok
    assert states == {
        ids["http://club.example/m/ep_1.mp3"]: "withdrawn",
        ids["http://cdn.club.example/m/ep2.mp3"]: "withdrawn",
        ids["http://other.example/a.flac"]: "kept",
    }
    assert blocked == {ids["http://club.example/m/ep_1.mp3"], ids["http://cdn.club.example/m/ep2.mp3"]}
    # the domain and its subdomains are never crawled again; other hosts still are
    cr = Crawler(fresh_db, store=store)
    sid = cr.seed("club2", "html_index", "http://www.club.example/index.html")
    cr.seed("other", "html_index", "http://other.example/index.html")
    with db.tx(fresh_db) as c:
        urls = {r["url"]: (r["state"], r["reason"]) for r in c.execute("SELECT url, state, reason FROM urls WHERE kind <> 'audio'")}
    assert sid and urls["http://www.club.example/index.html"] == ("skipped", "takedown")
    assert urls["http://other.example/index.html"] == ("queued", None)


def test_a_url_takedown_matches_by_prefix_not_by_pattern(fresh_db, tmp_path):
    store = LocalStore(tmp_path / "store")
    _seed(fresh_db, store, tmp_path)
    tid = takedown.request("url", "http://club.example/m/ep_1.mp3", "Speaker asked", "admin:test", fresh_db)
    assert takedown.execute(tid, store, "admin:test", fresh_db)["items"] == 1
    cr = Crawler(fresh_db, store=store)
    cr.seed("again", "html_index", "http://club.example/m/ep_1.mp3?x=1")
    cr.seed("near", "html_index", "http://club.example/m/epX1.mp3")  # `_` is not a wildcard
    with db.tx(fresh_db) as c:
        urls = {r["url"]: r["reason"] for r in c.execute("SELECT url, reason FROM urls")}
    assert urls["http://club.example/m/ep_1.mp3?x=1"] == "takedown" and urls["http://club.example/m/epX1.mp3"] is None


def test_a_speaker_takedown_removes_only_that_voice_and_blocks_it(fresh_db, tmp_path):
    store = LocalStore(tmp_path / "store")
    _seed(fresh_db, store, tmp_path)
    tid = takedown.request("speaker", "spk-b", "Speaker withdrew consent", "admin:test", fresh_db)
    out = takedown.execute(tid, store, "admin:test", fresh_db)
    assert out == {"items": 0, "segments": 2, "releases": ["v1"], "blobs_deleted": 0}
    with db.tx(fresh_db) as c:
        segs = {
            r["speaker"]: r["states"]
            for r in c.execute("SELECT speaker, array_agg(DISTINCT state) AS states FROM segments GROUP BY speaker")
        }
        centroid = c.execute("SELECT centroid FROM blocked_speakers").fetchone()["centroid"]
    assert segs == {"spk-a": ["kept"], "spk-b": ["withdrawn"]}
    assert centroid == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)


def test_takedown_requests_are_validated(fresh_db):
    with pytest.raises(ValueError):
        takedown.request("everything", "x", "y", "a", fresh_db)
    with pytest.raises(ValueError):
        takedown.request("url", " ", "reason", "a", fresh_db)


# ------------------------------------------------------------------ API roles


KEYS = "viewer-key-0000000001:viewer,reviewer-key-00000001:reviewer,admin-key-0000000000001:admin,short:admin"


@pytest.fixture
def api(fresh_db, tmp_path, monkeypatch):
    monkeypatch.delenv("SCR_AUTH", raising=False)
    monkeypatch.setenv("SCR_API_KEYS", KEYS)
    store = LocalStore(tmp_path / "store")
    ids = _seed(fresh_db, store, tmp_path)
    with db.tx(fresh_db) as c:
        c.execute("UPDATE items SET state = 'held', reason = 'synthetic_suspected' WHERE id = %s", (ids["http://other.example/a.flac"],))
    return TestClient(create_app(fresh_db, store)), ids


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_every_read_needs_a_key_and_keys_shorter_than_16_characters_are_ignored(api):
    client, _ = api
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers=_h("short")).status_code == 401
    r = client.get("/api/overview", headers=_h("viewer-key-0000000001"))
    assert r.status_code == 200 and r.json()["held"] == 1 and r.json()["audit"]["ok"]


def test_roles_gate_review_decisions_and_takedowns(api):
    client, ids = api
    held = ids["http://other.example/a.flac"]
    assert client.post(f"/api/items/{held}/resolve", json={"decision": "keep"}, headers=_h("viewer-key-0000000001")).status_code == 403
    r = client.post(f"/api/items/{held}/resolve", json={"decision": "keep", "note": "real reader"}, headers=_h("reviewer-key-00000001"))
    assert r.status_code == 200 and r.json() == {"item_id": held, "state": "kept"}
    assert client.post(f"/api/items/{held}/resolve", json={"decision": "keep"}, headers=_h("reviewer-key-00000001")).status_code == 409
    assert client.post(f"/api/items/{held}/resolve", json={"decision": "maybe"}, headers=_h("reviewer-key-00000001")).status_code == 422
    body = {"kind": "domain", "value": "club.example", "reason": "Rights holder asked"}
    assert client.post("/api/takedowns", json=body, headers=_h("reviewer-key-00000001")).status_code == 403
    preview = client.post("/api/takedowns/preview", json=body, headers=_h("viewer-key-0000000001"))
    assert preview.status_code == 200 and preview.json()["items"] == 2
    done = client.post("/api/takedowns", json=body, headers=_h("admin-key-0000000000001"))
    assert done.status_code == 200, done.text
    listed = client.get("/api/takedowns", headers=_h("viewer-key-0000000001")).json()
    assert listed[0]["value"] == "club.example" and listed[0]["affected"]["items"] == 2
    with db.tx(TEST_DB) as c:  # the reviewer's decision and the takedown are in the audit trail, attributed
        events = [(r["actor"], r["event"]) for r in c.execute("SELECT actor, event FROM audit ORDER BY seq")]
    assert ("reviewer:revi", "review.resolve") in events and ("admin:admi", "takedown.execute") in events


def test_spot_checks_are_recorded_and_summarised(api):
    client, ids = api
    item = ids["http://club.example/m/ep_1.mp3"]
    for verdict in ("agree", "agree", "disagree"):
        assert (
            client.post("/api/reviews", json={"item_id": item, "verdict": verdict}, headers=_h("reviewer-key-00000001")).status_code == 200
        )
    rows = client.get("/api/reviews/summary", headers=_h("viewer-key-0000000001")).json()
    kept = next(r for r in rows if r["decision"] == "kept")
    assert kept["n"] == 3 and kept["agree"] == 2 and 0 < kept["agree_interval"][0] < 0.67 < kept["agree_interval"][1]
    assert json.loads(json.dumps(rows))  # serialisable


# ------------------------------------------------------------------ duplicates: the better copy wins only once it is kept


def test_a_worse_copy_is_demoted_only_by_a_kept_better_one_and_requeued_if_that_one_fails(fresh_db, tmp_path):
    from scr import process

    ids = _seed(fresh_db, LocalStore(tmp_path / "store"), tmp_path)
    a, b, other = ids["http://club.example/m/ep_1.mp3"], ids["http://cdn.club.example/m/ep2.mp3"], ids["http://other.example/a.flac"]
    with db.tx(fresh_db) as c:
        for i in (a, b, other):
            c.execute("INSERT INTO jobs (kind, ref, state) VALUES ('analyse', %s, 'done')", (i,))
        # b is better than the kept a: a goes, with its segments
        assert process.demote_replaced(c, b, [a]) == [a]
        row = c.execute("SELECT state, reason, detail FROM items WHERE id = %s", (a,)).fetchone()
        assert (row["state"], row["reason"], row["detail"]["duplicate_of"]) == ("rejected", "duplicate", b)
        assert {r["state"] for r in c.execute("SELECT state FROM segments WHERE item_id = %s", (a,))} == {"withdrawn"}
        # a copy rejected for another reason is left alone
        c.execute("UPDATE items SET state = 'rejected', reason = 'licence' WHERE id = %s", (other,))
        assert process.demote_replaced(c, b, [other]) == []
        # b then fails on its own (say, clipping): a was rejected for nothing and is judged again
        assert process.requeue_duplicates_of(c, b) == [a]
        assert c.execute("SELECT state, reason FROM items WHERE id = %s", (a,)).fetchone() == {"state": "new", "reason": None}
        job = c.execute("SELECT state, attempts FROM jobs WHERE ref = %s", (a,)).fetchone()
        assert job == {"state": "queued", "attempts": 0}
        assert process.requeue_duplicates_of(c, other) == []


def test_keeping_a_held_better_copy_on_review_supersedes_the_kept_worse_one(api):
    client, ids = api
    held, worse = ids["http://other.example/a.flac"], ids["http://club.example/m/ep_1.mp3"]
    with db.tx(TEST_DB) as c:
        c.execute("UPDATE items SET detail = jsonb_build_object('replaces', jsonb_build_array(%s::bigint)) WHERE id = %s", (worse, held))
    r = client.post(f"/api/items/{held}/resolve", json={"decision": "keep"}, headers=_h("reviewer-key-00000001"))
    assert r.status_code == 200
    with db.tx(TEST_DB) as c:
        assert c.execute("SELECT state, reason FROM items WHERE id = %s", (worse,)).fetchone() == {"state": "rejected", "reason": "duplicate"}
