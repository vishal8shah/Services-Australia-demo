"""Query decomposition: one sentence into the separate situations it carries.

This is the single highest leverage step in the pipeline. "Mum is 82 and moving in
with us, I have dropped to three days a week" is two questions, and a system that
retrieves against the whole sentence answers the louder one and drops the other.
The heuristic split below runs with no model and no network. With a model
configured it is replaced by a model pass, which handles the sentences where the
situations are not separated by punctuation at all.
"""
from __future__ import annotations

import re

SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bbut\b|\bwhile\b|\balso\b|\bplus\b|\.)\s+", re.I)
STOPWORDS = {
    "i", "we", "my", "our", "me", "us", "it", "is", "am", "are", "was", "were", "the",
    "a", "an", "to", "of", "in", "on", "at", "so", "and", "but", "now", "just", "have",
    "has", "had", "do", "does", "did", "this", "that", "for", "with", "he", "she", "they",
}
CARRY = re.compile(r"^(i|we|my|our|she|he|they|it)\b", re.I)


def is_meaningful(fragment: str) -> bool:
    words = [w for w in re.findall(r"[a-z']+", fragment.lower()) if w not in STOPWORDS]
    return len(words) >= 2


def decompose(question: str, max_facets: int = 4) -> list[str]:
    """Heuristic split. Returns [] when the sentence carries a single situation.

    Short fragments are merged into their neighbour rather than dropped: "Mum is
    82" and "moving in with us" are one situation, and splitting them produces two
    weak queries instead of one good one.
    """
    raw = [f.strip(" .,;") for f in SPLIT.split(question) if f.strip(" .,;")]

    merged: list[str] = []
    for fragment in raw:
        short = len(fragment.split()) <= 3
        prev_short = bool(merged) and len(merged[-1].split()) <= 3
        bare_pronoun = bool(CARRY.match(fragment)) and len(fragment.split()) <= 3
        if merged and (short or prev_short or bare_pronoun):
            merged[-1] = f"{merged[-1]}, {fragment}"
        else:
            merged.append(fragment)

    facets = [f for f in merged if is_meaningful(f)]
    if len(facets) < 2:
        return []
    return facets[:max_facets]
