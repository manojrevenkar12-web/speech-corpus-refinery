"""The models, run on CPU through sherpa-onnx: Silero VAD, Whisper tiny (language ID and ASR),
CED audio tagging (AudioSet labels, including Speech, Music and Speech synthesizer) and a
WeSpeaker speaker-embedding model. Each is loaded once per process."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from typing import Any

import numpy as np

from .. import assets, config

THREADS = int(os.environ.get("SCR_MODEL_THREADS", "1"))


@dataclass
class Span:
    start: float
    end: float


def _so() -> Any:
    import sherpa_onnx

    return sherpa_onnx


@cache
def _vad_config() -> object:
    so = _so()
    s = config.settings()["segment"]
    cfg = so.VadModelConfig()
    cfg.silero_vad.model = str(assets.model_dir("silero_vad") / "silero_vad.onnx")
    cfg.silero_vad.min_silence_duration = float(s["vad_min_silence"])
    cfg.silero_vad.threshold = float(s["vad_threshold"])
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = float(s["max_seconds"])
    cfg.sample_rate = 16000
    cfg.num_threads = THREADS
    return cfg


def vad(x: np.ndarray, rate: int = 16000) -> list[Span]:
    """Speech regions. Silero splits regions longer than the maximum segment length."""
    assert rate == 16000
    so = _so()
    cfg = _vad_config()
    det = so.VoiceActivityDetector(cfg, buffer_size_in_seconds=max(60, int(len(x) / rate) + 10))
    w = cfg.silero_vad.window_size  # type: ignore[attr-defined]
    out: list[Span] = []

    def drain() -> None:
        while not det.empty():
            s = det.front
            out.append(Span(s.start / rate, (s.start + len(s.samples)) / rate))
            det.pop()

    for i in range(0, len(x), w):
        chunk = x[i : i + w]
        if len(chunk) < w:
            chunk = np.pad(chunk, (0, w - len(chunk)))
        det.accept_waveform(chunk)
        drain()
    det.flush()
    drain()
    return out


def speech_mask(spans: list[Span], seconds: float, hop: float = 0.010) -> np.ndarray:
    m = np.zeros(int(seconds / hop) + 1, bool)
    for s in spans:
        m[int(s.start / hop) : int(s.end / hop) + 1] = True
    return m


@cache
def _whisper() -> tuple[str, str, str]:
    d = assets.model_dir("whisper_tiny")
    return str(d / "tiny-encoder.int8.onnx"), str(d / "tiny-decoder.int8.onnx"), str(d / "tiny-tokens.txt")


@cache
def _recognizer(language: str) -> object:
    enc, dec, tok = _whisper()
    return _so().OfflineRecognizer.from_whisper(
        encoder=enc, decoder=dec, tokens=tok, language=language, task="transcribe", num_threads=THREADS
    )


def transcribe(x: np.ndarray, language: str = "en") -> str:
    rec = _recognizer(language)
    s = rec.create_stream()  # type: ignore[attr-defined]
    s.accept_waveform(16000, x)
    rec.decode_stream(s)  # type: ignore[attr-defined]
    return str(s.result.text).strip()


@cache
def _lid() -> object:
    so = _so()
    enc, dec, _ = _whisper()
    cfg = so.SpokenLanguageIdentificationConfig(
        whisper=so.SpokenLanguageIdentificationWhisperConfig(encoder=enc, decoder=dec), num_threads=THREADS
    )
    return so.SpokenLanguageIdentification(cfg)


def language(x: np.ndarray) -> str:
    lid = _lid()
    s = lid.create_stream()  # type: ignore[attr-defined]
    s.accept_waveform(16000, x[: 16000 * 30])
    return str(lid.compute(s))  # type: ignore[attr-defined]


@cache
def _tagger() -> object:
    so = _so()
    d = assets.model_dir("ced_mini")
    cfg = so.AudioTaggingConfig(
        model=so.AudioTaggingModelConfig(ced=str(d / "model.int8.onnx"), num_threads=THREADS),
        labels=str(d / "class_labels_indices.csv"),
        top_k=527,
    )
    return so.AudioTagging(cfg)


TAGS = {"speech": "Speech", "music": "Music", "synthesizer": "Speech synthesizer"}


def tags(x: np.ndarray, window: float = 10.0) -> dict[str, float]:
    """AudioSet probabilities for speech, music and synthesized speech: the mean over 10 s
    windows (speech, synthesizer) and the maximum (music: a jingle in one window is enough)."""
    tg = _tagger()
    per: dict[str, list[float]] = {k: [] for k in TAGS}
    n = int(16000 * window)
    for i in range(0, max(len(x), 1), n):
        chunk = x[i : i + n]
        if len(chunk) < 16000 and i > 0:
            break
        s = tg.create_stream()  # type: ignore[attr-defined]
        s.accept_waveform(16000, chunk)
        got = {e.name: float(e.prob) for e in tg.compute(s)}  # type: ignore[attr-defined]
        for k, label in TAGS.items():
            per[k].append(got.get(label, 0.0))
    return {
        "speech": float(np.mean(per["speech"])) if per["speech"] else 0.0,
        "music": float(np.max(per["music"])) if per["music"] else 0.0,
        "synthesizer": float(np.mean(per["synthesizer"])) if per["synthesizer"] else 0.0,
    }


@cache
def _embedder() -> object:
    so = _so()
    d = assets.model_dir("wespeaker")
    return so.SpeakerEmbeddingExtractor(
        so.SpeakerEmbeddingExtractorConfig(model=str(d / "wespeaker_en_voxceleb_resnet34.onnx"), num_threads=THREADS)
    )


def embedding(x: np.ndarray) -> np.ndarray:
    ex = _embedder()
    s = ex.create_stream()  # type: ignore[attr-defined]
    s.accept_waveform(16000, x)
    s.input_finished()
    e = np.asarray(ex.compute(s), dtype=np.float32)  # type: ignore[attr-defined]
    return e / (np.linalg.norm(e) + 1e-9)


@cache
def _tts() -> object:
    so = _so()
    d = assets.model_dir("piper_lessac")
    return so.OfflineTts(
        so.OfflineTtsConfig(
            model=so.OfflineTtsModelConfig(
                vits=so.OfflineTtsVitsModelConfig(
                    model=str(d / "en_US-lessac-medium.onnx"), tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data")
                ),
                num_threads=THREADS,
            )
        )
    )


def synthesize(text: str, speed: float = 1.0) -> tuple[np.ndarray, int]:
    """Piper TTS: used only to build the synthetic site of the test world (never released)."""
    a = _tts().generate(text, sid=0, speed=speed)  # type: ignore[attr-defined]
    return np.asarray(a.samples, dtype=np.float32), int(a.sample_rate)
