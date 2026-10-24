"""One-off: download the pinned inputs, hash them, write config/assets.yaml."""

import csv
import hashlib
import io
import pathlib
import sys
import urllib.request

import yaml

OUT = pathlib.Path(sys.argv[1])
CACHE = pathlib.Path(sys.argv[2])
CACHE.mkdir(parents=True, exist_ok=True)
RAW = "https://raw.githubusercontent.com"
pins = {
    "lj": ("coqui-ai/TTS", "dbf1a08a0d4e47fdad6172e433eeb34bc6b13b4e"),
    "fsdd": ("Jakobovski/free-spoken-digit-dataset", "26eb9aaf76e81b692f806f9140c2d2777410d7a1"),
    "valentini": ("facebookresearch/denoiser", "8afd7c166699bb3c8b2d95b6dd706f71e1075df0"),
    "esc50": ("karolpiczak/ESC-50", "33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6"),
    "whisper": ("openai/whisper", "86098128c0b4f24f0e2aa2994de830614b474227"),
    "tacotron2": ("NVIDIA/tacotron2", "185cd24e046cc1304b4f8e564734d2498c6e2e6f"),
}


def get(url):
    p = CACHE / hashlib.sha1(url.encode()).hexdigest()  # noqa: S324 - a cache file name, not security
    if not p.exists():
        with urllib.request.urlopen(url, timeout=120) as r:
            p.write_bytes(r.read())
    return p.read_bytes()


def entry(group, path):
    repo, sha = pins[group]
    url = f"{RAW}/{repo}/{sha}/{path}"
    b = get(url)
    return {"path": path, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}


corpora = {}
# LJSpeech clips (public domain) with their transcripts
# LJSpeech chapter LJ001, the 32 clips in coqui-ai/TTS test data; transcripts from NVIDIA/tacotron2 filelists
corpora["lj"] = {
    "repo": pins["lj"][0],
    "commit": pins["lj"][1],
    "licence": "LicenseRef-PublicDomain",
    "files": [entry("lj", f"tests/data/ljspeech/wavs/LJ001-{i:04d}.wav") for i in range(1, 33)],
}
corpora["ljtext"] = {
    "repo": pins["tacotron2"][0],
    "commit": pins["tacotron2"][1],
    "licence": "LicenseRef-PublicDomain",
    "files": [entry("tacotron2", f"filelists/ljs_audio_text_{k}_filelist.txt") for k in ("train", "val", "test")],
}
spk = ["george", "jackson", "lucas", "nicolas", "theo", "yweweler"]
corpora["fsdd"] = {
    "repo": pins["fsdd"][0],
    "commit": pins["fsdd"][1],
    "licence": "CC-BY-SA-4.0",
    "files": [entry("fsdd", f"recordings/{d}_{s}_{i}.wav") for s in spk for d in range(10) for i in range(5)],
}
corpora["valentini"] = {
    "repo": pins["valentini"][0],
    "commit": pins["valentini"][1],
    "licence": "CC-BY-4.0",
    "files": [entry("valentini", f"dataset/debug/{k}/p287_00{i}.wav") for k in ("clean", "noisy") for i in range(1, 7)],
}
esc = list(csv.DictReader(io.StringIO(get(f"{RAW}/{pins['esc50'][0]}/{pins['esc50'][1]}/meta/esc50.csv").decode())))
picked, seen = [], {}
for r in esc:
    if seen.get(r["category"], 0) < 2:
        seen[r["category"]] = seen.get(r["category"], 0) + 1
        picked.append(r["filename"])
corpora["esc50"] = {
    "repo": pins["esc50"][0],
    "commit": pins["esc50"][1],
    "licence": "CC-BY-NC-3.0",
    "files": [entry("esc50", "meta/esc50.csv"), entry("esc50", "LICENSE")] + [entry("esc50", f"audio/{f}") for f in picked],
}
corpora["whisper"] = {
    "repo": pins["whisper"][0],
    "commit": pins["whisper"][1],
    "licence": "LicenseRef-PublicDomain",
    "files": [entry("whisper", "tests/jfk.flac")],
}
REL = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
models = {}
for name, url in {
    "silero_vad": f"{REL}/asr-models/silero_vad.onnx",
    "whisper_tiny": f"{REL}/asr-models/sherpa-onnx-whisper-tiny.tar.bz2",
    "ced_mini": f"{REL}/audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2",
    "wespeaker": f"{REL}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx",
    "piper_lessac": f"{REL}/tts-models/vits-piper-en_US-lessac-medium.tar.bz2",
}.items():
    b = get(url)
    models[name] = {"url": url, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
doc = {"raw_base": RAW, "corpora": corpora, "models": models}
OUT.write_text(
    "# Pinned inputs: every byte the pipeline reads is listed here with its SHA-256.\n# Written by scripts/make_assets.py; `scr fetch` downloads and verifies.\n"
    + yaml.safe_dump(doc, sort_keys=False, width=140)
)
print({k: len(v["files"]) for k, v in corpora.items()}, sum(f["bytes"] for v in corpora.values() for f in v["files"]) // 1e6, "MB corpora")
