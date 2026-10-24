"""PostgreSQL access: one connection pool per process, migrations on start."""

from __future__ import annotations

import atexit
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pools: dict[str, ConnectionPool] = {}


def pool(url: str | None = None) -> ConnectionPool:
    url = url or config.database_url()
    if url not in _pools:
        _pools[url] = ConnectionPool(url, min_size=1, max_size=8, kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
    return _pools[url]


@contextmanager
def tx(url: str | None = None) -> Iterator[psycopg.Connection[Any]]:
    with pool(url).connection() as conn, conn.transaction():
        yield conn


def migrate(url: str | None = None) -> list[int]:
    applied = []
    with tx(url) as c:
        c.execute("SELECT pg_advisory_xact_lock(4242)")
        have = c.execute("SELECT to_regclass('schema_version') AS t").fetchone()
        done = {r["version"] for r in c.execute("SELECT version FROM schema_version")} if have and have["t"] else set()
        files = sorted((p for p in resources.files("scr.migrations").iterdir() if p.name.endswith(".sql")), key=lambda p: p.name)
        for f in files:
            v = int(f.name.split("_")[0])
            if v in done:
                continue
            c.execute(f.read_text().encode())
            c.execute("INSERT INTO schema_version (version) VALUES (%s)", (v,))
            applied.append(v)
    return applied


def reset(url: str) -> None:
    """Drop everything (tests and demos only)."""
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


def close_all() -> None:
    for p in _pools.values():
        p.close()
    _pools.clear()


atexit.register(close_all)
