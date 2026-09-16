"""Prompt construction.

Four blocks, in a fixed order: boundaries, chunks, schema, question. No examples
of good answers are included. Few shot examples here teach the model to imitate
the shape of a confident answer, which is precisely what the validator exists to
defend against.
"""
from __future__ import annotations

from ..retrieve.search import Hit
from .contract import SCHEMA_FOR_PROMPT

SYSTEM = """You answer questions about Australian government payments using ONLY the numbered chunks supplied in the user message. You are not Services Australia and you have no access to anyone's record.

Hard boundaries, absolute:
- Never state a dollar amount, payment rate, wait time or processing time. If the question asks for one, put it in not_answered.
- Never tell someone they qualify or do not qualify. Report what the eligibility rules say and let them check.
- Never mention a payment that does not appear in the supplied chunks.
- Every claim you make must cite the chunk id it came from. A claim you cannot cite must be omitted, not softened. Hedged wording such as "you may be eligible" reads as an answer to someone who is frightened, so it is not an acceptable substitute for omitting the claim.
- If the chunks do not support an answer, return an empty payments list and say why in not_answered.

Write in plain language at about a year 7 reading level. Keep payment names exactly as they appear in the chunks: never translate, abbreviate or pluralise them."""

LANGUAGE_BLOCK = """Answer in {language}. Keep every payment name, source title and url in English exactly as supplied, and put your translated gloss beside the payment name in the one_liner. A translated payment name is not searchable on the official site and not recognisable to staff on the phone."""


def format_chunks(hits: list[Hit]) -> str:
    blocks = []
    for h in hits:
        c = h.chunk
        blocks.append(
            f"[{c.chunk_id}] {c.title}\n"
            f"section: {c.heading_path}\n"
            f"url: {c.url}\n"
            f"page last updated: {c.page_last_updated or 'unknown'}\n"
            f"---\n{c.text}"
        )
    return "\n\n".join(blocks)


def build_user_message(question: str, facets: list[str], hits: list[Hit],
                       language: str = "en") -> str:
    parts = [
        "CHUNKS",
        format_chunks(hits),
        "",
        "OUTPUT SCHEMA, return this JSON object and nothing else:",
        SCHEMA_FOR_PROMPT,
        "",
    ]
    if language and language != "en":
        parts.extend([LANGUAGE_BLOCK.format(language=language), ""])
    parts.append(f"QUESTION\n{question}")
    if facets:
        parts.append("The question contains these separate situations, and each one "
                     "that the chunks cover should be answered:\n- " + "\n- ".join(facets))
    return "\n".join(parts)
