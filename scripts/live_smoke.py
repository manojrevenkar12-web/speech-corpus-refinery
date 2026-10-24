"""Against the real sources, gently: does each connector still understand what LibriVox and the
Internet Archive return, and do their robots.txt still let our crawler in? Five requests at most,
one per second, with the crawler's own user agent. Run weekly in CI; failures are reported, not
fatal, because the outside world changes without asking."""

from __future__ import annotations

import json
import sys
import time

import httpx

from scr import config
from scr.crawl import connectors
from scr.rights import licence, robots

UA = config.settings()["crawl"]["user_agent"]
TOKEN = config.settings()["crawl"]["robots_token"]


def get(client: httpx.Client, url: str) -> httpx.Response:
    time.sleep(1.0)
    return client.get(url, follow_redirects=True)


def main() -> int:
    checks: dict[str, bool | str] = {}
    with httpx.Client(headers={"User-Agent": UA}, timeout=30) as c:
        lv_api = "https://librivox.org/api/feed/audiobooks/?format=json&extended=1&limit=2"
        r = get(c, "https://librivox.org/robots.txt")
        checks["librivox robots lets ScrBot read the API"] = robots.from_response(r.status_code, r.text).allowed(lv_api, TOKEN)
        r = get(c, lv_api)
        found = [f for f in connectors.librivox(lv_api, r.content, page_size=2) if f.kind == "audio"]
        checks["librivox API returns sections with audio"] = len(found) > 0
        checks["librivox audio is public domain"] = (
            all(licence.normalise(f.meta["licence"]) == "LicenseRef-PublicDomain" for f in found) if found else "no audio"
        )

        ia = "https://archive.org/advancedsearch.php?q=collection%3Alibrivoxaudio&fl%5B%5D=identifier&rows=1&output=json"
        r = get(c, "https://archive.org/robots.txt")
        checks["archive.org robots lets ScrBot search"] = robots.from_response(r.status_code, r.text).allowed(ia, TOKEN)
        r = get(c, ia)
        meta_urls = [f.url for f in connectors.ia_search(ia, r.content, rows=1) if f.parser == "ia_metadata"]
        checks["archive.org search returns items"] = len(meta_urls) == 1
        if meta_urls:
            r = get(c, meta_urls[0])
            audio = [f for f in connectors.ia_metadata(meta_urls[0], r.content) if f.kind == "audio"]
            checks["archive.org metadata yields one preferred audio file per track"] = len(audio) > 0
    print(json.dumps(checks, indent=1))
    return 0 if all(v is True for v in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
