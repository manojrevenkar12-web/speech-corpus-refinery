"""W3C TDMRep (Text and Data Mining Reservation Protocol), the machine-readable way to reserve
rights under Article 4 of the EU DSM Directive.

Three places, later ones overriding earlier ones: `/.well-known/tdmrep.json` (path rules),
the `tdm-reservation` HTTP header, and `<meta name="tdm-reservation">` in HTML. Values other
than 0 or 1 are protocol errors and count as unset.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit


@dataclass
class Reservation:
    reserved: bool | None  # None: nothing said
    policy: str = ""
    where: str = ""  # file | header | meta

    def __bool__(self) -> bool:
        return bool(self.reserved)


def _value(v: Any) -> bool | None:
    s = str(v).strip()
    return {"1": True, "0": False}.get(s)


def _pattern(loc: str) -> re.Pattern[str]:
    p = re.escape(unquote(loc)).replace(r"\*", ".*")
    if p.endswith(r"\$"):
        p = p[:-2] + "$"
    return re.compile(p)


def parse_file(text: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    return [r for r in doc if isinstance(r, dict) and "location" in r] if isinstance(doc, list) else []


def from_file(rules: list[dict[str, Any]], url: str) -> Reservation:
    path = unquote(urlsplit(url).path or "/")
    best: dict[str, Any] | None = None
    for r in rules:
        loc = str(r["location"])
        if _pattern(loc).match(path) and (best is None or len(loc) > len(str(best["location"]))):
            best = r
    if best is None:
        return Reservation(None)
    return Reservation(_value(best.get("tdm-reservation")), str(best.get("tdm-policy", "")), "file")


def from_headers(headers: dict[str, str], prior: Reservation) -> Reservation:
    h = {k.lower(): v for k, v in headers.items()}
    if "tdm-reservation" not in h:
        return prior
    v = _value(h["tdm-reservation"])
    return prior if v is None else Reservation(v, h.get("tdm-policy", ""), "header")


_META = re.compile(r"<meta\s+[^>]*name=[\"']tdm-(reservation|policy)[\"'][^>]*content=[\"']([^\"']*)[\"']", re.I)


def from_html(html: str, prior: Reservation) -> Reservation:
    found = dict((k.lower(), v) for k, v in _META.findall(html))
    if "reservation" not in found:
        return prior
    v = _value(found["reservation"])
    return prior if v is None else Reservation(v, found.get("policy", ""), "meta")
