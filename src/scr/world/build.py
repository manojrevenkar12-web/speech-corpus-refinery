"""The test world: a small internet of `.example` sites built from the pinned real audio.

Each site is shaped like a real kind of source (a LibriVox-style audiobook API, an Internet
Archive-style item store, Podcasting 2.0 RSS feeds, plain HTML pages) and carries the problems a
real crawl meets: robots.txt rules, TDM reservations, a blocked domain, non-commercial licences,
synthetic speech with and without a declaration, re-uploads at another bitrate, phone-band audio
stored at 44.1 kHz, music beds, clipping, noise, and servers that fail in the usual ways.

Ground truth goes to `truth.json` next to the sites. Only `scr.evaluation` reads it.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np

from .. import assets, config
from ..audio import decode as dec

SEED = 20261024
CC = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC-BY-NC-3.0": "https://creativecommons.org/licenses/by-nc/3.0/",
    "CC-BY-NC-4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
    "CC-PDM-1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
    "CC-BY-SA-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC-BY-ND-4.0": "https://creativecommons.org/licenses/by-nd/4.0/",
    "CC-BY-NC-SA-4.0": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
}
SYNTHETIC_IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"


@dataclass
class Truth:
    url: str
    licence: str  # what is true, not what the page claims
    speech: bool
    synthetic: bool = False
    declared: bool = False  # the source declares it AI-generated
    duplicate_of: str = ""  # a URL whose recording this repeats
    protected: bool = False  # contains our evaluation recordings
    defects: list[str] = field(default_factory=list)  # bandwidth, music, clipping, noise, corrupt
    blocked_by: str = ""  # robots, tdm, blocked_domain, fetch
    clips: list[dict[str, Any]] = field(default_factory=list)  # [{start, end, text}] when known
    expected: str = ""  # keep | reject:<reason>

    def decide(self, rights: dict[str, Any]) -> None:
        if self.blocked_by:
            self.expected = f"reject:{self.blocked_by}"
        elif "corrupt" in self.defects:
            self.expected = "reject:corrupt"
        elif self.licence not in rights["allowed_licences"]:
            self.expected = "reject:licence"
        elif self.synthetic and not rights.get("allow_synthetic"):
            self.expected = "reject:synthetic"
        elif self.protected:
            self.expected = "reject:protected"
        elif self.duplicate_of:
            self.expected = "reject:duplicate"
        elif not self.speech:
            self.expected = "reject:not_speech"
        elif self.defects:
            self.expected = "reject:" + self.defects[0]
        else:
            self.expected = "keep"


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.truth: list[Truth] = []
        self.rng = np.random.default_rng(SEED)
        self.behaviour: dict[str, Any] = {}

    def path(self, host: str, rel: str) -> Path:
        p = self.root / "sites" / host / rel.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write(self, host: str, rel: str, text: str) -> None:
        self.path(host, rel).write_text(text)

    def audio(
        self, host: str, rel: str, x: np.ndarray, rate: int, codec: str, out_rate: int | None = None, bitrate: str | None = None
    ) -> str:
        dec.encode(x, rate, self.path(host, rel), codec=codec, out_rate=out_rate, bitrate=bitrate)
        return f"http://{host}/{rel.lstrip('/')}"

    def add(self, t: Truth) -> Truth:
        self.truth.append(t)
        return t


# ---------------------------------------------------------------- source material


def _load(a: assets.Asset, rate: int) -> np.ndarray:
    return dec.resample(a.local, rate)


def lj_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for a in assets.corpus_assets():
        if a.corpus == "ljtext":
            for line in a.local.read_text().splitlines():
                if "|" in line:
                    path, text = line.split("|", 1)
                    out[Path(path).stem] = text.strip()
    return out


def esc_licences() -> dict[str, str]:
    """Per-clip licences from ESC-50's LICENSE file ("[1-100032-A.ogg]: ... [CC0]")."""
    lic = next(a for a in assets.corpus_assets() if a.corpus == "esc50" and a.path == "LICENSE").local.read_text()
    out = {}
    for m in re.finditer(r"\[(\d+-\d+-[A-Z])\.ogg\]:.*\[(CC0|CC-BY|CC-BY-NC)\]", lic):
        out[m.group(1)] = {"CC0": "CC0-1.0", "CC-BY": "CC-BY-3.0", "CC-BY-NC": "CC-BY-NC-3.0"}[m.group(2)]
    return out


def music_bed(seconds: float, rate: int, rng: np.random.Generator) -> np.ndarray:
    """A deterministic little tune: chord tones with harmonics and a soft beat."""
    t = np.arange(int(seconds * rate)) / rate
    roots = [220.0, 174.6, 196.0, 261.6]
    x = np.zeros_like(t)
    bar = 2.0
    for i, r in enumerate(roots * int(seconds // (bar * 4) + 1)):
        m = (t >= i * bar) & (t < (i + 1) * bar)
        for ratio, amp in ((1.0, 0.5), (1.25, 0.3), (1.5, 0.3), (2.0, 0.15)):
            x[m] += amp * np.sin(2 * np.pi * r * ratio * t[m])
    beat = (np.sin(2 * np.pi * 2.0 * t) > 0.95).astype(float) * rng.normal(0, 0.4, len(t))
    y = x + beat
    return (y / (np.max(np.abs(y)) + 1e-9)).astype(np.float32)


def join(clips: list[np.ndarray], rate: int, gap: float = 0.6) -> tuple[np.ndarray, list[tuple[float, float]]]:
    out, spans, pos = [], [], 0.0
    silence = np.zeros(int(gap * rate), np.float32)
    for c in clips:
        out += [c, silence]
        spans.append((pos, pos + len(c) / rate))
        pos += (len(c) + len(silence)) / rate
    return np.concatenate(out), spans


# ---------------------------------------------------------------- the sites


def build(root: Path | None = None, synthetic_clips: int = 24) -> Path:
    root = root or config.DATA_DIR / "world"
    if root.exists():
        shutil.rmtree(root)
    w = World(root)
    rights = config.rights()
    A = assets.corpus_assets()
    texts = lj_texts()
    sr = 22050

    lj = sorted((a for a in A if a.corpus == "lj"), key=lambda a: a.path)
    lj_audio = {Path(a.path).stem: _load(a, sr) for a in lj}
    ids = list(lj_audio)

    # 1. audiobooks.example: LibriVox-style API, public domain, book text published
    sections = [ids[0:8], ids[8:16], ids[16:24]]
    book_text = "\n\n".join(" ".join(texts[i] for i in s) for s in sections)
    w.write("audiobooks.example", "/texts/printing.txt", book_text)
    secs: list[dict[str, Any]] = []
    section_urls = []
    for n, sec in enumerate(sections, 1):
        x, spans = join([lj_audio[i] for i in sec], sr)
        rel = f"/download/printing_{n:02d}_morris_64kb.mp3"
        url = w.audio("audiobooks.example", rel, x, sr, "mp3", out_rate=44100, bitrate="128k")
        section_urls.append(url)
        clips = [{"start": a, "end": b, "text": texts[i], "id": i} for (a, b), i in zip(spans, sec, strict=True)]
        w.add(Truth(url, "LicenseRef-PublicDomain", True, protected=(n == 3), clips=clips))
        secs.append(
            {
                "id": str(9000 + n),
                "section_number": str(n),
                "title": f"Chapter {n}",
                "listen_url": url,
                "language": "English",
                "playtime": str(int(len(x) / sr)),
                "file_name": Path(rel).name,
                "readers": [{"reader_id": "18", "display_name": "Linda Johnson"}],
            }
        )
    feed = {
        "books": [
            {
                "id": "777",
                "title": "The Printing of Books (chapter 1)",
                "description": "Public-domain reading. LibriVox recordings are in the public domain.",
                "url_text_source": "http://audiobooks.example/texts/printing.txt",
                "language": "English",
                "copyright_year": "1893",
                "num_sections": str(len(secs)),
                "url_librivox": "http://audiobooks.example/printing-of-books/",
                "totaltimesecs": sum(int(s["playtime"]) for s in secs),
                "authors": [{"id": "1", "first_name": "William", "last_name": "Morris"}],
                "sections": secs,
            }
        ]
    }
    w.write("audiobooks.example", "/api/feed/audiobooks/index.json", json.dumps(feed, indent=1))
    w.write("audiobooks.example", "/robots.txt", "User-agent: *\nDisallow: /admin/\n")

    # 2. pirate.example: the same files, byte for byte, on a blocked domain
    links = []
    for n, url in enumerate(section_urls, 1):
        src = w.root / "sites" / "audiobooks.example" / url.split("/", 3)[3]
        dst = w.path("pirate.example", f"/free/printing_{n}.mp3")
        shutil.copy2(src, dst)
        u = f"http://pirate.example/free/printing_{n}.mp3"
        links.append(u)
        w.add(Truth(u, "LicenseRef-PublicDomain", True, duplicate_of=url, blocked_by="blocked_domain"))
    w.write("pirate.example", "/index.html", _page("Free audiobooks", links, CC["CC0-1.0"]))

    # 3. archive.example: Internet Archive-style items with per-item licence URLs
    items: dict[str, dict[str, Any]] = {}

    def ia_item(ident: str, licence: str, files: list[tuple[str, np.ndarray, int, str, str | None]], truth_kw: dict[str, Any]) -> None:
        meta_files = []
        for name, x, rate, codec, out_rate in files:
            fmt = {"mp3": "VBR MP3", "flac": "Flac", "wav": "WAVE", "ogg": "Ogg Vorbis"}[codec]
            url = w.audio("archive.example", f"/download/{ident}/{name}", x, rate, codec, out_rate=int(out_rate) if out_rate else None)
            meta_files.append({"name": name, "format": fmt, "source": "original"})
            w.add(Truth(url, truth_kw.pop("true_licence", licence), **truth_kw))
        items[ident] = {"metadata": {"identifier": ident, "mediatype": "audio", "licenseurl": CC.get(licence, "")}, "files": meta_files}

    jfk = next(a for a in A if a.corpus == "whisper")
    ia_item(
        "jfk-inaugural-excerpt",
        "CC-PDM-1.0",
        [("jfk.flac", _load(jfk, 44100), 44100, "flac", None)],
        {"speech": True, "defects": ["bandwidth"]},
    )
    val = {Path(a.path).parent.name + "/" + Path(a.path).stem: a for a in A if a.corpus == "valentini"}
    clean = [_load(val[f"clean/p287_00{i}"], 16000) for i in range(1, 7)]
    noisy = [_load(val[f"noisy/p287_00{i}"], 16000) for i in range(1, 7)]
    xc, _ = join(clean, 16000)
    xn, _ = join(noisy, 16000)
    ia_item("p287-read-speech", "CC-BY-4.0", [("p287_clean.flac", xc, 16000, "flac", None)], {"speech": True})
    ia_item("p287-read-speech-cafe", "CC-BY-4.0", [("p287_noisy.flac", xn, 16000, "flac", None)], {"speech": True, "defects": ["noise"]})
    # a re-upload of chapter 2: 32 kbps, 6 dB quieter, 2 s of silence in front
    x2, _ = join([lj_audio[i] for i in sections[1]], sr)
    x2 = np.concatenate([np.zeros(2 * sr, np.float32), 0.5 * x2])
    ia_item(
        "printing-of-books-ch2-reupload",
        "CC-PDM-1.0",
        [("chapter2.mp3", x2, sr, "mp3", None)],
        {"speech": True, "duplicate_of": section_urls[1]},
    )
    # phone-band voice messages (8 kHz recordings) stored as 44.1 kHz WAV
    fsdd: dict[str, list[assets.Asset]] = {}
    for a in A:
        if a.corpus == "fsdd":
            fsdd.setdefault(Path(a.path).stem.split("_")[1], []).append(a)
    for spk, files in sorted(fsdd.items()):
        x, _ = join([_load(a, 8000) for a in sorted(files, key=lambda a: a.path)], 8000, gap=0.35)
        ia_item(
            f"voice-messages-{spk}", "CC-BY-SA-4.0", [(f"{spk}.wav", x, 8000, "wav", "44100")], {"speech": True, "defects": ["bandwidth"]}
        )
    # field recordings with their real per-clip licences
    esc_lic = esc_licences()
    esc_meta = {
        r["filename"]: r["category"]
        for r in csv.DictReader(io.StringIO(next(a for a in A if a.corpus == "esc50" and a.path.endswith(".csv")).local.read_text()))
    }
    for a in sorted((a for a in A if a.corpus == "esc50" and a.path.endswith(".wav")), key=lambda a: a.path)[::2]:
        stem = Path(a.path).stem
        lic = esc_lic.get(stem.rsplit("-", 1)[0], "CC-BY-NC-3.0")
        cat = esc_meta[Path(a.path).name]
        ia_item(f"field-{stem}-{cat}", lic, [(f"{stem}.flac", _load(a, 44100), 44100, "flac", None)], {"speech": False})
    w.write("archive.example", "/advancedsearch.json", json.dumps({"response": {"docs": [{"identifier": k} for k in items]}}, indent=1))
    for k, v in items.items():
        w.write("archive.example", f"/metadata/{k}.json", json.dumps(v, indent=1))

    # 4. podcasts.example: Podcasting 2.0 RSS with <podcast:license>
    rng = w.rng
    episodes_by: dict[str, list[tuple[str, str]]] = {"reading-club": [], "late-night-readings": [], "ai-news-daily": []}
    clean_ep, _ = join([lj_audio[i] for i in ids[24:27]], sr)
    u = w.audio("podcasts.example", "/media/rc-001.mp3", clean_ep, sr, "mp3", out_rate=44100, bitrate="128k")
    w.add(Truth(u, "CC-BY-4.0", True, clips=_clips(ids[24:27], texts, lj_audio, sr)))
    episodes_by["reading-club"].append(("Episode 1", u))
    bed_ep, _ = join([lj_audio[i] for i in ids[27:29]], sr)
    bed = music_bed(len(bed_ep) / sr + 1, sr, rng)[: len(bed_ep)]
    u = w.audio("podcasts.example", "/media/rc-002.mp3", 0.8 * bed_ep + 0.35 * bed, sr, "mp3", out_rate=44100, bitrate="128k")
    w.add(Truth(u, "CC-BY-4.0", True, defects=["music"]))
    episodes_by["reading-club"].append(("Episode 2 (with our new theme tune)", u))
    clip_ep = np.clip(lj_audio[ids[29]] * 8.0, -1.0, 1.0)
    u = w.audio("podcasts.example", "/media/rc-003.wav", clip_ep, sr, "wav", out_rate=44100)
    w.add(Truth(u, "CC-BY-4.0", True, defects=["clipping"]))
    episodes_by["reading-club"].append(("Episode 3 (recorded too hot)", u))
    x1, _ = join([lj_audio[i] for i in sections[0]], sr)
    u = w.audio("podcasts.example", "/media/rc-004.mp3", 0.9 * x1, sr, "mp3", out_rate=44100, bitrate="96k")
    w.add(Truth(u, "CC-BY-4.0", True, duplicate_of=section_urls[0]))
    episodes_by["reading-club"].append(("Episode 4 (rerun of the chapter 1 reading)", u))
    nc_ep, _ = join([lj_audio[i] for i in ids[30:32]], sr)
    u = w.audio("podcasts.example", "/media/lnr-001.mp3", nc_ep, sr, "mp3", out_rate=44100, bitrate="128k")
    w.add(Truth(u, "CC-BY-NC-4.0", True))
    episodes_by["late-night-readings"].append(("Night 1", u))

    # synthetic narration: declared on voices.example, undeclared in one podcast
    synth = _synthetic(texts, synthetic_clips)
    half = len(synth) // 2
    for n, (x, rate, text) in enumerate(synth[:half]):
        u = w.audio("podcasts.example", f"/media/aind-{n:03d}.mp3", x, rate, "mp3", out_rate=44100, bitrate="128k")
        w.add(Truth(u, "CC-BY-4.0", True, synthetic=True, clips=[{"start": 0.0, "end": len(x) / rate, "text": text}]))
        episodes_by["ai-news-daily"].append((f"AI news {n + 1}", u))
    feeds = {"reading-club": "CC-BY-4.0", "late-night-readings": "CC-BY-NC-4.0", "ai-news-daily": "CC-BY-4.0"}
    for name, lic in feeds.items():
        w.write("podcasts.example", f"/feeds/{name}.xml", _rss(name, lic, episodes_by[name]))
    w.write("podcasts.example", "/index.html", _page("Podcasts", [f"http://podcasts.example/feeds/{n}.xml" for n in feeds], ""))

    pages = []
    for n, (x, rate, text) in enumerate(synth[half:]):
        u = w.audio("voices.example", f"/clips/v{n:03d}.mp3", x, rate, "mp3", out_rate=44100, bitrate="128k")
        w.add(Truth(u, "CC0-1.0", True, synthetic=True, declared=True))
        rel = f"/clips/v{n:03d}.html"
        w.write("voices.example", rel, _audio_page(f"Voice sample {n}", u, CC["CC0-1.0"], synthetic=True, text=text))
        pages.append(f"http://voices.example{rel}")
    w.write("voices.example", "/index.html", _page("Synthetic voice samples", pages, ""))

    # 5. reserved.example: TDM reservations by file, header and meta tag
    open_pages: list[str] = []
    res_pages: list[str] = []
    w.write(
        "reserved.example",
        "/.well-known/tdmrep.json",
        json.dumps([{"location": "/studio/*", "tdm-reservation": 1}, {"location": "/open/", "tdm-reservation": 0}]),
    )
    for n, i in enumerate(range(0, 6)):
        x, _ = join([_load(fsdd["george"][i], 16000)], 16000)
        area = "studio" if n < 2 else "press" if n < 4 else "open"
        u = w.audio("reserved.example", f"/{area}/take{n}.flac", np.tile(x, 8), 16000, "flac")
        blocked = "tdm" if area in ("studio", "press") else ""
        page = f"/{area}/take{n}.html"
        meta_reserved = area == "press" and n == 3
        w.write("reserved.example", page, _audio_page(f"Take {n}", u, CC["CC-BY-4.0"], tdm_meta=meta_reserved))
        w.add(Truth(u, "CC-BY-4.0", True, blocked_by=blocked, defects=["bandwidth"]))
        (res_pages if blocked else open_pages).append(f"http://reserved.example{page}")
    w.behaviour["reserved.example"] = {"headers": {"/press/": {"tdm-reservation": "1"}}}
    w.write("reserved.example", "/index.html", _page("Studio takes", open_pages + res_pages, ""))

    # 6. private.example: robots.txt keeps us out of /recordings/ except /recordings/public/
    w.write(
        "private.example",
        "/robots.txt",
        "User-agent: *\nAllow: /\n\nUser-agent: ScrBot\nDisallow: /recordings/\nAllow: /recordings/public/\n",
    )
    priv_links = []
    for n, (area, i) in enumerate([("recordings/public", 0), ("recordings/members", 2), ("recordings/members", 4)]):
        a = sorted(fsdd["lucas"], key=lambda a: a.path)[i]
        x = np.tile(_load(a, 16000), 10)
        u = w.audio("private.example", f"/{area}/r{n}.flac", x, 16000, "flac")
        w.add(Truth(u, "CC-BY-SA-4.0", True, blocked_by="" if "public" in area else "robots", defects=["bandwidth"]))
        priv_links.append(u)
    w.write("private.example", "/index.html", _page("Recordings", priv_links, CC["CC-BY-SA-4.0"]))

    # 7. flaky.example: servers failing in the usual ways (content: ESC-50 CC0 clips, not speech)
    cc0 = [
        a for a in A if a.corpus == "esc50" and a.path.endswith(".wav") and esc_lic.get(Path(a.path).stem.rsplit("-", 1)[0]) == "CC0-1.0"
    ][:6]
    flaky: dict[str, dict[str, Any]] = {
        "rate-limited.flac": {"fail": [429, 429], "retry_after": 1},
        "unavailable.flac": {"fail": [503]},
        "slow.flac": {"delay_first": 8},
        "truncated.flac": {"truncate_first": True},
        "not-audio.mp3": {"html_body": True},
        "loop.flac": {"redirect_loop": True},
    }
    flinks = []
    for (name, beh), a in zip(flaky.items(), cc0, strict=False):
        u = w.audio("flaky.example", f"/files/{name}", _load(a, 44100), 44100, "flac" if name.endswith(".flac") else "mp3")
        flinks.append(u)
        corrupt = beh.get("html_body", False)
        blocked = "fetch" if beh.get("redirect_loop") else ""
        w.add(Truth(u, "CC0-1.0", False, defects=["corrupt"] if corrupt else [], blocked_by=blocked))
    w.behaviour["flaky.example"] = {"files": {f"/files/{k}": v for k, v in flaky.items()}}
    w.write("flaky.example", "/index.html", _page("Sound files", flinks, CC["CC0-1.0"]))

    for t in w.truth:
        t.decide(rights)
    (root / "truth.json").write_text(json.dumps([asdict(t) for t in w.truth], indent=1))
    (root / "behaviour.json").write_text(json.dumps(w.behaviour, indent=1))
    (root / "seeds.json").write_text(
        json.dumps(
            [
                {
                    "source": "audiobooks",
                    "kind": "librivox",
                    "url": "http://audiobooks.example/api/feed/audiobooks/?format=json&extended=1",
                },
                {"source": "archive", "kind": "internet_archive", "url": "http://archive.example/advancedsearch.php"},
                {"source": "podcasts", "kind": "html_index", "url": "http://podcasts.example/index.html"},
                {"source": "voices", "kind": "html_index", "url": "http://voices.example/index.html"},
                {"source": "reserved", "kind": "html_index", "url": "http://reserved.example/index.html"},
                {"source": "private", "kind": "html_index", "url": "http://private.example/index.html"},
                {"source": "pirate", "kind": "html_index", "url": "http://pirate.example/index.html"},
                {"source": "flaky", "kind": "html_index", "url": "http://flaky.example/index.html"},
            ],
            indent=1,
        )
    )
    return root


def _clips(ids: list[str], texts: dict[str, str], audio: dict[str, np.ndarray], rate: int, gap: float = 0.6) -> list[dict[str, Any]]:
    out, pos = [], 0.0
    for i in ids:
        d = len(audio[i]) / rate
        out.append({"start": pos, "end": pos + d, "text": texts[i], "id": i})
        pos += d + gap
    return out


def _synthetic(texts: dict[str, str], n: int) -> list[tuple[np.ndarray, int, str]]:
    from ..audio import models

    # narration from the printing-history chapter (LJ001), sentences beyond the 32 whose recordings we use
    picked = [t for k, t in sorted(texts.items()) if k.startswith("LJ001-") and int(k[6:]) > 40 and 60 < len(t) < 160][:n]
    out = []
    for t in picked:
        x, rate = models.synthesize(t)
        out.append((x, rate, t))
    return out


def _page(title: str, links: list[str], licence_url: str) -> str:
    lic = f'<link rel="license" href="{licence_url}">' if licence_url else ""
    items = "\n".join(f'<li><a href="{escape(u)}">{escape(u.rsplit("/", 1)[-1])}</a></li>' for u in links)
    return (
        f"<!doctype html><html><head><title>{escape(title)}</title>{lic}</head><body><h1>{escape(title)}</h1><ul>{items}</ul></body></html>"
    )


def _audio_page(title: str, audio_url: str, licence_url: str, synthetic: bool = False, tdm_meta: bool = False, text: str = "") -> str:
    ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "AudioObject",
        "name": title,
        "contentUrl": audio_url,
        "license": licence_url,
    }
    if synthetic:
        ld["digitalSourceType"] = SYNTHETIC_IPTC
    if text:
        ld["transcript"] = text
    meta = '<meta name="tdm-reservation" content="1">' if tdm_meta else ""
    return (
        f"<!doctype html><html><head><title>{escape(title)}</title>{meta}"
        f'<link rel="license" href="{licence_url}">'
        f'<script type="application/ld+json">{json.dumps(ld)}</script></head>'
        f'<body><h1>{escape(title)}</h1><audio src="{escape(audio_url)}" controls></audio></body></html>'
    )


def _rss(name: str, licence: str, episodes: Sequence[tuple[str, ...]]) -> str:
    def item(e: tuple[str, ...]) -> str:
        t, u = e[0], e[1]
        own = e[2] if len(e) > 2 else ""
        lic = f'<podcast:license url="{CC.get(own, "")}">{own.lower()}</podcast:license>' if own else ""
        return f'<item><title>{escape(t)}</title><guid>{escape(u)}</guid>{lic}<enclosure url="{escape(u)}" type="audio/mpeg" length="0"/></item>'

    items = "".join(item(e) for e in episodes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:podcast="https://podcastindex.org/namespace/1.0">'
        f"<channel><title>{escape(name)}</title><link>http://podcasts.example/</link>"
        f'<podcast:license url="{CC.get(licence, "")}">{licence.lower()}</podcast:license>'
        f"<language>en</language>{items}</channel></rss>"
    )
