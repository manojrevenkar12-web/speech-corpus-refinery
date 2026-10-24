"""HTTP clients. In tests and demos, hosts under the reserved `.example` TLD are routed to the
local test-world server; every other host goes to the real internet."""

from __future__ import annotations

import os

import httpx


class WorldTransport(httpx.BaseTransport):
    def __init__(self, addr: str, inner: httpx.BaseTransport | None = None) -> None:
        host, port = addr.rsplit(":", 1)
        self.host, self.port = host, int(port)
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host.endswith(".example"):
            request.headers["Host"] = request.url.host
            request.url = request.url.copy_with(scheme="http", host=self.host, port=self.port)
        return self.inner.handle_request(request)


def client(user_agent: str, timeout: float, world: str | None = None) -> httpx.Client:
    world = world or os.environ.get("SCR_WORLD_ADDR")
    transport = WorldTransport(world) if world else httpx.HTTPTransport(retries=0)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=False,
    )
