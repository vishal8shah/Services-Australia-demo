"""Query expansion: the person's words into the vocabulary of the pages.

This is the cheapest fix for the gap the eval suite measures. The corpus says
"constant care", "income test" and "looking for work". People say "Mum is moving
in with us" and "I got let go". No lexical retriever bridges that, and neither
does the offline embedder, so the bridge has to be built on the way in.

The expander is allowed to guess, including at payment names, because nothing it
produces can reach the user: it only changes which chunks are retrieved, and
validator rule 3 still requires every payment named in an answer to appear
verbatim in a chunk that answer cites.

What the expander must never do is manufacture confidence. Chunks retrieved
through an expansion count for less in the refusal decision than chunks that
match what the person actually said, so an expander that guesses confidently
cannot talk the system out of a refusal on its own.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

from .. import config

SYSTEM = """You rewrite a person's situation into the vocabulary used on Australian government payment pages, so a search engine can find the right pages.

Return a JSON array of at most 5 short search phrases and nothing else. Each phrase is 2 to 5 words. Prefer the words the pages themselves would use: "constant care", "care receiver", "income test", "looking for work", "activity test", "principal carer", "residence rules".

Do not answer the question. Do not explain. Do not include the person's own wording back. If the situation is already stated in official vocabulary, return an empty array."""

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


class Expander(Protocol):
    name: str

    def expand(self, question: str) -> list[str]: ...


class NullExpander:
    """No model configured. Retrieval runs on the person's own words alone."""

    name = "none"

    def expand(self, question: str) -> list[str]:
        return []


class ClaudeExpander:
    """One small, fast call per question. Uses the key you already need for synthesis."""

    name = "claude"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or config.EXPANSION_MODEL
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

    def expand(self, question: str) -> list[str]:
        body = {
            "model": self.model, "max_tokens": 200, "temperature": 0,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": question}],
        }
        req = urllib.request.Request(
            f"{config.ANTHROPIC_BASE.rstrip('/')}/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            text = "".join(b.get("text", "") for b in payload.get("content", []))
            phrases = json.loads(FENCE.sub("", text.strip()))
        except Exception:  # noqa: BLE001
            # Expansion is an optimisation. Losing it degrades retrieval, and
            # failing the whole question because of it would be worse.
            return []
        return [p.strip() for p in phrases if isinstance(p, str) and p.strip()][:5]


def get_expander(name: str | None = None) -> Expander:
    name = name or config.EXPANDER
    if name in ("none", "", None):
        return NullExpander()
    if name == "claude":
        return ClaudeExpander()
    raise ValueError(f"unknown expander: {name}")
