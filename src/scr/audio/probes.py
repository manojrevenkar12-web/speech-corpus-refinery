"""Signal measurements that need no model: level, clipping, effective bandwidth, SNR."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import welch


def dbfs(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0
    return 20 * np.log10(rms) if rms > 0 else -120.0


def clipped_ratio(x: np.ndarray, threshold: float) -> float:
    """Share of samples at full scale that sit in runs of three or more (single peaks at full
    scale are legitimate; flat-topped runs are clipping)."""
    if not len(x):
        return 0.0
    hot = np.abs(x) >= threshold
    if not hot.any():
        return 0.0
    run3 = hot[:-2] & hot[1:-1] & hot[2:]
    return float(run3.sum()) / len(x)


def bandwidth(x: np.ndarray, rate: int, floor_db: float) -> float:
    """Effective bandwidth (HiFiTTS-2): the highest frequency whose mean power is within
    `floor_db` of the spectral peak. A file stored at 44.1 kHz with content up to 4 kHz shows
    about 4 kHz, which reveals it was upsampled from telephone-rate audio."""
    if len(x) < 2048:
        return 0.0
    f, p = welch(x.astype(np.float64), fs=rate, nperseg=2048, noverlap=1024)
    p_db = 10 * np.log10(p + 1e-20)
    peak = p_db.max()
    above = np.nonzero(p_db >= peak + floor_db)[0]
    return float(f[above[-1]]) if len(above) else 0.0


def frame_power(x: np.ndarray, rate: int, frame: float = 0.025, hop: float = 0.010) -> np.ndarray:
    n, h = int(rate * frame), int(rate * hop)
    if len(x) < n:
        return np.array([np.mean(np.square(x, dtype=np.float64))]) if len(x) else np.array([0.0])
    idx = np.arange(0, len(x) - n + 1, h)
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[idx]
    return np.mean(np.square(frames, dtype=np.float64), axis=1)


@dataclass
class Snr:
    db: float
    method: str


def snr(x: np.ndarray, rate: int, speech_mask: np.ndarray | None = None) -> Snr:
    """Signal-to-noise ratio of speech audio, from 25 ms frame powers.

    Noise is the mean power of the quietest tenth of frames that are not digital silence (exact
    zeros, as in edited gaps, say nothing about the recording's noise). With a VAD mask the
    signal is the mean power of speech frames; without one, the loudest tenth. Continuous
    background noise keeps even the quietest frames loud, so it shows; clean speech with room
    tone between phrases does not.
    """
    p = frame_power(x, rate)
    eps = 1e-12
    live = p[p > 1e-10]
    if len(live) < 10:
        return Snr(0.0, "too short")
    noise = float(np.mean(np.sort(live)[: max(3, len(live) // 10)]))
    method = "percentile"
    sig = float(np.mean(np.sort(live)[-max(3, len(live) // 10) :]))
    if speech_mask is not None:
        m = speech_mask[: len(p)]
        if len(m) < len(p):
            m = np.concatenate([m, np.zeros(len(p) - len(m), bool)])
        sp = p[m & (p > 1e-10)]
        if len(sp) >= 10:
            sig, method = float(np.mean(sp)), "vad"
    return Snr(float(10 * np.log10(max(sig - noise, eps) / max(noise, eps))), method)
