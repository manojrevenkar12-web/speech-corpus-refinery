import os
from pathlib import Path

import pytest

from scr import assets, config

TEST_DB = os.environ.get("SCR_TEST_DATABASE_URL", "postgresql:///scr_test")
HAVE_MODELS = assets.have_models()
HAVE_CORPORA = assets.have_corpora()
needs_models = pytest.mark.skipif(not (HAVE_MODELS and HAVE_CORPORA), reason="pinned models and corpora missing: run `scr fetch`")

FAST = """
crawl:
  timeout_seconds: 3
  min_delay_seconds: 0.05
  backoff_seconds: [0.2, 0.5, 1.0]
"""


def _db_ok() -> bool:
    try:
        import psycopg

        with psycopg.connect(TEST_DB, connect_timeout=3):
            return True
    except Exception:
        return False


HAVE_DB = _db_ok()
needs_db = pytest.mark.skipif(not HAVE_DB, reason="PostgreSQL not reachable at SCR_TEST_DATABASE_URL")


@pytest.fixture
def fresh_db():
    from scr import db

    db.close_all()
    db.reset(TEST_DB)
    db.migrate(TEST_DB)
    os.environ["SCR_DATABASE_URL"] = TEST_DB
    yield TEST_DB
    db.close_all()


from scr.world.serve import WorldServer  # noqa: E402,F401


@pytest.fixture(scope="session")
def world_root(tmp_path_factory):
    """The test world, built once per session (about a minute) unless SCR_WORLD_DIR points at one."""
    if not (HAVE_MODELS and HAVE_CORPORA):
        pytest.skip("pinned models and corpora missing")
    given = os.environ.get("SCR_WORLD_DIR")
    if given and (Path(given) / "truth.json").exists():
        return Path(given)
    from scr.world import build

    return build.build(tmp_path_factory.mktemp("world"))


@pytest.fixture
def fast_settings(monkeypatch):
    monkeypatch.setenv("SCR_SETTINGS_OVERRIDE", FAST)
    config.load.cache_clear()
    yield
    config.load.cache_clear()
