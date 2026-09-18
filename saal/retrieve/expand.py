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

from typing import Protocol

from .. import config
from ..llm import LLMError, api_key, chat, parse_json

SYSTEM = """You rewrite a person's situation into the vocabulary used on Australian government payment pages, so a search engine can find the right pages.

The pages cover these payments and cards, by these exact names: JobSeeker Payment, Youth Allowance, Austudy, ABSTUDY, Assistance for Isolated Children, Special Benefit, Work Bonus, Rent Assistance, Family Tax Benefit, Parenting Payment, Parental Leave Pay, Newborn Upfront Payment, Child Care Subsidy, Child Support, Carer Payment, Carer Allowance, Carer Supplement, Child Disability Assistance Payment, Age Pension, Commonwealth Seniors Health Card, Pensioner Concession Card, Disability Support Pension, Mobility Allowance, Low Income Health Care Card, Health Care Card, Pension Bonus Bereavement Payment, Crisis Payment, Disaster Recovery Payment, Disaster Recovery Allowance. A situation often involves more than one: think about each part of it separately, and include the name of every payment above that a person in that situation would commonly look at.

Return JSON: an array of at most 6 short search phrases, and nothing else. Each phrase is 2 to 5 words. Prefer the words the pages themselves would use: "constant care", "care receiver", "income test", "looking for work", "activity test", "principal carer", "residence rules".

The person may write in any language. The pages are in English, so every phrase you return must be in English, whatever language the situation is written in.

Do not answer the question. Do not explain. Do not include the person's own wording back. If the situation is already stated in official English vocabulary, return an empty array."""

class Expander(Protocol):
    name: str

    def expand(self, question: str) -> list[str]: ...


class NullExpander:
    """No model configured. Retrieval runs on the person's own words alone."""

    name = "none"

    def expand(self, question: str) -> list[str]:
        return []


class ApiExpander:
    """One small, fast call per question, on whichever key you already have."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        self.provider = provider
        self.name = provider
        self.model = model or config.fast_model_for(provider)
        api_key(provider)

    def expand(self, question: str) -> list[str]:
        try:
            text = chat(SYSTEM, question, provider=self.provider, model=self.model,
                        max_tokens=200, json_mode=False, timeout=30)
            phrases = parse_json(text)
            if isinstance(phrases, dict):  # JSON mode can wrap a list in an object
                phrases = next((v for v in phrases.values() if isinstance(v, list)), [])
        except (LLMError, StopIteration):
            # Expansion is an optimisation. Losing it degrades retrieval, and
            # failing the whole question because of it would be worse.
            return []
        return [p.strip() for p in phrases if isinstance(p, str) and p.strip()][:6]


def get_expander(name: str | None = None) -> Expander:
    name = name or config.EXPANDER
    if name in ("none", "", None):
        return NullExpander()
    if name == "claude":  # kept as an alias so existing scripts keep working
        return ApiExpander("anthropic")
    if name in ("anthropic", "openai"):
        return ApiExpander(name)
    raise ValueError(f"unknown expander: {name}")
