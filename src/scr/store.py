"""Content-addressed blob storage: local disk for development, Google Cloud Storage in production.
Keys are `blobs/<sha256[:2]>/<sha256>`, so the same bytes from two URLs are stored once and a
takedown deletes one object."""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
from typing import Any, Protocol

from . import config


class Store(Protocol):
    def put_file(self, sha256: str, path: Path) -> None: ...
    def get_file(self, sha256: str, dest: Path) -> Path: ...
    def exists(self, sha256: str) -> bool: ...
    def delete(self, sha256: str) -> bool: ...
    def put_bytes(self, key: str, body: bytes) -> None: ...


def blob_key(sha256: str) -> str:
    if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256):
        raise ValueError(f"not a sha256: {sha256!r}")
    return f"blobs/{sha256[:2]}/{sha256}"


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"key escapes the store: {key}")
        return p

    def put_file(self, sha256: str, path: Path) -> None:
        dest = self._p(blob_key(sha256))
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(path.read_bytes())
        tmp.replace(dest)

    def get_file(self, sha256: str, dest: Path) -> Path:
        return self._p(blob_key(sha256))

    def exists(self, sha256: str) -> bool:
        return self._p(blob_key(sha256)).exists()

    def delete(self, sha256: str) -> bool:
        p = self._p(blob_key(sha256))
        if p.exists():
            p.unlink()
            return True
        return False

    def put_bytes(self, key: str, body: bytes) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)


class GcsStore:
    """Google Cloud Storage. Objects are written with an if-generation-match=0 precondition, so a
    blob is created once and never silently overwritten."""

    def __init__(self, bucket: str, client: Any = None) -> None:
        from google.cloud import storage

        self.client: Any = client or storage.Client()
        self.bucket: Any = self.client.bucket(bucket)

    def put_file(self, sha256: str, path: Path) -> None:
        from google.api_core.exceptions import PreconditionFailed

        with contextlib.suppress(PreconditionFailed):  # already there: content-addressed, so identical
            self.bucket.blob(blob_key(sha256)).upload_from_filename(str(path), if_generation_match=0)

    def get_file(self, sha256: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.bucket.blob(blob_key(sha256)).download_to_filename(str(dest))
        if hashlib.sha256(dest.read_bytes()).hexdigest() != sha256:
            raise OSError(f"blob {sha256} does not match its name")
        return dest

    def exists(self, sha256: str) -> bool:
        return bool(self.bucket.blob(blob_key(sha256)).exists())

    def delete(self, sha256: str) -> bool:
        b = self.bucket.blob(blob_key(sha256))
        if not b.exists():
            return False
        b.delete()
        return True

    def put_bytes(self, key: str, body: bytes) -> None:
        self.bucket.blob(key).upload_from_string(body)


def publish_dir(bucket: str, prefix: str, folder: Path, client: Any = None) -> int:
    """Upload a finished release folder to `gs://bucket/prefix/`. Each object is created once
    (if-generation-match=0): publishing a release name that already exists fails rather than
    overwriting what people may have trained on."""
    from google.cloud import storage

    b = (client or storage.Client()).bucket(bucket)
    n = 0
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            b.blob(f"{prefix}/{p.relative_to(folder).as_posix()}").upload_from_filename(str(p), if_generation_match=0)
            n += 1
    return n


def default() -> Store:
    bucket = os.environ.get("SCR_GCS_BUCKET")
    if bucket:
        return GcsStore(bucket)
    return LocalStore(config.DATA_DIR / "store")
