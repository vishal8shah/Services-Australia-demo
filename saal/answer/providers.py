"""Answer providers behind one method, so the harness never needs a network.

- anthropic : the real thing
- stub      : deterministic composition from the retrieved chunks, no model at
              all. It exists so the contract, the validator and the scorer can be
              exercised offline. It is not a model and its scores are a floor,
              not a result.
- fixture   : replays recorded responses, keyed by question, for a deterministic
              suite once you have recorded a run against the real model.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Protocol

from .. import config
from ..retrieve.search import Hit
from .synthesize import SYSTEM, build_user_message

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def answer(self, question: str, facets: list[str], hits: list[Hit],
               language: str) -> dict: ...


def _parse_json(text: str) -> dict:
    cleaned = FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(cleaned[start:end + 1])


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or config.LLM_MODEL
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")

    def answer(self, question, facets, hits, language="en") -> dict:
        body = {
            "model": self.model,
            "max_tokens": 2000,
            "temperature": 0,
            "system": SYSTEM,
            "messages": [{"role": "user",
                          "content": build_user_message(question, facets, hits, language)}],
        }
        req = urllib.request.Request(
            f"{config.ANTHROPIC_BASE.rstrip('/')}/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
        text = "".join(b.get("text", "") for b in payload.get("content", []))
        return _parse_json(text)


class StubProvider:
    """Composes an answer from chunk structure alone. Deterministic, no model.

    It reads the heading path the way a person skimming the page would: the
    section called "Who can get it" holds the eligibility signals, the section
    called "How to claim" holds the next action.
    """

    name = "stub"
    ELIGIBILITY = re.compile(r"who can get|eligib|you must|qualif", re.I)
    CLAIM = re.compile(r"how to claim|claim|apply|what you (need|should) do", re.I)

    def answer(self, question, facets, hits, language="en") -> dict:
        by_page: dict[str, list[Hit]] = {}
        for h in hits:
            by_page.setdefault(h.chunk.url, []).append(h)

        # Rank pages by their best hit, then drop the tail. Without this the stub
        # reports whatever the retriever returned eighth, which is noise wearing
        # the same shape as an answer.
        ranked = sorted(by_page.items(), key=lambda kv: max(h.score for h in kv[1]),
                        reverse=True)
        best_coverage = max((h.coverage for h in hits), default=0.0)
        pages = [(url, group) for url, group in ranked
                 if max(h.coverage for h in group) >= best_coverage * 0.5][:2]
        kept_urls = {url for url, _ in pages}

        payments = []
        for _url, group in pages:
            title = group[0].chunk.title
            lead = self._first_sentence(group[0].chunk.text)
            signals = []
            for h in group:
                if self.ELIGIBILITY.search(h.chunk.heading_path):
                    for line in self._lines(h.chunk.text)[:3]:
                        signals.append({"text": line, "source_ids": [h.chunk.chunk_id]})
            if not signals:
                signals = [{"text": lead, "source_ids": [group[0].chunk.chunk_id]}]
            payments.append({
                "name": title,
                "one_liner": lead,
                "distinguisher": None,
                "eligibility_signals": signals[:4],
                "source_ids": [h.chunk.chunk_id for h in group],
            })

        actions = []
        for h in hits:
            if (h.chunk.url in kept_urls and self.CLAIM.search(h.chunk.heading_path)
                    and len(actions) < 3):
                actions.append({
                    "order": len(actions) + 1,
                    "text": self._first_sentence(h.chunk.text),
                    "url": h.chunk.url,
                    "source_ids": [h.chunk.chunk_id],
                })
        if not actions and pages:
            h = pages[0][1][0]
            actions = [{"order": 1, "text": f"Read the {h.chunk.title} page in full.",
                        "url": h.chunk.url, "source_ids": [h.chunk.chunk_id]}]

        return {
            "payments": payments,
            "next_actions": actions,
            "not_answered": ["How much you would receive: this tool does not quote amounts."],
        }

    @staticmethod
    def _first_sentence(text: str) -> str:
        flat = " ".join(t.strip(" -") for t in text.splitlines() if t.strip())
        return SENTENCE.split(flat)[0].strip() if flat else ""

    @staticmethod
    def _lines(text: str) -> list[str]:
        out = []
        for line in text.splitlines():
            line = line.strip(" -\t")
            if len(line) > 15:
                out.append(line)
        return out


class FixtureProvider:
    """Replays recorded responses keyed by the question text."""

    name = "fixture"

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or config.ROOT / "evals" / "fixtures" / "llm.json")
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    @staticmethod
    def key(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def answer(self, question, facets, hits, language="en") -> dict:
        k = self.key(question)
        if k not in self.data:
            raise ProviderError(f"no fixture recorded for: {question!r}")
        return self.data[k]


class RecordingProvider:
    """Wraps a real provider and writes every response to a fixture file.

    Record once against the model, then run the suite a hundred times offline
    without paying for it or waiting for it.
    """

    def __init__(self, inner: Provider, path: Path | str | None = None) -> None:
        self.inner = inner
        self.name = f"recording:{inner.name}"
        self.path = Path(path or config.ROOT / "evals" / "fixtures" / "llm.json")
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def answer(self, question, facets, hits, language="en") -> dict:
        out = self.inner.answer(question, facets, hits, language)
        self.data[FixtureProvider.key(question)] = out
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        return out


def get_provider(name: str | None = None) -> Provider:
    name = name or config.LLM_PROVIDER
    base: Provider
    if name == "anthropic":
        base = AnthropicProvider()
    elif name == "stub":
        base = StubProvider()
    elif name == "fixture":
        base = FixtureProvider()
    else:
        raise ValueError(f"unknown provider: {name}")
    if os.environ.get("SAAL_RECORD") == "1" and name == "anthropic":
        return RecordingProvider(base)
    return base
