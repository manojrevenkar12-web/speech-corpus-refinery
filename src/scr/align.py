"""Matching what Whisper heard to the text the source published (LibriVox books point to their
text, schema.org pages may carry a transcript). The matched span of the published text, with
its punctuation and casing, becomes the segment's transcript, as Libriheavy does; the character
error rate between ASR and that span measures how well audio and text agree."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_WORD = re.compile(r"[a-z0-9']+")


def norm_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return _WORD.findall(t)


def cer(ref: str, hyp: str) -> float:
    r, h = " ".join(norm_words(ref)), " ".join(norm_words(hyp))
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / len(r)


@dataclass
class Aligned:
    text: str
    cer: float
    start_word: int
    end_word: int


class Book:
    """Published text, tokenised once, with an index of word trigrams for fast lookup."""

    def __init__(self, text: str) -> None:
        self.raw_tokens: list[str] = re.findall(r"\S+", text)
        self.words: list[str] = []
        self.owner: list[int] = []  # normalised word -> raw token index
        for i, tok in enumerate(self.raw_tokens):
            for w in norm_words(tok):
                self.words.append(w)
                self.owner.append(i)
        self.grams: dict[tuple[str, ...], list[int]] = {}
        for i in range(len(self.words) - 2):
            self.grams.setdefault(tuple(self.words[i : i + 3]), []).append(i)

    def align(self, asr: str, hint: int = 0) -> Aligned | None:
        hyp = norm_words(asr)
        if len(hyp) < 2 or not self.words:
            return None
        votes: dict[int, int] = {}
        for i in range(len(hyp) - 2):
            for pos in self.grams.get(tuple(hyp[i : i + 3]), ()):
                start = pos - i
                votes[start] = votes.get(start, 0) + 1
        start = max(votes, key=lambda s: (votes[s], -abs(s - hint))) if votes else hint
        lo = max(0, start - 5)
        hi = min(len(self.words), start + len(hyp) + 5)
        window = self.words[lo:hi]
        sm = SequenceMatcher(a=window, b=hyp, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        if not blocks:
            return None
        a0 = lo + blocks[0].a
        a1 = lo + blocks[-1].a + blocks[-1].size
        # extend to cover words ASR missed at the edges
        a0 = max(lo, a0 - blocks[0].b)
        a1 = min(hi, a1 + (len(hyp) - blocks[-1].b - blocks[-1].size))
        text = " ".join(self.raw_tokens[self.owner[a0] : self.owner[a1 - 1] + 1])
        return Aligned(text, cer(text, asr), a0, a1)
