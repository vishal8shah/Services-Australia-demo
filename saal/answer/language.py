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
    ("pa", re.compile("[਀-੿]")),
    ("bn", re.compile("[ঀ-৿]")),
    ("ta", re.compile("[஀-௿]")),
    ("si", re.compile("[඀-෿]")),
    ("th", re.compile("[฀-๿]")),
]
VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ]|[̀-̣]")
RTL = {"ar", "fa", "he", "ur"}

# The languages most spoken at home in Australia after English, plus a few more.
# The interface lets a person pick one, which is what separates Italian from English
# when the script cannot. Codes are BCP 47 primary subtags, "yue" is Cantonese.
NAMES = {"en": "English", "zh": "Simplified Chinese", "yue": "Cantonese (Traditional Chinese script)",
         "ar": "Arabic", "vi": "Vietnamese", "pa": "Punjabi", "el": "Greek",
         "it": "Italian", "hi": "Hindi", "ne": "Nepali", "tl": "Tagalog", "fil": "Filipino",
         "es": "Spanish", "ko": "Korean", "ja": "Japanese", "ta": "Tamil", "ur": "Urdu",
         "fa": "Persian", "id": "Indonesian", "th": "Thai", "ru": "Russian", "tr": "Turkish",
         "bn": "Bengali", "si": "Sinhala", "ml": "Malayalam", "te": "Telugu", "gu": "Gujarati",
         "mk": "Macedonian", "hr": "Croatian", "sr": "Serbian", "pl": "Polish", "pt": "Portuguese",
         "fr": "French", "de": "German", "so": "Somali", "sw": "Swahili", "my": "Burmese",
         "km": "Khmer", "am": "Amharic", "he": "Hebrew"}


def detect(text: str) -> str:
    for code, pattern in RANGES:
        if pattern.search(text):
            return code
    if VIETNAMESE.search(text):
        return "vi"
    return "en"


def name(code: str) -> str:
    return NAMES.get(code, NAMES.get(code.split("-")[0].lower(), code))


def normalise(code: str | None) -> str | None:
    """"vi-VN" from a speech recogniser becomes "vi"; Cantonese keeps "yue"."""
    if not code:
        return None
    c = code.strip().lower()
    if c in ("zh-hk", "zh-tw", "yue-hk"):
        return "yue"
    primary = c.split("-")[0]
    return primary if re.fullmatch(r"[a-z]{2,3}", primary) else None


def is_rtl(code: str) -> bool:
    return code in RTL
