"""Decode any container ffmpeg understands into float32 mono, at the file's own rate and at the
analysis rate. The native rate matters: a 44.1 kHz file whose content stops at 4 kHz was
upsampled, and only the native-rate signal shows it."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np


class DecodeError(RuntimeError):
    pass


@dataclass
class Audio:
    native_rate: int
    channels: int
    codec: str
    native: np.ndarray  # mono float32 at native_rate (first `native_seconds` only when limited)
    rate: int
    samples: np.ndarray  # mono float32 at `rate`

    @property
    def seconds(self) -> float:
        return len(self.samples) / self.rate


@cache
def ffmpeg() -> str:
    import shutil

    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


_STREAM = re.compile(r"Audio: ([^,\s]+)[^,]*, (\d+) Hz, ([^,]+)")


def probe(path: Path) -> tuple[str, int, int]:
    """(codec, sample rate, channels) from ffmpeg's stream line."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, check=False)  # noqa: S603
    m = _STREAM.search(r.stderr)
    if not m:
        raise DecodeError(f"no audio stream in {path.name}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'empty'}")
    layout = m.group(3).strip()
    channels = {"mono": 1, "stereo": 2}.get(layout, int(layout.split()[0]) if layout[:1].isdigit() else 2)
    return m.group(1), int(m.group(2)), channels


def _pcm(path: Path, rate: int, seconds: float | None = None) -> np.ndarray:
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-i", str(path)]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
    if r.returncode != 0:
        raise DecodeError(f"cannot decode {path.name}: {r.stderr.decode(errors='replace').strip()[:300]}")
    x = np.frombuffer(r.stdout, dtype=np.float32).copy()
    if not len(x):
        raise DecodeError(f"{path.name} decodes to no samples")
    if not np.all(np.isfinite(x)):
        raise DecodeError(f"{path.name} decodes to non-finite samples")
    return x


def decode(path: Path, rate: int = 16000, native_seconds: float | None = 30.0) -> Audio:
    codec, native_rate, channels = probe(path)
    return Audio(native_rate, channels, codec, _pcm(path, native_rate, native_seconds), rate, _pcm(path, rate))


def resample(path: Path, rate: int, start: float = 0.0, seconds: float | None = None) -> np.ndarray:
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-i", str(path)]
    if seconds:
        cmd += ["-t", f"{seconds:.3f}"]
    cmd += ["-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
    if r.returncode != 0:
        raise DecodeError(r.stderr.decode(errors="replace")[:300])
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def encode(
    samples: np.ndarray, rate: int, path: Path, codec: str = "flac", out_rate: int | None = None, bitrate: str | None = None
) -> None:
    """Write float32 mono samples with ffmpeg (flac, wav, mp3, ogg ...)."""
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-y", "-f", "f32le", "-ar", str(rate), "-ac", "1", "-i", "-"]
    if out_rate:
        cmd += ["-ar", str(out_rate)]
    if bitrate:
        cmd += ["-b:a", bitrate]
    if codec == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif codec == "mp3":
        cmd += ["-c:a", "libmp3lame"]
    elif codec == "flac":
        cmd += ["-c:a", "flac"]
    elif codec == "ogg":
        cmd += ["-c:a", "libvorbis"]
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([*cmd, str(path)], input=np.clip(samples, -1, 1).astype(np.float32).tobytes(), capture_output=True, check=False)  # noqa: S603
    if r.returncode != 0:
        raise DecodeError(r.stderr.decode(errors="replace")[:300])
