"""The six validator rules, enforced in code after generation.

Prompt instructions are not a control. Everything that must be true of a response
is checked here, against the retrieved set, with no model in the loop.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..retrieve.search import Hit
from . import contract

MONEY = re.compile(
    r"(\$\s?[\d,]+(?:\.\d+)?)"
    r"|(\b\d[\d,]*(?:\.\d+)?\s?(?:dollars|per fortnight|a fortnight|per week|a week|"
    r"per year|a year)\b)", re.I)
TIMING = re.compile(
    r"(\b\d+\s*(?:to\s*\d+\s*)?(?:business\s*)?(?:days?|weeks?|months?)\b[^.]{0,60}"
    r"\b(?:process|processed|processing|wait|waiting|assess|assessed|decision)\b)"
    r"|(\b(?:process|processing|wait|waiting|assessment)\b[^.]{0,60}"
    r"\b\d+\s*(?:to\s*\d+\s*)?(?:business\s*)?(?:days?|weeks?|months?)\b)", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Result:
    ok: bool
    response: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    refusal_class: str | None = None


def searchable(hit: Hit) -> str:
    c = hit.chunk
    return f"{c.title}\n{c.heading_path}\n{c.text}".lower()


def strip_forbidden(text: str) -> tuple[str, list[str]]:
    """Rule 6. Remove any sentence carrying a dollar figure or a processing time."""
    removed: list[str] = []
    kept: list[str] = []
    for sentence in SENTENCE.split(text or ""):
        if MONEY.search(sentence) or TIMING.search(sentence):
            removed.append(sentence.strip())
        else:
            kept.append(sentence)
    return " ".join(k for k in kept if k).strip(), removed


def validate(response: dict, hits: list[Hit]) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    retrieved = {h.chunk.chunk_id: h for h in hits}
    out = dict(response)

    # Rule 5: shape.
    shape = contract.shape_errors(out)
    if shape:
        return Result(False, out, [f"shape: {e}" for e in shape], warnings, "low_confidence")

    # Rule 1: every cited id was actually retrieved for this query.
    unknown = sorted(contract.cited_ids(out) - set(retrieved))
    if unknown:
        errors.append(f"rule 1: cited ids not in the retrieved set: {unknown}")

    # Rule 2: every claim carries at least one source id. (Shape already checked
    # presence: this catches empty lists that slipped through as [""].)
    for p in out.get("payments", []):
        for sig in p.get("eligibility_signals", []):
            if not [s for s in (sig.get("source_ids") or []) if s]:
                errors.append(f"rule 2: unsourced eligibility signal in {p.get('name')!r}")
    for a in out.get("next_actions", []):
        if not [s for s in (a.get("source_ids") or []) if s]:
            errors.append(f"rule 2: unsourced next action {a.get('text')!r}")

    # Rule 3: the payment name must appear verbatim in a chunk that payment cites.
    for p in out.get("payments", []):
        name = (p.get("name") or "").strip()
        cites = [retrieved[s] for s in (p.get("source_ids") or []) if s in retrieved]
        if not name:
            errors.append("rule 3: payment with no name")
            continue
        if not any(name.lower() in searchable(h) for h in cites):
            errors.append(f"rule 3: payment name not present in its cited chunks: {name!r}")

    # Rule 4: an action url must belong to a chunk that action cites.
    for a in out.get("next_actions", []):
        url = a.get("url")
        if not url:
            continue
        allowed = {retrieved[s].chunk.url for s in (a.get("source_ids") or []) if s in retrieved}
        if url not in allowed:
            warnings.append(f"rule 4: url stripped, not from a cited source: {url}")
            a["url"] = None

    # Rule 6: no dollar figures, wait times or processing times anywhere.
    not_answered = list(out.get("not_answered") or [])
    for p in out.get("payments", []):
        for key in ("one_liner", "distinguisher"):
            if p.get(key):
                cleaned, removed = strip_forbidden(p[key])
                if removed:
                    p[key] = cleaned or None
                    warnings.append(f"rule 6: stripped from {p.get('name')} {key}")
        kept_signals = []
        for sig in p.get("eligibility_signals", []):
            cleaned, removed = strip_forbidden(sig.get("text", ""))
            if removed:
                warnings.append(f"rule 6: stripped from a signal in {p.get('name')}")
            if cleaned:
                sig["text"] = cleaned
                kept_signals.append(sig)
        p["eligibility_signals"] = kept_signals
    kept_actions = []
    for a in out.get("next_actions", []):
        cleaned, removed = strip_forbidden(a.get("text", ""))
        if removed:
            warnings.append("rule 6: stripped from a next action")
        if cleaned:
            a["text"] = cleaned
            kept_actions.append(a)
    out["next_actions"] = kept_actions
    if any(w.startswith("rule 6") for w in warnings):
        not_answered.append(
            "Amounts and processing times: this tool does not report them. "
            "Use the official estimator or your myGov account."
        )
    out["not_answered"] = not_answered

    if errors:
        return Result(False, out, errors, warnings, "low_confidence")
    return Result(True, out, errors, warnings, None)
