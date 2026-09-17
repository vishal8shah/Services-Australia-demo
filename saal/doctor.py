"""Check that what you have configured actually works, before you rely on it.

Run this the moment you add a key. It makes one cheap call per configured
provider and tells you which of the three roles, embeddings, synthesis and query
expansion, are live. Everything it reports is what the pipeline itself would do,
so a pass here means the pipeline will not surprise you on the demo.

    python3 -m saal.doctor
"""
from __future__ import annotations

import os
import sys

from . import config, store
from .ingest.embed import get_embedder
from .llm import LLMError, chat

OK, BAD, SKIP = "  ok  ", " FAIL ", " skip "


def line(status: str, role: str, detail: str) -> None:
    print(f"[{status}] {role:<22} {detail}")


def check_environment() -> bool:
    ok = sys.version_info >= (3, 11)
    line(OK if ok else BAD, "python",
         f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
         + ("" if ok else ", this project needs 3.11 or newer"))
    if config.ENV_LOADED:
        for path in config.ENV_LOADED:
            line(OK, "env file", f"loaded {path}")
    else:
        line(SKIP, "env file",
             "none found, reading the shell environment only. cp .env.example .env")
    print()
    return ok


def check_keys() -> None:
    print("keys found in the environment")
    for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "VOYAGE_API_KEY"):
        value = os.environ.get(env)
        shown = f"set, {len(value)} characters" if value else "not set"
        line(OK if value else SKIP, env, shown)
    print()


def check_embeddings() -> bool:
    name = config.EMBED_PROVIDER
    try:
        embedder = get_embedder(name)
        vector = embedder.embed(["constant care"])[0]
    except Exception as exc:  # noqa: BLE001 the point is to report it, not raise
        line(BAD, f"embeddings [{name}]", str(exc)[:90])
        return False
    detail = f"{len(vector)} dimensions"
    if name == "hashing":
        detail += ", spelling only, no semantic matching"
    line(OK, f"embeddings [{name}]", detail)
    return True


def check_synthesis() -> bool:
    name = config.LLM_PROVIDER
    if name in ("stub", "fixture"):
        line(SKIP, f"synthesis [{name}]", "no model configured, answers come from chunk structure")
        return True
    try:
        reply = chat("Reply with the JSON object {\"ok\": true} and nothing else.",
                     "ping", provider=name, model=config.model_for(name),
                     max_tokens=20, timeout=30)
    except LLMError as exc:
        line(BAD, f"synthesis [{name}]", str(exc)[:90])
        return False
    line(OK, f"synthesis [{name}]", f"{config.model_for(name)} replied {reply.strip()[:40]!r}")
    return True


def check_expansion() -> bool:
    name = config.EXPANDER
    if name in ("none", ""):
        line(SKIP, "query expansion [none]",
             "situation questions will refuse unless the embedder is semantic")
        return True
    provider = "anthropic" if name == "claude" else name
    try:
        from .retrieve.expand import get_expander
        phrases = get_expander(name).expand(
            "Mum is 82 and moving in with us, I have dropped to three days a week.")
    except Exception as exc:  # noqa: BLE001
        line(BAD, f"query expansion [{provider}]", str(exc)[:90])
        return False
    if not phrases:
        line(BAD, f"query expansion [{provider}]",
             "returned nothing, which silently degrades retrieval")
        return False
    line(OK, f"query expansion [{provider}]", ", ".join(phrases)[:80])
    return True


def check_corpus() -> bool:
    if not config.DB_PATH.exists():
        line(SKIP, "corpus", f"no database at {config.DB_PATH}, run make crawl then make index")
        return True
    with store.connect() as conn:
        counts = store.counts(conn)
    if not counts["chunks"]:
        line(BAD, "corpus", "database exists but holds no chunks, run make index")
        return False
    expected = f"{config.EMBED_PROVIDER}:"
    stored = counts.get("embedder") or "unknown"
    if not stored.startswith(expected):
        line(BAD, "corpus",
             f"embedded with {stored} but configured for {config.EMBED_PROVIDER}, rerun make index")
        return False
    line(OK, "corpus", f"{counts['chunks']} chunks, {counts['pages']} pages, embedded {stored}")
    return True


def main() -> int:
    print(f"demo mode: {config.DEMO_MODE}\n")
    print("environment")
    environment_ok = check_environment()
    check_keys()
    print("roles")
    results = [environment_ok, check_embeddings(), check_synthesis(),
               check_expansion(), check_corpus()]
    print()
    if all(results):
        print("all configured roles are working")
        return 0
    print("something configured is not working, see FAIL above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
