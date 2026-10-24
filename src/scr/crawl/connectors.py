"""Turning a fetched document into new URLs, with what the source says about each one.

Shapes follow the real services: the LibriVox API (`books[].sections[].listen_url`), the
Internet Archive (`advancedsearch.php`, `/metadata/<id>`, `/download/<id>/<file>`,
`metadata.licenseurl`), Podcasting 2.0 RSS (`<podcast:license>`, `<enclosure>`), and HTML pages
(`<a href>`, `<audio src>`, `<link rel="license">`, schema.org JSON-LD with `license` and IPTC
`digitalSourceType`)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

AUDIO_EXT = (".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac")
SYNTHETIC_TYPES = ("trainedalgorithmicmedia", "compositesynthetic", "algorithmicmedia")
PODCAST_NS = "https://podcastindex.org/namespace/1.0"
LIBRIVOX_LICENCE = "LicenseRef-PublicDomain"
LIBRIVOX_EVIDENCE = "LibriVox: all recordings are released into the public domain"


@dataclass
class Found:
    url: str
    kind: str  # api | feed | page | audio | text
    parser: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def kind_of(url: str) -> str:
    path = urlsplit(url).path.lower()
    if path.endswith(AUDIO_EXT):
        return "audio"
    if path.endswith((".xml", ".rss")) or ("/feed" in path and not path.endswith((".html", ".htm"))):
        return "feed"
    return "page"


# ---------------------------------------------------------------- LibriVox


def librivox(url: str, body: bytes, page_size: int = 50) -> list[Found]:
    doc = json.loads(body)
    books = doc.get("books") or []
    out: list[Found] = []
    for b in books:
        for s in b.get("sections") or []:
            u = s.get("listen_url")
            if not u:
                continue
            readers = ", ".join(r.get("display_name", "") for r in s.get("readers") or [])
            out.append(
                Found(
                    u,
                    "audio",
                    meta={
                        "licence": LIBRIVOX_LICENCE,
                        "licence_evidence": LIBRIVOX_EVIDENCE,
                        "title": f"{b.get('title', '')}: {s.get('title', '')}",
                        "attribution": f"Read by {readers} for LibriVox" if readers else "LibriVox",
                        "text_url": b.get("url_text_source") or None,
                        "language": s.get("language") or b.get("language"),
                    },
                )
            )
    if len(books) >= page_size:
        parts = urlsplit(url)
        q = dict(parse_qsl(parts.query))
        q["offset"] = str(int(q.get("offset", 0)) + page_size)
        q["limit"] = str(page_size)
        out.append(Found(urlunsplit(parts._replace(query=urlencode(q))), "api", "librivox"))
    return out


# ---------------------------------------------------------------- Internet Archive

IA_PREFERENCE = ["Flac", "24bit Flac", "WAVE", "VBR MP3", "128Kbps MP3", "64Kbps MP3", "Ogg Vorbis"]


def ia_search(url: str, body: bytes, rows: int = 50) -> list[Found]:
    doc = json.loads(body).get("response", {})
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    out = [Found(f"{base}/metadata/{d['identifier']}", "api", "ia_metadata") for d in doc.get("docs", []) if d.get("identifier")]
    start, total = int(doc.get("start", 0)), int(doc.get("numFound", 0))
    if start + rows < total:
        parts = urlsplit(url)
        q = dict(parse_qsl(parts.query))
        q["page"] = str(start // rows + 2)
        q["rows"] = str(rows)
        out.append(Found(urlunsplit(parts._replace(query=urlencode(q))), "api", "ia_search"))
    return out


def ia_metadata(url: str, body: bytes) -> list[Found]:
    doc = json.loads(body)
    meta = doc.get("metadata") or {}
    ident = meta.get("identifier")
    if not ident:
        return []
    files = [f for f in doc.get("files") or [] if f.get("format") in IA_PREFERENCE]
    if not files:
        return []
    best = min(files, key=lambda f: IA_PREFERENCE.index(f["format"]))  # one copy per item: IA derives MP3/OGG from the original
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    creator = meta.get("creator")
    creator = ", ".join(creator) if isinstance(creator, list) else creator
    return [
        Found(
            f"{base}/download/{ident}/{best['name']}",
            "audio",
            meta={
                "licence": meta.get("licenseurl") or "",
                "licence_evidence": f"archive.org metadata licenseurl of {ident}"
                if meta.get("licenseurl")
                else "no licenseurl in item metadata",
                "title": meta.get("title") or ident,
                "attribution": f"{creator} via the Internet Archive ({ident})" if creator else f"Internet Archive item {ident}",
                "language": meta.get("language"),
            },
        )
    ]


# ---------------------------------------------------------------- RSS


def rss(url: str, body: bytes) -> list[Found]:
    root = ET.fromstring(body)  # noqa: S314 - feeds are untrusted but ElementTree does not resolve external entities
    ch = root.find("channel")
    if ch is None:
        return []

    def lic(el: ET.Element) -> str:
        node = el.find(f"{{{PODCAST_NS}}}license")
        if node is None:
            return ""
        return node.get("url") or (node.text or "").strip()

    chan_lic = lic(ch)
    title = (ch.findtext("title") or "").strip()
    out = []
    for item in ch.findall("item"):
        enc = item.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        il = lic(item) or chan_lic
        out.append(
            Found(
                urljoin(url, enc.get("url", "")),
                "audio",
                meta={
                    "licence": il,
                    "licence_evidence": "podcast:license on the " + ("item" if lic(item) else "channel")
                    if il
                    else "no podcast:license in feed",
                    "title": f"{title}: {(item.findtext('title') or '').strip()}",
                    "attribution": title,
                    "language": ch.findtext("language"),
                },
            )
        )
    return out


# ---------------------------------------------------------------- HTML


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (url, tag)
        self.licence = ""
        self.ld: list[str] = []
        self._in_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self.links.append((a["href"], "a"))
            if "license" in a.get("rel", "").split():
                self.licence = self.licence or a["href"]
        elif tag in ("audio", "source") and a.get("src"):
            self.links.append((a["src"], "audio"))
        elif tag == "link" and "license" in a.get("rel", "").split() and a.get("href"):
            self.licence = self.licence or a["href"]
        elif tag == "link" and a.get("type") in ("application/rss+xml", "application/atom+xml") and a.get("href"):
            self.links.append((a["href"], "feed"))
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self.ld.append(data)


def _ld_objects(chunks: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in chunks:
        try:
            doc = json.loads(c)
        except json.JSONDecodeError:
            continue
        for d in doc if isinstance(doc, list) else [doc]:
            if isinstance(d, dict):
                out += [x for x in d.get("@graph", []) if isinstance(x, dict)] if "@graph" in d else [d]
    return out


def html(url: str, body: bytes, same_host_only: bool = True) -> list[Found]:
    p = _Html()
    p.feed(body.decode("utf-8", errors="replace"))
    host = urlsplit(url).netloc
    by_audio: dict[str, dict[str, Any]] = {}
    for d in _ld_objects(p.ld):
        if str(d.get("@type", "")).lower() in ("audioobject", "podcastepisode") and d.get("contentUrl"):
            dst = str(d.get("digitalSourceType", "")).lower()
            by_audio[urljoin(url, d["contentUrl"])] = {
                "licence": d.get("license") or "",
                "synthetic_declared": any(t in dst for t in SYNTHETIC_TYPES),
                "title": d.get("name") or "",
                "transcript": d.get("transcript") or "",
            }
    out, seen = [], set()
    for href, tag in p.links:
        u = urljoin(url, href).split("#")[0]
        if not u.startswith(("http://", "https://")) or u in seen:
            continue
        seen.add(u)
        k = "audio" if tag == "audio" else "feed" if tag == "feed" else kind_of(u)
        if same_host_only and urlsplit(u).netloc != host and k != "audio":
            continue
        meta: dict[str, Any] = {}
        if k == "audio":
            ld = by_audio.get(u, {})
            lic = ld.get("licence") or p.licence
            meta = {
                "licence": lic,
                "licence_evidence": ("schema.org license of the AudioObject" if ld.get("licence") else 'page <link rel="license">')
                if lic
                else "no licence on the page",
                "synthetic_declared": bool(ld.get("synthetic_declared")),
                "title": ld.get("title") or u.rsplit("/", 1)[-1],
                "attribution": host,
                "transcript": ld.get("transcript") or "",
            }
        out.append(Found(u, k, "rss" if k == "feed" else "html" if k == "page" else "", meta))
    return out


PARSERS = {"librivox": librivox, "ia_search": ia_search, "ia_metadata": ia_metadata, "rss": rss, "html": html}


def parser_for(kind: str, url: str) -> str:
    if kind == "feed":
        return "rss"
    if kind == "page":
        return "html"
    if "/api/feed/audiobooks" in url:
        return "librivox"
    if "advancedsearch.php" in url:
        return "ia_search"
    if re.search(r"/metadata/[^/]+$", url):
        return "ia_metadata"
    return ""
