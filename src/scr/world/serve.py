"""Serve the test world: one aiohttp server, sites chosen by the Host header.

Real-source shapes: `/api/feed/audiobooks/` pages like LibriVox's API (limit, offset),
`/advancedsearch.php` and `/metadata/<id>` like the Internet Archive. Per-site behaviour from
behaviour.json: extra headers by path prefix, and failures (429 with Retry-After, 503, a slow
first response, a truncated body, HTML served as audio, a redirect loop).
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
from collections import Counter
from pathlib import Path
from typing import Any

from aiohttp import web

mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("application/rss+xml", ".xml")


def make_app(root: Path) -> web.Application:
    sites = root / "sites"
    behaviour: dict[str, Any] = json.loads((root / "behaviour.json").read_text()) if (root / "behaviour.json").exists() else {}
    attempts: Counter[str] = Counter()
    log: list[dict[str, Any]] = []

    async def handle(request: web.Request) -> web.StreamResponse:
        host = (request.host or "").split(":")[0]
        path = request.path
        log.append(
            {"host": host, "path": path, "ua": request.headers.get("User-Agent", ""), "method": request.method, "t": time.monotonic()}
        )
        base = sites / host
        if not base.is_dir():
            return web.Response(status=404, text="unknown host")
        key = f"{host}{path}"
        attempts[key] += 1
        n = attempts[key]
        beh = behaviour.get(host, {})
        extra = {}
        for prefix, hdrs in beh.get("headers", {}).items():
            if path.startswith(prefix):
                extra.update(hdrs)
        f = beh.get("files", {}).get(path, {})
        if f.get("redirect_loop"):
            raise web.HTTPFound(location=f"{path}?hop={n}")
        fails = f.get("fail", [])
        if n <= len(fails):
            hdr = {"Retry-After": str(f.get("retry_after", 1))} if fails[n - 1] == 429 else {}
            return web.Response(status=fails[n - 1], headers=hdr, text="try later")
        if f.get("delay_first") and n == 1:
            await asyncio.sleep(float(f["delay_first"]))

        # API shapes
        if path.rstrip("/") == "/api/feed/audiobooks" and (base / "api/feed/audiobooks/index.json").exists():
            doc = json.loads((base / "api/feed/audiobooks/index.json").read_text())
            off, lim = int(request.query.get("offset", 0)), int(request.query.get("limit", 50))
            return web.json_response(
                {"books": doc["books"][off : off + lim]} if doc["books"][off : off + lim] else {"error": "No audiobooks found"}
            )
        if path == "/advancedsearch.php" and (base / "advancedsearch.json").exists():
            doc = json.loads((base / "advancedsearch.json").read_text())
            rows, page = int(request.query.get("rows", 50)), int(request.query.get("page", 1))
            docs = doc["response"]["docs"]
            return web.json_response(
                {"response": {"numFound": len(docs), "start": (page - 1) * rows, "docs": docs[(page - 1) * rows : page * rows]}}
            )
        if path.startswith("/metadata/") and (base / "advancedsearch.json").exists():
            p = base / "metadata" / f"{path.split('/')[2]}.json"
            return web.json_response(json.loads(p.read_text())) if p.exists() else web.json_response({})

        target = (base / path.lstrip("/")).resolve()
        if path.endswith("/"):
            target = target / "index.html"
        if not str(target).startswith(str(base.resolve())) or not target.is_file():
            return web.Response(status=404, text="not found", headers=extra)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if f.get("html_body"):
            return web.Response(body=b"<html><body>Our CDN is having trouble.</body></html>", content_type="audio/mpeg", headers=extra)
        body = target.read_bytes()
        if f.get("truncate_first") and n == 1:
            resp = web.StreamResponse(headers={"Content-Type": ctype, "Content-Length": str(len(body)), **extra})
            await resp.prepare(request)
            await resp.write(body[: len(body) // 3])
            if request.transport is not None:
                request.transport.close()
            return resp
        etag = f'"{hash(body) & 0xFFFFFFFF:08x}"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag, **extra})
        return web.Response(body=body, headers={"Content-Type": ctype, "ETag": etag, **extra})

    app = web.Application()
    app["log"] = log
    app["attempts"] = attempts
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


async def start(root: Path, port: int = 0) -> tuple[web.AppRunner, int]:
    runner = web.AppRunner(make_app(root))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    sock = site._server.sockets[0]  # type: ignore[union-attr]
    return runner, int(sock.getsockname()[1])


class WorldServer:
    """The test world on a background thread: `with WorldServer(root) as w: ... w.addr`."""

    def __init__(self, root: Path, port: int = 0) -> None:
        import threading

        self.root = root
        self.want_port = port
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.port = 0

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.runner, self.port = self.loop.run_until_complete(start(self.root, self.want_port))
        self.ready.set()
        self.loop.run_forever()
        self.loop.run_until_complete(self.runner.cleanup())

    def __enter__(self) -> WorldServer:
        self.thread.start()
        if not self.ready.wait(15):
            raise RuntimeError("test world did not start")
        return self

    def __exit__(self, *exc: object) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)

    @property
    def addr(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def log(self) -> list[dict[str, Any]]:
        return list(self.runner.app["log"])
