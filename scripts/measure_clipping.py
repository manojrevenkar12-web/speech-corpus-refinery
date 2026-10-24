"""How well does the clipping probe find clipping after lossy coding? (docs/MEASUREMENTS.md)

Ten LJSpeech clips, peak-normalised, each clipped by 0, 3, 6, 9 and 12 dB of gain (plus a quiet
copy) and stored as flac, mp3 128k, mp3 64k and ogg 96k at 44.1 kHz: 240 files. The truth is the
share of samples clipped before encoding; a file counts as clipped above the policy's 0.05%.
Compares the old test (runs of three samples at >= 0.98) with the share of samples at or above
each level of full scale, after the 16 kHz resample the pipeline analyses."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from scr import assets, config
from scr.audio import decode

CLIPS = [f"LJ001-00{n:02d}" for n in (13, 14, 25, 26, 27, 28, 29, 30, 31, 32)]
GAINS = {"clean": None, "quiet": None, "clip3": 3, "clip6": 6, "clip9": 9, "clip12": 12}
CODECS = [("flac", None), ("mp3", "128k"), ("mp3", "64k"), ("ogg", "96k")]
LEVELS = (0.85, 0.88, 0.9, 0.92, 0.95)


def runs3(x: np.ndarray, threshold: float = 0.98) -> float:
    hot = np.abs(x) >= threshold
    return float((hot[:-2] & hot[1:-1] & hot[2:]).sum()) / len(x) if len(x) > 2 else 0.0


def main(out: Path) -> None:
    files = {a.local.name: a.local for a in assets.corpus_assets()}
    limit = float(config.settings()["decide"]["max_clipped_ratio"])
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for c in CLIPS:
            x = decode.resample(files[f"{c}.wav"], 22050)
            x = x / np.abs(x).max()
            for label, g in GAINS.items():
                y = x * (0.3 if label == "quiet" else 0.999) if g is None else np.clip(x * 10 ** (g / 20), -1, 1)
                truth = 0.0 if g is None else float(np.mean(np.abs(x * 10 ** (g / 20)) >= 1))
                for codec, br in CODECS:
                    f = Path(td) / f"{c}_{label}.{codec}"
                    decode.encode(y.astype(np.float32), 22050, f, codec=codec, out_rate=44100, bitrate=br)
                    d = decode.resample(f, 16000)
                    rows.append(
                        {
                            "clip": c,
                            "case": label,
                            "codec": codec + (br or ""),
                            "truth": truth,
                            "runs3": runs3(d),
                            **{f"share_{t}": float(np.mean(np.abs(d) >= t)) for t in LEVELS},
                        }
                    )

    def score(key: str) -> dict[str, int]:
        fp = sum(r["truth"] <= limit and r[key] > limit for r in rows)
        fn = sum(r["truth"] > limit and r[key] <= limit for r in rows)
        near = sum((r["truth"] <= limit) != (r[key] <= limit) and limit / 2 < r["truth"] < limit * 2 for r in rows)
        return {"wrong": fp + fn, "false_alarms": fp, "missed": fn, "wrong_within_2x_of_limit": near}

    summary = {
        "files": len(rows),
        "clipped": sum(r["truth"] > limit for r in rows),
        "runs3_at_0.98": score("runs3"),
        **{f"share_at_{t}": score(f"share_{t}") for t in LEVELS},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "clipping.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else config.ROOT / "reports" / "measurements")
