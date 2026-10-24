"""Licences as SPDX identifiers, from the many ways sources state them: Creative Commons URLs
(with or without https, trailing slashes, `deed.de`), Podcasting 2.0 slugs (`cc-by-4.0`),
words ("Public Domain"), and source conventions (LibriVox recordings are public domain).
Then the policy in config/rights.yaml decides what may train a commercial TTS model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

UNKNOWN = "LicenseRef-Unknown"

_CC_URL = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z-]+)/(\d\.\d)", re.I)
_SLUG = re.compile(r"^(cc0|cc-by(?:-sa|-nc|-nd|-nc-sa|-nc-nd)?|cc-pdm)-?(\d\.\d)$", re.I)


def normalise(value: str | None) -> str:
    if not value:
        return UNKNOWN
    v = value.strip()
    m = _CC_URL.search(v)
    if m:
        kind, code, ver = m.group(1).lower(), m.group(2).lower(), m.group(3)
        if kind == "publicdomain":
            return {"zero": f"CC0-{ver}", "mark": f"CC-PDM-{ver}"}.get(code, UNKNOWN)
        return f"CC-{code.upper()}-{ver}"
    m = _SLUG.match(v.replace("_", "-"))
    if m:
        code, ver = m.group(1).lower(), m.group(2)
        if code == "cc0":
            return f"CC0-{ver}"
        if code == "cc-pdm":
            return f"CC-PDM-{ver}"
        return f"{code.upper()}-{ver}"
    low = v.lower()
    if low in ("public domain", "publicdomain", "pd", "licenseref-publicdomain"):
        return "LicenseRef-PublicDomain"
    if re.fullmatch(r"[A-Za-z0-9.+-]+", v) and v.upper().startswith(("CC", "LICENSEREF")):
        return v
    if "all rights reserved" in low:
        return "LicenseRef-AllRightsReserved"
    return UNKNOWN


@dataclass
class Verdict:
    allowed: bool
    licence: str
    attribution: bool = False
    share_alike: bool = False
    reason: str = ""


def decide(licence: str, policy: dict[str, Any]) -> Verdict:
    allowed = policy["allowed_licences"]
    if licence in allowed:
        terms = allowed[licence] or {}
        return Verdict(True, licence, bool(terms.get("attribution")), bool(terms.get("share_alike")))
    if licence == UNKNOWN:
        return Verdict(False, licence, reason="no licence stated")
    if "-NC" in licence:
        return Verdict(False, licence, reason="non-commercial licence")
    if "-ND" in licence:
        return Verdict(False, licence, reason="no-derivatives licence")
    return Verdict(False, licence, reason=f"{licence} is not on the allowed list")


def blocked_domain(host: str, policy: dict[str, Any]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in policy.get("blocked_domains", []))
