"""robots.txt as RFC 9309 specifies it.

- The crawler obeys the group whose user-agent line matches its product token
  (case-insensitive); groups with the same agent are merged; `*` applies only when no group
  matches.
- Within the group, the rule with the longest matching path wins; on a tie, allow wins.
- `*` matches any sequence of characters and `$` anchors the end.
- Fetch failures: 4xx means no restrictions; 5xx or an unreachable server means complete
  disallow (and the crawler retries later).
`Crawl-delay` is not in the RFC; it is read as an extension because many sites use it.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass
class Rule:
    allow: bool
    path: str

    def pattern(self) -> re.Pattern[str]:
        p = re.escape(_norm(self.path)).replace(r"\*", ".*")
        if p.endswith(r"\$"):
            p = p[:-2] + "$"
        return re.compile(p)


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass
class Robots:
    groups: list[Group]
    disallow_all: bool = False  # the server failed: obey nothing but "stay out"
    sitemaps: list[str] = field(default_factory=list)

    def group_for(self, token: str) -> Group | None:
        t = token.lower()
        mine = [g for g in self.groups if t in [a.lower() for a in g.agents]]
        if not mine:
            mine = [g for g in self.groups if "*" in g.agents]
        if not mine:
            return None
        merged = Group(agents=[token])
        for g in mine:
            merged.rules += g.rules
            if g.crawl_delay is not None:
                merged.crawl_delay = max(merged.crawl_delay or 0.0, g.crawl_delay)
        return merged

    def allowed(self, url: str, token: str) -> bool:
        if self.disallow_all:
            return False
        parts = urlsplit(url)
        path = _norm((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
        if path == "/robots.txt":
            return True
        g = self.group_for(token)
        if g is None:
            return True
        best: Rule | None = None
        for r in g.rules:
            if r.path == "":  # "Disallow:" with no path allows everything
                continue
            longer = best is None or len(r.path) > len(best.path) or (len(r.path) == len(best.path) and r.allow and not best.allow)
            if longer and r.pattern().match(path):
                best = r
        return True if best is None else best.allow

    def crawl_delay(self, token: str) -> float | None:
        g = self.group_for(token)
        return g.crawl_delay if g else None


def _norm(path: str) -> str:
    # compare percent-decoded, except an encoded slash keeps its meaning
    return unquote(path.replace("%2F", "%252F").replace("%2f", "%252f"))


def parse(text: str) -> Robots:
    groups: list[Group] = []
    sitemaps: list[str] = []
    current: Group | None = None
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = Group()
                groups.append(current)
            current.agents.append(value)
            last_was_agent = True
            continue
        last_was_agent = False
        if key == "sitemap":
            sitemaps.append(value)
        elif current is None:
            continue
        elif key in ("allow", "disallow"):
            current.rules.append(Rule(key == "allow", value))
        elif key == "crawl-delay":
            with contextlib.suppress(ValueError):
                current.crawl_delay = float(value)
    return Robots(groups, sitemaps=sitemaps)


def from_response(status: int | None, text: str) -> Robots:
    """RFC 9309 section 2.3.1: what a fetch outcome means."""
    if status is None or status >= 500:
        return Robots([], disallow_all=True)
    if 400 <= status < 500:
        return Robots([])
    return parse(text)
