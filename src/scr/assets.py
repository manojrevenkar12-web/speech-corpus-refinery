"""The pinned inputs (config/assets.yaml): real, openly licensed audio and the models, each checked by SHA-256."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from . import config


class AssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class Asset:
    corpus: str
    path: str
    url: str
    sha256: str
    licence: str

    @property
    def local(self) -> Path:
        return config.ASSETS_DIR / self.corpus / self.path


def manifest() -> dict[str, Any]:
    return config.load("assets")


def corpus_assets() -> list[Asset]:
    doc = manifest()
    out = []
    for name, c in doc["corpora"].items():
        for f in c["files"]:
            url = f"{doc['raw_base']}/{c['repo']}/{c['commit']}/{f['path']}"
            out.append(Asset(name, f["path"], url, f["sha256"], c["licence"]))
    return out


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(client: httpx.Client, url: str, dest: Path, sha256: str, attempts: int = 3) -> None:
    if not url.startswith("https://"):
        raise AssetError(f"refusing non-https asset URL: {url}")
    if dest.exists() and _sha(dest) == sha256:
        return
    for n in range(attempts):
        try:
            _download_once(client, url, dest, sha256)
            return
        except (AssetError, httpx.HTTPError):
            if n == attempts - 1:
                raise


def _download_once(client: httpx.Client, url: str, dest: Path, sha256: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    got = _sha(tmp)
    if got != sha256:
        tmp.unlink()
        raise AssetError(f"checksum mismatch for {url}: {got} != {sha256}")
    tmp.replace(dest)


def fetch(models: bool = True, corpora: bool = True) -> int:
    """Download what is missing; verify every file. Returns the number of files checked."""
    n = 0
    with httpx.Client(follow_redirects=True, timeout=300) as client:
        if corpora:
            for a in corpus_assets():
                _download(client, a.url, a.local, a.sha256)
                n += 1
        if models:
            for name, m in manifest()["models"].items():
                if (config.MODELS_DIR / name).exists():
                    n += 1
                    continue
                dest = config.MODELS_DIR / "downloads" / Path(m["url"]).name
                _download(client, m["url"], dest, m["sha256"])
                _unpack(name, dest)
                n += 1
    return n


def _unpack(name: str, archive: Path) -> None:
    target = config.MODELS_DIR / name
    if target.exists():
        return
    if archive.name.endswith(".tar.bz2"):
        tmp = config.MODELS_DIR / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        with tarfile.open(archive) as t:
            t.extractall(tmp, filter="data")
        inner = [p for p in tmp.iterdir() if p.is_dir()]
        (inner[0] if len(inner) == 1 else tmp).rename(target)
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        target.mkdir(parents=True)
        shutil.copy2(archive, target / archive.name)


def model_dir(name: str) -> Path:
    p = config.MODELS_DIR / name
    if not p.exists():
        raise AssetError(f"model {name} missing: run `scr fetch`")
    return p


def have_models() -> bool:
    return all((config.MODELS_DIR / n).exists() for n in manifest()["models"])


def have_corpora() -> bool:
    return all(a.local.exists() for a in corpus_assets())
