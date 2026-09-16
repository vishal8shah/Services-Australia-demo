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
EMBED_DIMS = int(os.environ.get("SAAL_EMBED_DIMS", "512"))
LLM_PROVIDER = os.environ.get("SAAL_LLM_PROVIDER", "stub")
LLM_MODEL = os.environ.get("SAAL_MODEL", "claude-sonnet-5")
JUDGE_MODEL = os.environ.get("SAAL_JUDGE_MODEL", "claude-opus-5")
ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# Presentation
DEMO_MODE = os.environ.get("SAAL_DEMO_MODE", "live")  # live | static
PHONE_GENERAL = "132 850"
