"""Settings from config/*.yaml. Code reads thresholds from here, never from literals."""

from __future__ import annotations

import hashlib
import json
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("SCR_HOME", Path(__file__).resolve().parents[2]))
CONFIG_DIR = Path(os.environ.get("SCR_CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.environ.get("SCR_DATA_DIR", ROOT / "data"))
ASSETS_DIR = DATA_DIR / "assets"
MODELS_DIR = DATA_DIR / "models"


@cache
def load(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / f"{name}.yaml") as f:
        doc = yaml.safe_load(f) or {}
    assert isinstance(doc, dict), name
    return doc


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def settings() -> dict[str, Any]:
    """config/settings.yaml, with SCR_SETTINGS_OVERRIDE (inline YAML) merged on top for tests and drills."""
    base = load("settings")
    over = os.environ.get("SCR_SETTINGS_OVERRIDE")
    return _merge(base, yaml.safe_load(over) or {}) if over else base


def rights() -> dict[str, Any]:
    return load("rights")


def pricing() -> dict[str, Any]:
    return load("pricing")


def fingerprint(*parts: Any) -> str:
    """A short stable hash of configuration, so stage outputs record what produced them."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def database_url() -> str:
    return os.environ.get("SCR_DATABASE_URL", "postgresql:///scr")
