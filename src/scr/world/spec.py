"""Render a world from a YAML spec, so held-out worlds can be written by someone who has never
seen the code (heldout/WRITING_SETS.md says how). The spec names sites, their rules, and items
made from the pinned materials with transformations; each item carries the writer's expected
outcome. The renderer builds the sites and turns the expectations into truth.json, which only
`scr.evaluation` reads."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .. import assets
from ..audio import decode as dec
from . import build as wb

RIGHTS_REASONS = {"robots", "tdm", "blocked_domain", "fetch"}
LICENCE_URL = {
    **wb.CC,
    "CC-BY-SA-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC-BY-ND-4.0": "https://creativecommons.org/licenses/by-nd/4.0/",
    "CC-BY-NC-SA-4.0": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
}
RATE = 44100


class SpecError(ValueError):
    pass


class Materials:
    def __init__(self) -> None:
        A = assets.corpus_assets()
        self.lj = {Path(a.path).stem: a for a in A if a.corpus == "lj"}
        self.texts = wb.lj_texts()
        self.fsdd: dict[str, list[assets.Asset]] = {}
        for a in A:
            if a.corpus == "fsdd":
                self.fsdd.setdefault(Path(a.path).stem.split("_")[1], []).append(a)
        self.esc = {Path(a.path).stem: a for a in A if a.corpus == "esc50" and a.path.endswith(".wav")}
        self.val = {f"{Path(a.path).parent.name}/{Path(a.path).stem}": a for a in A if a.corpus == "valentini"}
        self.jfk = next(a for a in A if a.corpus == "whisper")

    def render(self, m: dict[str, Any], done: dict[str, np.ndarray]) -> tuple[np.ndarray, list[dict[str, Any]], bool]:
        """(samples at RATE, true clips with text, synthetic?)"""
        gap = float(m.get("gap", 0.6))
        if "clips" in m:
            parts, clips, pos = [], [], 0.0
            for cid in m["clips"]:
                if cid not in self.lj:
                    raise SpecError(f"unknown LJSpeech clip {cid}")
                x = dec.resample(self.lj[cid].local, RATE)
                parts += [x, np.zeros(int(gap * RATE), np.float32)]
                clips.append({"start": pos, "end": pos + len(x) / RATE, "text": self.texts.get(cid, ""), "id": cid})
                pos += len(x) / RATE + gap
            return np.concatenate(parts), clips, False
        if "synthetic" in m:
            from ..audio import models

            x, r = models.synthesize(str(m["synthetic"]), voice=str(m.get("voice", "amy")))
            y = _resample(x, r)
            return y, [{"start": 0.0, "end": len(y) / RATE, "text": m["synthetic"]}], True
        if "fsdd" in m:
            spk, n = m["fsdd"]["speaker"], int(m["fsdd"].get("n", 20))
            files = sorted(self.fsdd[spk], key=lambda a: a.path)[:n]
            parts = []
            for a in files:
                parts += [dec.resample(a.local, RATE), np.zeros(int(0.35 * RATE), np.float32)]
            return np.concatenate(parts), [], False
        if "esc" in m:
            if m["esc"] not in self.esc:
                raise SpecError(f"unknown ESC-50 clip {m['esc']}")
            return dec.resample(self.esc[m["esc"]].local, RATE), [], False
        if "valentini" in m:
            kind = m["valentini"]
            parts = []
            for i in range(1, 7):
                parts += [dec.resample(self.val[f"{kind}/p287_00{i}"].local, RATE), np.zeros(int(gap * RATE), np.float32)]
            return np.concatenate(parts), [], False
        if "jfk" in m:
            return dec.resample(self.jfk.local, RATE), [], False
        if "copy_of" in m:
            if m["copy_of"] not in done:
                raise SpecError(f"copy_of {m['copy_of']}: that item must come earlier in the file")
            return done[m["copy_of"]].copy(), [], False
        raise SpecError(f"unknown material {m}")


def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE:
        return x
    from scipy.signal import resample_poly

    g = np.gcd(rate, RATE)
    return resample_poly(x, RATE // g, rate // g).astype(np.float32)


def transform(x: np.ndarray, steps: list[dict[str, Any]], mats: Materials) -> np.ndarray:
    for st in steps or []:
        ((op, arg),) = st.items()
        if op == "gain_db":
            x = x * 10 ** (float(arg) / 20)
        elif op == "clip_gain_db":
            x = np.clip(x * 10 ** (float(arg) / 20), -1, 1)
        elif op == "silence_prefix":
            x = np.concatenate([np.zeros(int(float(arg) * RATE), np.float32), x])
        elif op == "silence_suffix":
            x = np.concatenate([x, np.zeros(int(float(arg) * RATE), np.float32)])
        elif op == "lowpass_hz":
            from scipy.signal import butter, sosfiltfilt

            x = sosfiltfilt(butter(10, float(arg), fs=RATE, output="sos"), x).astype(np.float32)
        elif op == "mix_noise":
            n = dec.resample(mats.esc[arg["esc"]].local, RATE)
            n = np.tile(n, int(np.ceil(len(x) / len(n))))[: len(x)]
            ps, pn = float(np.mean(x**2)) + 1e-12, float(np.mean(n**2)) + 1e-12
            x = x + n * np.sqrt(ps / (pn * 10 ** (float(arg["snr_db"]) / 10)))
        elif op == "music_bed":
            bed = wb.music_bed(len(x) / RATE + 1, RATE, np.random.default_rng(7))[: len(x)]
            x = x + bed * 10 ** (float(arg["level_db"]) / 20) * float(np.sqrt(np.mean(x**2)) / (np.sqrt(np.mean(bed**2)) + 1e-12))
        elif op == "excerpt":
            a, b = float(arg["start"]), float(arg["end"])
            x = x[int(a * RATE) : int(b * RATE)]
        elif op == "speed":
            from scipy.signal import resample

            x = resample(x, int(len(x) / float(arg))).astype(np.float32)
        else:
            raise SpecError(f"unknown transform {op}")
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return (
        (x / peak * 0.99).astype(np.float32) if peak > 1.0 and not any("clip_gain_db" in s for s in steps or []) else x.astype(np.float32)
    )


def render(spec_path: Path, out: Path) -> Path:
    spec = yaml.safe_load(spec_path.read_text())
    if out.exists():
        shutil.rmtree(out)
    w = wb.World(out)
    mats = Materials()
    done: dict[str, np.ndarray] = {}
    urls: dict[str, str] = {}
    seeds: list[dict[str, Any]] = []
    blocked = []
    for site in spec["sites"]:
        host, kind = site["host"], site["type"]
        if not host.endswith(".example"):
            raise SpecError(f"{host}: test hosts must end in .example")
        if site.get("blocked"):
            blocked.append(host)
        if site.get("robots"):
            w.write(host, "/robots.txt", site["robots"])
        if site.get("tdmrep"):
            w.write(host, "/.well-known/tdmrep.json", json.dumps(site["tdmrep"]))
        if site.get("reserve_header_prefixes"):
            w.behaviour[host] = {"headers": {p: {"tdm-reservation": "1"} for p in site["reserve_header_prefixes"]}}
        site_lic = site.get("licence", "")
        entries = []
        for it in site["items"]:
            x, clips, synthetic = mats.render(it["material"], done)
            x = transform(x, it.get("transforms", []), mats)
            done[it["id"]] = x
            fmt = it.get("format", {})
            codec = fmt.get("codec", "mp3")
            ext = {"mp3": "mp3", "flac": "flac", "wav": "wav", "ogg": "ogg"}[codec]
            path = f"/download/{it['id']}/{it['id']}.{ext}" if kind == "archive" else it.get("path", f"/audio/{it['id']}.{ext}")
            url = w.audio(host, path, x, RATE, codec, out_rate=int(fmt.get("rate", RATE)), bitrate=fmt.get("bitrate"))
            urls[it["id"]] = url
            if it.get("transforms") and any("excerpt" in s or "speed" in s for s in it["transforms"]):
                clips = []  # true clip timings no longer hold
            expected = str(it["expected"])
            reason = expected.split(":", 1)[1] if ":" in expected else ""
            dup = it["material"].get("copy_of")
            t = wb.Truth(
                url,
                licence=it.get("licence_true", it.get("licence", site_lic)) or "LicenseRef-Unknown",
                speech=reason not in ("not_speech",),
                synthetic=synthetic,
                declared=bool(it.get("declared_synthetic")),
                duplicate_of=urls.get(dup, "") if dup else "",
                protected=reason == "protected",
                defects=[reason] if reason in ("bandwidth", "music", "noise", "clipping", "corrupt", "language") else [],
                blocked_by=reason if reason in RIGHTS_REASONS else "",
                clips=clips if it.get("transcript") == "published" or expected == "keep" else [],
                expected=expected,
            )
            w.add(t)
            entries.append((it, url))
        _site_pages(w, site, entries, seeds)
    for t in w.truth:  # a blocked domain is never contacted, whatever else is true
        if any(t.url.startswith(f"http://{h}/") for h in blocked):
            t.blocked_by, t.expected = "blocked_domain", "reject:blocked_domain"
    (out / "truth.json").write_text(json.dumps([asdict(t) for t in w.truth], indent=1))
    (out / "behaviour.json").write_text(json.dumps(w.behaviour, indent=1))
    (out / "seeds.json").write_text(json.dumps(seeds, indent=1))
    (out / "rights_override.json").write_text(json.dumps({"blocked_domains": blocked}))
    return out


def _site_pages(w: wb.World, site: dict[str, Any], entries: list[tuple[dict[str, Any], str]], seeds: list[dict[str, Any]]) -> None:
    host, kind = site["host"], site["type"]
    site_lic_url = LICENCE_URL.get(site.get("licence", ""), "")
    if kind == "html":
        links = []
        for it, url in entries:
            # a site-wide licence appears on every page of the site, as real footers do
            lic_url = LICENCE_URL.get(it.get("licence", ""), it.get("licence", "")) or site_lic_url
            if it.get("page", True):
                rel = f"/pages/{it['id']}.html"
                clip_ids = it["material"].get("clips", [])
                transcript = " ".join(wb.lj_texts().get(c, "") for c in clip_ids) if it.get("transcript") == "published" else ""
                w.write(
                    host,
                    rel,
                    wb._audio_page(
                        it.get("title", it["id"]),
                        url,
                        lic_url,
                        synthetic=bool(it.get("declared_synthetic")),
                        tdm_meta=bool(it.get("meta_tdm_reserved")),
                        text=transcript,
                    ),
                )
                links.append(f"http://{host}{rel}")
            else:
                links.append(url)
        w.write(host, "/index.html", wb._page(site.get("title", host), links, site_lic_url))
        seeds.append({"source": host.split(".")[0], "kind": "html_index", "url": f"http://{host}/index.html"})
    elif kind == "rss":
        w.write(
            host,
            "/feed.xml",
            wb._rss(
                site.get("title", host),
                site.get("licence", ""),
                [(it.get("title", it["id"]), url, it.get("licence", "")) for it, url in entries],
            ),
        )
        w.write(host, "/index.html", wb._page(site.get("title", host), [f"http://{host}/feed.xml"], ""))
        seeds.append({"source": host.split(".")[0], "kind": "html_index", "url": f"http://{host}/index.html"})
    elif kind == "archive":
        docs = []
        for it, url in entries:
            ident, name = url.split("/download/", 1)[1].split("/", 1) if "/download/" in url else (it["id"], url.rsplit("/", 1)[1])
            meta = {
                "metadata": {"identifier": ident, "mediatype": "audio", "licenseurl": LICENCE_URL.get(it.get("licence", ""), "")},
                "files": [{"name": name, "format": "VBR MP3" if name.endswith(".mp3") else "Flac" if name.endswith(".flac") else "WAVE"}],
            }
            w.write(host, f"/metadata/{ident}.json", json.dumps(meta))
            docs.append({"identifier": ident})
        w.write(host, "/advancedsearch.json", json.dumps({"response": {"docs": docs}}))
        seeds.append({"source": host.split(".")[0], "kind": "internet_archive", "url": f"http://{host}/advancedsearch.php"})
    elif kind == "librivox":
        text = "\n\n".join(" ".join(wb.lj_texts().get(c, "") for c in it["material"].get("clips", [])) for it, _ in entries)
        w.write(host, "/texts/book.txt", text)
        secs = [
            {
                "id": str(i),
                "section_number": str(i + 1),
                "title": it.get("title", it["id"]),
                "listen_url": url,
                "language": "English",
                "playtime": "0",
                "readers": [{"reader_id": "1", "display_name": "A volunteer"}],
            }
            for i, (it, url) in enumerate(entries)
        ]
        book = {
            "id": "1",
            "title": site.get("title", host),
            "url_text_source": f"http://{host}/texts/book.txt",
            "language": "English",
            "sections": secs,
        }
        w.write(host, "/api/feed/audiobooks/index.json", json.dumps({"books": [book]}))
        seeds.append(
            {"source": host.split(".")[0], "kind": "librivox", "url": f"http://{host}/api/feed/audiobooks/?format=json&extended=1"}
        )
    else:
        raise SpecError(f"{host}: unknown site type {kind}")
