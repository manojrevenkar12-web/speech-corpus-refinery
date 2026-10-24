"""Command line: `scr --help`."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from . import config

app = typer.Typer(add_completion=False, help="Find, rights-check, crawl and refine speech audio into TTS training data.")
takedown_app = typer.Typer(help="Takedown requests.")
app.add_typer(takedown_app, name="takedown")


def _out(obj: object) -> None:
    typer.echo(json.dumps(obj, indent=1, default=str))


@app.command()
def fetch(models: bool = True, corpora: bool = True) -> None:
    """Download the pinned corpora and models and verify their SHA-256."""
    from . import assets

    typer.echo(f"{assets.fetch(models=models, corpora=corpora)} files verified")


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    from . import db

    _out({"applied": db.migrate()})


@app.command()
def world(out: Path | None = None) -> None:
    """Build the test world (about a minute)."""
    from .world import build

    typer.echo(str(build.build(out)))


@app.command("world-serve")
def world_serve(port: int = 8700, root: Path | None = None) -> None:
    """Serve the test world; point the crawler at it with SCR_WORLD_ADDR=127.0.0.1:<port>."""
    from aiohttp import web

    from .world import serve

    web.run_app(serve.make_app(root or config.DATA_DIR / "world"), host="127.0.0.1", port=port)


@app.command()
def protect() -> None:
    """Fingerprint the protected evaluation recordings (config/protected.yaml)."""
    from .pipeline import protect_all

    _out({"protected": protect_all()})


@app.command()
def seed(name: str, kind: str, url: str) -> None:
    """Add a source: kind is librivox, internet_archive, rss or html_index."""
    from .crawl.crawler import Crawler

    _out({"source_id": Crawler().seed(name, kind, url)})


@app.command()
def crawl(workers: int = 4, deadline: float = 3600.0) -> None:
    """Crawl until the frontier is empty or the deadline passes."""
    from .crawl.crawler import Crawler

    _out(Crawler().run(workers=workers, deadline=deadline).__dict__)


@app.command()
def work(processes: int = 1) -> None:
    """Process queued items (each process leases jobs from PostgreSQL)."""
    from . import pipeline
    from .store import LocalStore, default

    store = default()
    if isinstance(store, LocalStore):
        _out({"analysed": pipeline.work(config.database_url(), store, processes)})
    else:
        from . import jobs, process

        _out({"analysed": jobs.work(["analyse"], lambda j: process.analyse(j.ref, store))})


@app.command("release")
def release_cmd(name: str) -> None:
    """Freeze the kept segments into an immutable release."""
    from . import release
    from .store import default

    _out(release.build(name, default()))


@app.command()
def diff(a: str, b: str) -> None:
    """What changed between two releases, and why."""
    from . import release

    _out(release.diff(a, b))


@app.command()
def discover(name: str, kind: str, url: str, sample: int = 10) -> None:
    """Score a new source on a sample before ingesting it."""
    from . import discover as d
    from .store import default

    _out(d.probe(name, kind, url, default(), sample))


@app.command()
def costs() -> None:
    """Cost per usable hour, by source."""
    from . import cost

    _out(cost.report())


@takedown_app.command("request")
def td_request(kind: str, value: str, reason: str = typer.Option(...), by: str = typer.Option(...)) -> None:
    """Record a request (kind: url, domain, speaker, item)."""
    from . import takedown

    _out({"id": takedown.request(kind, value, reason, by)})


@takedown_app.command("preview")
def td_preview(kind: str, value: str) -> None:
    """What a takedown would withdraw."""
    from . import takedown

    _out(takedown.preview(kind, value))


@takedown_app.command("execute")
def td_execute(takedown_id: int, by: str = typer.Option(...)) -> None:
    """Withdraw, delete, and block re-ingestion."""
    from . import takedown
    from .store import default

    _out(takedown.execute(takedown_id, default(), by))


@app.command("verify-audit")
def verify_audit() -> None:
    """Check the hash chain of the audit trail; exit 1 if broken."""
    from . import audit, db

    with db.tx() as c:
        v = audit.verify(c)
    _out(v.__dict__)
    raise typer.Exit(0 if v.ok else 1)


@app.command()
def demo(processes: int = 2, sample: int = 4) -> None:
    """Build the test world and run everything against it; reports land in reports/."""
    from . import pipeline

    _out(pipeline.demo(processes=processes, sample=sample))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """The API and review console."""
    import uvicorn

    uvicorn.run("scr.api:app_from_env", host=host, port=port, factory=True)


def main() -> None:  # pragma: no cover
    app(prog_name="scr")


if __name__ == "__main__":  # pragma: no cover
    main()
