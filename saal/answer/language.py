"""Script based language detection, deliberately small.

Enough to route the three demo languages plus English without a dependency. When
the anthropic provider is configured the model does its own detection from the
question, and this only decides the interface direction. Replace it with a real
detector before anyone relies on it.
"""
from __future__ import annotations

import re

RANGES = [
    ("zh", re.compile(r"[一-鿿]")),
    ("ar", re.compile(r"[؀-ۿ]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
    ("ko", re.compile(r"[가-힯]")),
    ("ja", re.compile(r"[぀-ヿ]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("el", re.compile(r"[Ͱ-Ͽ]")),
]
VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ]|[̀-̣]")
RTL = {"ar", "fa", "he", "ur"}

NAMES = {"en": "English", "zh": "Simplified Chinese", "ar": "Arabic",
         "vi": "Vietnamese", "hi": "Hindi", "ko": "Korean", "ja": "Japanese",
         "ru": "Russian", "el": "Greek"}


def detect(text: str) -> str:
    for code, pattern in RANGES:
        if pattern.search(text):
            return code
    if VIETNAMESE.search(text):
        return "vi"
    return "en"


def name(code: str) -> str:
    return NAMES.get(code, code)


def is_rtl(code: str) -> bool:
    return code in RTL
