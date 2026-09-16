"""Guard, classify, decompose, retrieve, floor, synthesise, validate, assemble.

Every exit from this function is either a contract valid answer or a refusal.
There is no third outcome, and no path that returns prose.
"""
from __future__ import annotations

import time

from . import config, store
from .answer import contract, facets as facets_mod, guard, refuse, validate as validate_mod
from .answer import language as lang_mod
from .answer.providers import ProviderError, get_provider
from .retrieve.expand import get_expander
from .retrieve.search import confidence_of, search


def answer(question: str, *, conn=None, provider=None, embedder=None, expander=None,
           language: str | None = None, top_k: int | None = None) -> dict:
    started = time.perf_counter()
    lang = language or lang_mod.detect(question)
    out = contract.empty(lang)
    out["query"] = question
    out["query_expansions"] = []

    def finish(refusal: refuse.Refusal | None = None, **meta) -> dict:
        if refusal is not None:
            out["refusal"] = refusal.to_dict()
        out["meta"] = {
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "demo_mode": config.DEMO_MODE,
            **meta,
        }
        return out

    # 1. Identifiers never leave this process, so this runs before anything else.
    found = guard.detect(question)
    if found:
        return finish(refuse.build("pii_detected", detail=", ".join(found)))

    # 2. The dangerous refusal classes are caught by pattern, not by a model
    #    choosing to behave.
    pre = refuse.classify(question)
    if pre is not None:
        return finish(pre)

    # 3. Decompose, then retrieve for the sentence and for each facet.
    facet_list = facets_mod.decompose(question)
    out["query_facets"] = facet_list
    expander = expander or get_expander()
    expansions = expander.expand(question)
    out["query_expansions"] = expansions

    if conn is None:
        with store.connect() as owned_conn:
            return _retrieve_and_answer(owned_conn, question, facet_list, expansions,
                                        lang, out, finish, provider, embedder, top_k)
    return _retrieve_and_answer(conn, question, facet_list, expansions, lang, out,
                                finish, provider, embedder, top_k)


def _retrieve_and_answer(conn, question, facet_list, expansions, lang, out, finish,
                         provider, embedder, top_k):
    hits = search(conn, question, facets=facet_list, expansions=expansions,
                  top_k=top_k, embedder=embedder)
    confidence = confidence_of(hits)
    out["confidence"] = round(confidence, 4)

    # Kept on every response, answered or refused. Without it there is no way to
    # tell a retriever that missed the page from a generator that had the page and
    # did not use it, and those two failures need opposite fixes.
    retrieved_titles = sorted({h.chunk.title for h in hits})

    if not hits or confidence < config.SCORE_FLOOR:
        return finish(refuse.build("low_confidence",
                                   detail=f"confidence {confidence:.3f} below floor "
                                          f"{config.SCORE_FLOOR}"),
                      hits=len(hits), retrieved_titles=retrieved_titles)

    if provider is None:
        provider = get_provider("fixture" if config.DEMO_MODE == "static" else None)

    raw = None
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            raw = provider.answer(question, facet_list, hits, lang)
        except ProviderError as exc:
            return finish(refuse.build("low_confidence", detail=str(exc)),
                          provider=getattr(provider, "name", "?"), hits=len(hits))
        result = validate_mod.validate(raw, hits)
        if result.ok:
            return _assemble(out, result, hits, finish, provider, attempt,
                             retrieved_titles)
        errors = result.errors
        # Rule 5: one retry, then refuse. A second failure is a real defect, not
        # a formatting accident, and retrying it just burns the user's time.
        if attempt == 2 or not any(e.startswith("shape") for e in errors):
            break

    return finish(refuse.build("low_confidence", detail="; ".join(errors[:3])),
                  provider=getattr(provider, "name", "?"), hits=len(hits),
                  retrieved_titles=retrieved_titles, validator_errors=errors)


def _assemble(out, result, hits, finish, provider, attempts, retrieved_titles):
    response = result.response
    out["payments"] = response.get("payments", [])
    out["next_actions"] = sorted(response.get("next_actions", []),
                                 key=lambda a: a.get("order", 99))
    out["not_answered"] = response.get("not_answered", [])

    by_id = {h.chunk.chunk_id: h for h in hits}
    cited = contract.cited_ids(response)
    out["sources"] = [by_id[c].chunk.cite() for c in sorted(cited) if c in by_id]
    out["stale_sources"] = [s["id"] for s in out["sources"] if s["stale"]]

    return finish(None,
                  provider=getattr(provider, "name", "?"),
                  hits=len(hits),
                  attempts=attempts,
                  retrieved_titles=retrieved_titles,
                  validator_warnings=result.warnings)
