"""Pure functions: segmentation, duplicate ranking, fingerprints, alignment, splits, parsers, storage."""

from __future__ import annotations

import json

import numpy as np
import pytest
from scipy.signal import resample

from scr import align, config, cost, process, release
from scr.api import wilson
from scr.audio import fingerprint as fp
from scr.audio.models import Span
from scr.crawl import connectors
from scr.store import LocalStore, blob_key

SEG = {"min_seconds": 1.5, "max_seconds": 20.0, "pad_seconds": 0.1}


# ------------------------------------------------------------------ segmentation


def test_short_regions_join_across_short_gaps_and_get_padding():
    spans = [Span(0.5, 1.0), Span(1.2, 2.4), Span(5.0, 9.0)]
    assert process.merge_spans(spans, SEG, total=9.05) == [(0.4, 2.5), (4.9, 9.05)]


def test_nothing_exceeds_the_maximum_and_lone_blips_are_dropped():
    spans = [Span(i * 1.1, i * 1.1 + 1.0) for i in range(30)] + [Span(40.0, 40.6)]
    out = process.merge_spans(spans, SEG, total=60)
    assert out and all(b - a <= SEG["max_seconds"] + 2 * SEG["pad_seconds"] for a, b in out)
    assert all(b - a >= SEG["min_seconds"] for a, b in out)
    assert not [s for s in out if s[0] > 39]  # the 0.6 s blip at 40 s stands alone and is too short


def test_long_gaps_are_never_bridged():
    out = process.merge_spans([Span(0, 1.0), Span(1.6, 2.0)], SEG, total=10)
    assert out == []  # 0.6 s apart: not joined, and each alone is too short


# ------------------------------------------------------------------ duplicates: which copy is better


def test_quality_follows_the_policy_order_tier_then_snr_then_bitrate():
    full_noisy_hi = process.quality_key(11000, 28, 32000)
    wide_clean_hi = process.quality_key(8000, 45, 40000)
    assert full_noisy_hi > wide_clean_hi  # tier first
    assert process.quality_key(11000, 40, 8000) > process.quality_key(11000, 30, 32000)  # then SNR
    assert process.quality_key(11000, 40, 16000) > process.quality_key(11000, 41, 8000)  # within 5 dB, bitrate decides
    assert process.quality_key(6000, 50, 64000)[0] == 0.0  # below wide


def test_speed_factors_cover_both_directions_nearest_first():
    f = process.speed_factors(0.10, 0.005)
    assert len(f) == 40 and f[0] == pytest.approx(1.005) and f[1] == pytest.approx(1 / 1.005)
    assert max(f) == pytest.approx(1.10) and min(f) == pytest.approx(1 / 1.10)


# ------------------------------------------------------------------ fingerprints


from .conftest import HAVE_CORPORA  # noqa: E402

needs_corpora = pytest.mark.skipif(not HAVE_CORPORA, reason="pinned corpora missing: run `scr fetch`")
RATE = 8000


def _speech(*clips: str) -> np.ndarray:
    from scr import assets
    from scr.audio import decode

    files = {a.local.name: a.local for a in assets.corpus_assets()}
    return np.concatenate([decode.resample(files[f"{c}.wav"], RATE) for c in clips]).astype(np.float32)


def _roundtrip(x: np.ndarray, tmp_path, codec: str = "mp3", bitrate: str = "64k") -> np.ndarray:
    from scr.audio import decode

    f = tmp_path / f"copy.{codec}"
    decode.encode(x, RATE, f, codec=codec, out_rate=44100, bitrate=bitrate)
    return decode.resample(f, RATE)


def _match(query: np.ndarray, index: dict[int, np.ndarray], speed: float = 1.0) -> dict[int, fp.Match]:
    rows, sizes = [], {}
    for item, x in index.items():
        lm = fp.landmarks(x)
        sizes[item] = len(lm)
        rows += [(h, item, t) for h, t in lm]
    pk = fp.peaks(query)
    q = fp.hashes(fp.at_speed(pk, speed) if speed != 1.0 else pk)
    return {m.other: m for m in fp.best_matches(q, rows, sizes)}


def _is_copy(m: fp.Match | None, speed: bool = False) -> bool:
    d = config.settings()["dedup"]
    return (
        m is not None and m.votes >= int(d["min_matches"]) and m.ratio >= float(d["speed_min_match_ratio" if speed else "min_match_ratio"])
    )


@needs_corpora
def test_a_reencoded_quieter_offset_copy_is_found_and_other_speech_is_not(tmp_path):
    a, b = _speech("LJ001-0025", "LJ001-0026"), _speech("LJ001-0028", "LJ001-0029")
    copy = _roundtrip(np.concatenate([np.zeros(RATE * 2, np.float32), a * 0.3]), tmp_path)
    m = _match(copy, {1: a, 2: b})
    assert _is_copy(m.get(1)) and m[1].offset_seconds == pytest.approx(-2.0, abs=0.05)
    assert not _is_copy(m.get(2))


@needs_corpora
def test_an_excerpt_is_found_in_the_recording_it_came_from(tmp_path):
    a = _speech("LJ001-0025", "LJ001-0026", "LJ001-0027")
    m = _match(_roundtrip(a[RATE * 4 : RATE * 10], tmp_path, "ogg", "96k"), {1: a, 2: _speech("LJ001-0030", "LJ001-0031")})
    assert _is_copy(m.get(1)) and not _is_copy(m.get(2))


@needs_corpora
@pytest.mark.parametrize("speed", [1.08, 1 / 1.07])
def test_a_faster_or_slower_copy_is_found_once_the_peaks_are_rescaled(speed, tmp_path):
    a = _speech("LJ001-0025", "LJ001-0026")
    changed = _roundtrip(resample(a, int(len(a) / speed)).astype(np.float32), tmp_path)  # played `speed` times faster
    assert not _is_copy(_match(changed, {1: a}).get(1))  # plain landmarks do not survive the change
    assert _is_copy(_match(changed, {1: a}, speed=speed).get(1), speed=True)


# ------------------------------------------------------------------ alignment to published text


BOOK = (
    "Printing, in the only sense with which we are at present concerned, differs from most if not from all "
    "the arts and crafts represented in the Exhibition in being comparatively modern. For although the Chinese "
    "took impressions from wood blocks engraved in relief for centuries before the woodcutters of the Netherlands."
)


def test_alignment_finds_the_span_and_keeps_published_punctuation():
    a = align.Book(BOOK).align("differs from most if not from all the arts and crafts represented in the exhibition")
    assert a is not None and a.cer < 0.05
    assert a.text.startswith("differs") and a.text.endswith("Exhibition")


def test_alignment_covers_words_asr_dropped_at_the_edges():
    a = align.Book(BOOK).align("from most if not from all the arts and crafts represented in the")
    assert a is not None and "arts and crafts" in a.text and a.cer < 0.2


def test_speech_that_is_not_the_text_scores_a_high_error_rate():
    a = align.Book(BOOK).align("the weather today is cold and wet with strong winds from the north")
    assert a is None or a.cer > 0.25


def test_cer_normalises_case_and_punctuation():
    assert align.cer("Hello, World!", "hello world") == 0.0
    assert align.cer("", "") == 0.0 and align.cer("", "x") == 1.0
    assert align.cer("abcd", "abed") == pytest.approx(0.25)


# ------------------------------------------------------------------ speakers and splits


def test_speakers_cluster_by_voice_embedding():
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(3, 64))
    emb = np.vstack([c + rng.normal(scale=0.15, size=(10, 64)) for c in centres])
    labels = release.cluster_speakers(emb, threshold=0.55)
    assert len(set(labels)) == 3
    assert all(len(set(labels[i * 10 : (i + 1) * 10])) == 1 for i in range(3))
    assert release.cluster_speakers(np.zeros((0, 64)), 0.55) == [] and release.cluster_speakers(emb[:1], 0.55) == [0]


def test_splits_are_speaker_disjoint_and_near_their_targets():
    hours = {f"s{i}": h for i, h in enumerate([5, 4, 3, 2, 2, 1, 1, 1, 0.5, 0.5])}
    fr = {"train": 0.8, "dev": 0.1, "test": 0.1}
    out = release.assign_splits(hours, fr)
    assert set(out) == set(hours)  # each speaker in exactly one split
    got = {k: sum(h for s, h in hours.items() if out[s] == k) / sum(hours.values()) for k in fr}
    assert got["train"] >= 0.6 and got["dev"] > 0 and got["test"] > 0
    assert release.assign_splits({"only": 1.0}, fr) == {"only": "train"}


# ------------------------------------------------------------------ spot checks and cost


def test_wilson_interval():
    assert wilson(0, 0) is None
    lo, hi = wilson(9, 10)  # type: ignore[misc]
    assert 0.55 < lo < 0.6 and 0.98 < hi <= 1.0
    lo, hi = wilson(50, 100)  # type: ignore[misc]
    assert lo == pytest.approx(0.404, abs=0.002) and hi == pytest.approx(0.596, abs=0.002)


def test_cost_uses_the_configured_cloud_run_prices():
    p = config.pricing()
    usd = cost._compute_usd(3600.0, p)
    job = p["cloud_run_job"]
    per_vcpu_second = job["vcpu_second"] + job["gib_second"] * job["gib"] / job["vcpu"]
    assert usd == pytest.approx(3600 * per_vcpu_second, rel=1e-6)


# ------------------------------------------------------------------ parsers


def test_rss_item_licence_overrides_the_channel():
    feed = f"""<rss xmlns:podcast="{connectors.PODCAST_NS}"><channel><title>Club</title><language>en</language>
      <podcast:license url="https://creativecommons.org/licenses/by/4.0/">cc-by-4.0</podcast:license>
      <item><title>One</title><enclosure url="/m/1.mp3" type="audio/mpeg"/></item>
      <item><title>Two</title><podcast:license>cc-by-nc-4.0</podcast:license><enclosure url="/m/2.mp3"/></item>
      <item><title>No audio</title></item></channel></rss>""".encode()
    a, b = connectors.rss("http://club.example/feed.xml", feed)
    assert a.url == "http://club.example/m/1.mp3" and a.meta["licence"].endswith("/by/4.0/")
    assert a.meta["licence_evidence"] == "podcast:license on the channel"
    assert b.meta["licence"] == "cc-by-nc-4.0" and b.meta["licence_evidence"] == "podcast:license on the item"


def test_html_reads_schema_org_licence_synthetic_declaration_and_transcript():
    ld = {
        "@type": "AudioObject",
        "contentUrl": "/a/voice.mp3",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
        "transcript": "Hello there.",
    }
    page = f"""<html><head><link rel="license" href="https://creativecommons.org/licenses/by/4.0/">
      <script type="application/ld+json">{json.dumps(ld)}</script></head><body>
      <audio src="/a/voice.mp3"></audio><a href="/a/plain.flac">plain</a><a href="http://other.example/x.html">x</a>
      <a href="/next.html">next</a></body></html>""".encode()
    found = {f.url: f for f in connectors.html("http://site.example/index.html", page)}
    voice, plain = found["http://site.example/a/voice.mp3"], found["http://site.example/a/plain.flac"]
    assert voice.meta["synthetic_declared"] and voice.meta["licence"].endswith("/zero/1.0/") and voice.meta["transcript"] == "Hello there."
    assert not plain.meta["synthetic_declared"] and plain.meta["licence_evidence"] == 'page <link rel="license">'
    assert "http://other.example/x.html" not in found  # pages on other hosts are not followed
    assert found["http://site.example/next.html"].kind == "page"


def test_librivox_sections_are_public_domain_audio():
    body = json.dumps(
        {
            "books": [
                {
                    "title": "Book",
                    "url_text_source": "http://t.example/b.txt",
                    "sections": [
                        {"listen_url": "http://a.example/1.mp3", "title": "One", "readers": [{"display_name": "R"}]},
                        {"title": "No url"},
                    ],
                }
            ]
        }
    ).encode()
    out = [f for f in connectors.librivox("http://a.example/api", body) if f.kind == "audio"]
    assert [f.url for f in out] == ["http://a.example/1.mp3"]
    assert out[0].meta["licence"] == connectors.LIBRIVOX_LICENCE


def test_kind_of():
    assert connectors.kind_of("http://x.example/a/b.FLAC") == "audio"
    assert connectors.kind_of("http://x.example/feed.xml") == "feed"
    assert connectors.kind_of("http://x.example/feed/") == "feed"
    assert connectors.kind_of("http://x.example/feed.html") == "page"


# ------------------------------------------------------------------ storage


def test_local_store_is_content_addressed_and_contained(tmp_path):
    s = LocalStore(tmp_path / "store")
    src = tmp_path / "a.bin"
    src.write_bytes(b"abc")
    sha = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    s.put_file(sha, src)
    s.put_file(sha, src)  # idempotent
    assert s.exists(sha) and (tmp_path / "store" / blob_key(sha)).read_bytes() == b"abc"
    assert s.delete(sha) and not s.exists(sha) and not s.delete(sha)
    with pytest.raises(ValueError):
        blob_key("../../etc/passwd")
    with pytest.raises(ValueError):
        s.put_bytes("../outside.txt", b"x")


# ------------------------------------------------------------------ clipping survives lossy codecs


@needs_corpora
@pytest.mark.parametrize(("codec", "bitrate"), [("flac", None), ("mp3", "128k"), ("ogg", "96k")])
def test_clipping_is_measured_through_lossy_codecs_and_loud_clean_speech_passes(codec, bitrate, tmp_path):
    from scr.audio import decode, probes

    x = _speech("LJ001-0028", "LJ001-0029")
    x = x / np.abs(x).max()
    limit = float(config.settings()["decide"]["max_clipped_ratio"])
    level = float(config.settings()["audio"]["clip_level"])

    def measured(y: np.ndarray) -> float:
        f = tmp_path / f"y.{codec}"
        decode.encode(y.astype(np.float32), RATE, f, codec=codec, out_rate=44100, bitrate=bitrate)
        return probes.clipped_ratio(decode.resample(f, 16000), level)

    assert measured(x * 0.999) < limit  # peak-normalised, unclipped
    assert measured(x * 0.3) == 0.0
    clipped = np.clip(x * 10 ** (9 / 20), -1, 1)
    truth = float(np.mean(np.abs(x * 10 ** (9 / 20)) >= 1))
    got = measured(clipped)
    assert got > limit and truth / 2 < got < truth * 2


# ------------------------------------------------------------------ Google Cloud Storage, against a fake that enforces preconditions


class _FakeBlob:
    def __init__(self, objects: dict[str, bytes], key: str) -> None:
        self.objects, self.key = objects, key

    def upload_from_filename(self, path: str, if_generation_match: int | None = None) -> None:
        from google.api_core.exceptions import PreconditionFailed

        if if_generation_match == 0 and self.key in self.objects:
            raise PreconditionFailed("exists")
        self.objects[self.key] = open(path, "rb").read()  # noqa: SIM115

    def upload_from_string(self, body: bytes) -> None:
        self.objects[self.key] = body

    def download_to_filename(self, path: str) -> None:
        open(path, "wb").write(self.objects[self.key])  # noqa: SIM115

    def exists(self) -> bool:
        return self.key in self.objects

    def delete(self) -> None:
        del self.objects[self.key]


class _FakeClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def bucket(self, name: str):
        objects = self.objects

        class B:
            def blob(self, key: str) -> _FakeBlob:
                return _FakeBlob(objects, key)

        return B()


def test_gcs_store_writes_once_and_checks_content_on_read(tmp_path):
    import hashlib

    from scr.store import GcsStore

    client = _FakeClient()
    s = GcsStore("raw", client=client)
    f = tmp_path / "a"
    f.write_bytes(b"audio")
    sha = hashlib.sha256(b"audio").hexdigest()
    s.put_file(sha, f)
    s.put_file(sha, f)  # second write is a no-op, not an overwrite
    assert s.exists(sha) and s.get_file(sha, tmp_path / "out" / sha).read_bytes() == b"audio"
    client.objects[blob_key(sha)] = b"tampered"
    with pytest.raises(OSError):
        s.get_file(sha, tmp_path / "out2" / sha)
    assert s.delete(sha) and not s.delete(sha)


def test_publishing_a_release_twice_fails_instead_of_overwriting(tmp_path):
    from google.api_core.exceptions import PreconditionFailed

    from scr.store import publish_dir

    rel = tmp_path / "v1"
    (rel / "sub").mkdir(parents=True)
    (rel / "manifest.parquet").write_bytes(b"m")
    (rel / "sub" / "x.txt").write_bytes(b"x")
    client = _FakeClient()
    assert publish_dir("releases", "v1", rel, client=client) == 2
    assert set(client.objects) == {"v1/manifest.parquet", "v1/sub/x.txt"}
    with pytest.raises(PreconditionFailed):
        publish_dir("releases", "v1", rel, client=client)


def test_an_excerpt_never_replaces_the_fuller_recording_however_clean():
    full = (*process.quality_key(11000, 39, 16000), 11.0)
    clean_excerpt = (*process.quality_key(11000, 45, 20000), 5.5)
    assert process.outranks(full, clean_excerpt, 0.8) and not process.outranks(clean_excerpt, full, 0.8)
    # within 80% (padding, a speed change) quality decides as before
    slower_better = (*process.quality_key(11000, 45, 20000), 10.0)
    assert process.outranks(slower_better, full, 0.8) and not process.outranks(full, slower_better, 0.8)
    # copies indexed without speech seconds compare on quality alone
    assert process.outranks((2.0, 8.0, 16000.0), clean_excerpt, 0.8) is False
