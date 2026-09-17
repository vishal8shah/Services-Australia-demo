"""Every tunable in one place, all overridable by environment variable.

Retrieval thresholds live here rather than in the prompt, because a threshold
you cannot grep is a threshold you cannot tune against the eval suite.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("SAAL_DATA", ROOT / "data"))
RAW = DATA / "raw"
DB_PATH = Path(os.environ.get("SAAL_DB", DATA / "corpus.db"))

# Crawl
BASE = "https://www.servicesaustralia.gov.au"
SITEMAP = os.environ.get("SAAL_SITEMAP", f"{BASE}/sitemap.xml")
INCLUDE_PREFIXES = tuple(
    p for p in os.environ.get("SAAL_INCLUDE", "/individuals/").split(",") if p
)
USER_AGENT = os.environ.get(
    "SAAL_UA",
    "saal-research-prototype/0.1 (unofficial; contact via repository issues)",
)
CRAWL_DELAY = float(os.environ.get("SAAL_CRAWL_DELAY", "2.0"))

# Chunking
MAX_CHUNK_CHARS = int(os.environ.get("SAAL_MAX_CHUNK_CHARS", "1800"))
MIN_CHUNK_CHARS = int(os.environ.get("SAAL_MIN_CHUNK_CHARS", "120"))

# Retrieval
TOP_K = int(os.environ.get("SAAL_TOP_K", "8"))
CANDIDATES = int(os.environ.get("SAAL_CANDIDATES", "50"))
RRF_K = int(os.environ.get("SAAL_RRF_K", "60"))
VECTOR_CANDIDATES = int(os.environ.get("SAAL_VECTOR_CANDIDATES", "20"))
# A facet is a fragment of the question, so it gets less of a vote than the
# whole sentence. Raising this to 1.0 lets three facets outvote what was asked.
FACET_WEIGHT = float(os.environ.get("SAAL_FACET_WEIGHT", "0.7"))
# Confidence floor below which we refuse rather than answer. Tuned on the
# golden suite, never on a single hand run question.
SCORE_FLOOR = float(os.environ.get("SAAL_SCORE_FLOOR", "0.30"))

# Freshness
STALE_AFTER_DAYS = int(os.environ.get("SAAL_STALE_AFTER_DAYS", "548"))  # 18 months

# Providers
EMBED_PROVIDER = os.environ.get("SAAL_EMBED_PROVIDER", "hashing")
EMBED_DIMS = int(os.environ.get("SAAL_EMBED_DIMS", "1024"))
CHAR_NGRAM_WEIGHT = float(os.environ.get("SAAL_CHAR_NGRAM_WEIGHT", "0.35"))

# stub and fixture need no key and no network. anthropic and openai need theirs.
LLM_PROVIDER = os.environ.get("SAAL_LLM_PROVIDER", "stub")
# Query expansion bridges the person's words to the vocabulary of the pages.
# Set to anthropic or openai. It costs one small call per question.
EXPANDER = os.environ.get("SAAL_EXPANDER", "none")
JUDGE_PROVIDER = os.environ.get("SAAL_JUDGE_PROVIDER", "")

ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")

# Model names change and get retired, so every one of these is overridable and
# none of them is hard coded at a call site. Check what your key can see with:
#   curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4o-mini"}
FAST_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini"}
OPENAI_EMBED_MODEL = os.environ.get("SAAL_OPENAI_EMBED_MODEL", "text-embedding-3-small")
# Cosine runs in pure Python, so dimensions are latency. text-embedding-3-*
# supports shortening natively and stays usable well below its full width.
OPENAI_EMBED_DIMS = int(os.environ.get("SAAL_OPENAI_EMBED_DIMS", "512"))


def model_for(provider: str) -> str:
    """The model for synthesis, unless SAAL_MODEL overrides it."""
    return os.environ.get("SAAL_MODEL") or DEFAULT_MODELS.get(provider, "")


def fast_model_for(provider: str) -> str:
    """Expansion and judging want the cheap fast model, not the good one."""
    return os.environ.get("SAAL_FAST_MODEL") or FAST_MODELS.get(provider, "")


# Evidence reached through an expansion is second hand, so it counts for less
# in the refusal decision than evidence matching what the person actually said.
EXPANSION_WEIGHT = float(os.environ.get("SAAL_EXPANSION_WEIGHT", "0.5"))

# Presentation
DEMO_MODE = os.environ.get("SAAL_DEMO_MODE", "live")  # live | static
PHONE_GENERAL = "132 850"
