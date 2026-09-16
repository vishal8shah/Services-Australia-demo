"""Identifier detection, run before retrieval and before any model call.

An identifier must never leave this process, so this is a regex pass on the raw
input rather than anything cleverer. It fails closed: a false positive costs the
user one rephrase, a false negative sends a customer reference number to a model
provider. Those costs are not symmetric.
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("crn", re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\s?[A-Za-z]\b")),
    ("medicare", re.compile(r"\b[2-6]\d{3}\s?\d{5}\s?\d\b")),
    ("tfn", re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("date_of_birth", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    ("bank_account", re.compile(r"\b\d{2}[- ]?\d{3}[- ]?\d{3}\b(?=.*\b(bsb|account)\b)", re.I)),
]


def detect(text: str) -> list[str]:
    """Return the kinds of identifier found, most specific first."""
    found: list[str] = []
    for kind, pattern in PATTERNS:
        if pattern.search(text):
            found.append(kind)
    # A CRN match also matches the looser TFN digits pattern: report the specific one.
    if "crn" in found and "tfn" in found:
        found.remove("tfn")
    return found


def redact(text: str) -> str:
    """For logs only. The raw input is never written to disk anywhere in this codebase."""
    out = text
    for kind, pattern in PATTERNS:
        out = pattern.sub(f"<{kind}>", out)
    return out
