"""How far is the SNR estimate from the SNR a file was mixed at? (docs/MEASUREMENTS.md)

24 LJSpeech clips (the protected ones excluded), each mixed with rain, engine, wind and vacuum
noise from ESC-50 at 15 to 35 dB, plus the clean clip, as mp3 128k at 44.1 kHz: 600 files. The
mix SNR is the clip's mean power over the noise's, as the held-out worlds define it. Compares
the pipeline's estimator (speech frames from the VAD over the quietest tenth of frames) with two
estimators that do not need pauses: WADA-SNR (Kim and Stern 2008) and a minimum-statistics
noise floor (after Martin 2001)."""

from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.signal import stft

from scr import assets, config
from scr.audio import decode, models, probes

CLIPS = [f"LJ001-{n:04d}" for n in [*range(1, 17), *range(25, 33)]]
NOISES = {"rain": "1-17367-A-10", "engine": "1-18527-A-44", "wind": "1-137296-A-16", "vacuum": "1-100210-A-36"}
SNRS = [35, 30, 27, 25, 23, 20, 15]


def _wada_table() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    a = rng.gamma(0.4, 1.0, 400_000) * rng.choice([-1, 1], 400_000)
    a /= np.sqrt(np.mean(a**2))
    n = rng.normal(size=400_000)
    snrs = np.arange(-20, 101, 1.0)
    g = [np.log(np.mean(z)) - np.mean(np.log(z + 1e-20)) for z in (np.abs(a * 10 ** (s / 20) + n) for s in snrs)]
    return snrs, np.array(g)


SN, G = _wada_table()


def wada(x: np.ndarray) -> float:
    z = np.maximum(np.abs(x[np.abs(x) > 1e-10]), 1e-20)
    return float(np.interp(np.log(np.mean(z)) - np.mean(np.log(z)), G, SN))


def minimum_statistics(x: np.ndarray, mask: np.ndarray, q: float = 20) -> float:
    _, _, z = stft(x, fs=16000, nperseg=400, noverlap=240, boundary=None)
    p = np.abs(z) ** 2
    ps = np.apply_along_axis(lambda r: np.convolve(r, np.ones(3) / 3, mode="same"), 1, p)
    live = ps.sum(axis=0) > 1e-10
    noise = float(np.percentile(ps[:, live], q, axis=1).sum())
    m = np.zeros(p.shape[1], bool)
    m[: min(len(mask), p.shape[1])] = mask[: p.shape[1]]
    sig = float(p[:, m & live].sum(axis=0).mean()) if (m & live).sum() >= 10 else float(p[:, live].sum(axis=0).mean())
    return float(10 * np.log10(max(sig - noise, 1e-12) / max(noise, 1e-12)))


def main(out: Path) -> None:
    files = {a.local.name: a.local for a in assets.corpus_assets()}
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for c in CLIPS:
            x = decode.resample(files[f"{c}.wav"], 22050)
            cases: list[tuple[str, int | None]] = [("clean", None)] + [(k, s) for k in NOISES for s in SNRS]
            for noise, snr in cases:
                y = x
                if snr is not None:
                    nz = decode.resample(files[f"{NOISES[noise]}.wav"], 22050)
                    nz = np.tile(nz, int(np.ceil(len(x) / len(nz))))[: len(x)]
                    y = x + nz * np.sqrt(np.mean(x**2) / (np.mean(nz**2) * 10 ** (snr / 10)))
                y = (y / max(1.0, np.abs(y).max() / 0.95)).astype(np.float32)
                f = Path(td) / "f.mp3"
                decode.encode(y, 22050, f, codec="mp3", out_rate=44100, bitrate="128k")
                d = decode.resample(f, 16000)
                mask = models.speech_mask(models.vad(d, 16000), len(d) / 16000)
                rows.append(
                    {
                        "clip": c,
                        "noise": noise,
                        "mixed_db": snr,
                        "seconds": len(d) / 16000,
                        "pause_seconds": float((~mask[: len(d) // 160]).sum() * 0.01),
                        "pipeline": probes.snr(d, 16000, mask).db,
                        "wada": wada(d),
                        "minimum_statistics": minimum_statistics(d, mask),
                    }
                )
    limit = float(config.settings()["decide"]["min_snr_db"])
    judged = [r for r in rows if r["mixed_db"] != limit]

    def wrong(key: str, sub=lambda r: True) -> int:
        return sum(((r["mixed_db"] is None or r["mixed_db"] > limit) != (r[key] >= limit)) for r in judged if sub(r))

    few = lambda r: r["pause_seconds"] < 0.3  # noqa: E731
    bias = defaultdict(list)
    for r in rows:
        if r["mixed_db"] is not None:
            bias[r["mixed_db"]].append(r["pipeline"] - r["mixed_db"])
    summary = {
        "files": len(rows),
        "judged_files": len(judged),
        "wrong_side_of_limit": {k: wrong(k) for k in ("pipeline", "wada", "minimum_statistics")},
        "pipeline_wrong_in_files_with_under_0.3s_of_pause": wrong("pipeline", few),
        "files_with_under_0.3s_of_pause": sum(few(r) for r in judged),
        "pipeline_bias_db_by_mixed_snr": {
            str(k): {"mean": round(float(np.mean(v)), 1), "min": round(float(np.min(v)), 1), "max": round(float(np.max(v)), 1)}
            for k, v in sorted(bias.items())
        },
        "clean_files_read_below_limit": [
            (r["clip"], round(r["pipeline"], 1), r["pause_seconds"]) for r in rows if r["mixed_db"] is None and r["pipeline"] < limit
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "snr.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else config.ROOT / "reports" / "measurements")
