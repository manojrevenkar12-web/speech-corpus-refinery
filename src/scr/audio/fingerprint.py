"""Audio fingerprints that survive re-encoding, gain changes and added silence (landmark
hashing, after Wang 2003): spectrogram peaks, paired into (f1, f2, dt) hashes with the anchor's
time. Two recordings match when many hashes agree on one time offset."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import stft

N_FFT = 512
HOP = 128  # 16 ms at 8 kHz
FAN_OUT = 5
DT_MAX = 63
PEAKS_PER_SECOND = 30


def landmarks(x: np.ndarray, rate: int = 8000) -> list[tuple[int, int]]:
    """(hash, anchor frame) pairs. `x` must be at `rate` (8 kHz keeps phone-band content)."""
    if len(x) < N_FFT * 4:
        return []
    _, _, z = stft(x, fs=rate, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary=None)
    s = np.log(np.abs(z) + 1e-6)[1:]  # drop DC
    local = maximum_filter(s, size=(15, 9)) == s
    floor = np.median(s) + 1.0
    fi, ti = np.nonzero(local & (s > floor))
    if not len(ti):
        return []
    # keep the strongest peaks per second of audio
    frames_per_s = rate / HOP
    budget = max(1, int(PEAKS_PER_SECOND * s.shape[1] / frames_per_s))
    order = np.argsort(s[fi, ti])[::-1][:budget]
    peaks = sorted(zip(ti[order].tolist(), fi[order].tolist(), strict=True))
    out: list[tuple[int, int]] = []
    for i, (t1, f1) in enumerate(peaks):
        n = 0
        for t2, f2 in peaks[i + 1 :]:
            dt = t2 - t1
            if dt == 0:
                continue
            if dt > DT_MAX:
                break
            if abs(f2 - f1) > 64:
                continue
            h = (f1 << 15) | (f2 << 6) | dt
            out.append((h, t1))
            n += 1
            if n >= FAN_OUT:
                break
    return out


@dataclass
class Match:
    other: int
    votes: int
    ratio: float
    offset_seconds: float


def best_matches(
    query: list[tuple[int, int]],
    candidates: Iterable[tuple[int, int, int]],
    sizes: dict[int, int],
    rate: int = 8000,
) -> list[Match]:
    """`candidates`: (hash, item, frame) rows from the index for the query's hashes; `sizes`:
    number of hashes per indexed item. Votes per item are counted at its most common offset."""
    by_hash: dict[int, list[int]] = defaultdict(list)
    for h, t in query:
        by_hash[h].append(t)
    offsets: dict[int, Counter[int]] = defaultdict(Counter)
    for h, item, t in candidates:
        for tq in by_hash.get(h, ()):
            offsets[item][t - tq] += 1
    out = []
    for item, c in offsets.items():
        off, votes = c.most_common(1)[0]
        smaller = max(1, min(len(query), sizes.get(item, len(query))))
        out.append(Match(item, votes, votes / smaller, off * HOP / rate))
    return sorted(out, key=lambda m: -m.votes)
