"""The one output shape, and a dependency free shape check.

There is no free prose path anywhere in this package. Either a response conforms
to this contract and survives the validator, or the user gets a refusal. A half
answer with a broken citation is worse than no answer, because it looks exactly
like a good one.
"""
from __future__ import annotations

from typing import Any

SCHEMA_FOR_PROMPT = """{
  "payments": [
    {
      "name": "<exact payment name, copied verbatim from a chunk>",
      "one_liner": "<one sentence: who this is for>",
      "distinguisher": "<how it differs from a similarly named payment, or null>",
      "eligibility_signals": [
        {"text": "<one signal, plainly worded>", "source_ids": ["<chunk id>"]}
      ],
      "source_ids": ["<chunk id>", "..."]
    }
  ],
  "next_actions": [
    {"order": 1, "text": "<what the person does next>", "url": "<url of a cited chunk>",
     "source_ids": ["<chunk id>"]}
  ],
  "not_answered": ["<anything the question asked that these chunks cannot answer>"]
}"""

REQUIRED_PAYMENT_KEYS = {"name", "one_liner", "eligibility_signals", "source_ids"}
REQUIRED_ACTION_KEYS = {"order", "text", "source_ids"}


def empty(language: str = "en") -> dict[str, Any]:
    return {
        "language": language,
        "query": None,
        "query_facets": [],
        "refusal": None,
        "payments": [],
        "next_actions": [],
        "sources": [],
        "not_answered": [],
        "confidence": 0.0,
        "meta": {},
    }


def shape_errors(obj: Any) -> list[str]:
    """Structural check only. Truthfulness is the validator's job, not this one."""
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["response is not an object"]

    payments = obj.get("payments")
    if not isinstance(payments, list):
        errs.append("payments is not a list")
        payments = []
    for i, p in enumerate(payments):
        if not isinstance(p, dict):
            errs.append(f"payments[{i}] is not an object")
            continue
        missing = REQUIRED_PAYMENT_KEYS - set(p)
        if missing:
            errs.append(f"payments[{i}] missing {sorted(missing)}")
        if not isinstance(p.get("source_ids"), list) or not p.get("source_ids"):
            errs.append(f"payments[{i}].source_ids must be a non empty list")
        for j, sig in enumerate(p.get("eligibility_signals") or []):
            if not isinstance(sig, dict) or "text" not in sig:
                errs.append(f"payments[{i}].eligibility_signals[{j}] malformed")
            elif not sig.get("source_ids"):
                errs.append(f"payments[{i}].eligibility_signals[{j}] has no source_ids")

    actions = obj.get("next_actions")
    if not isinstance(actions, list):
        errs.append("next_actions is not a list")
        actions = []
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            errs.append(f"next_actions[{i}] is not an object")
            continue
        missing = REQUIRED_ACTION_KEYS - set(a)
        if missing:
            errs.append(f"next_actions[{i}] missing {sorted(missing)}")
        if not a.get("source_ids"):
            errs.append(f"next_actions[{i}] has no source_ids")

    if obj.get("not_answered") is not None and not isinstance(obj.get("not_answered"), list):
        errs.append("not_answered is not a list")
    return errs


def cited_ids(obj: dict) -> set[str]:
    out: set[str] = set()
    for p in obj.get("payments") or []:
        out.update(p.get("source_ids") or [])
        for sig in p.get("eligibility_signals") or []:
            out.update(sig.get("source_ids") or [])
    for a in obj.get("next_actions") or []:
        out.update(a.get("source_ids") or [])
    return out
