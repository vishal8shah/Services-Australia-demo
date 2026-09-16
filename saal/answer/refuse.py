"""Refusal classes, and the deterministic pass that catches the dangerous ones.

The high risk classes are caught by pattern before retrieval, so the decision to
refuse a question about someone's claim never depends on a model behaving well.
The patterns are deliberately narrow: an over refusing system is a system people
stop using, which sends them back to the 30 million calls a year this is trying
to reduce. The over refusal control set in the golden suite is what keeps this
file honest.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .. import config

CLASSES = {
    "personal_record": "Anything about this person's claim, balance or history",
    "claim_status": "Timing or progress of a claim",
    "amount": "A dollar figure",
    "wait_time": "Operational data we do not hold",
    "determination": "A yes or no on whether this person qualifies",
    "action_on_record": "Doing something to a record on the person's behalf",
    "out_of_corpus": "Business, health provider or other non individuals content",
    "out_of_scope": "Not Services Australia at all",
    "low_confidence": "Retrieval below the score floor, or a validator failure",
    "pii_detected": "The input contained an identifier",
}

MESSAGES = {
    "personal_record": "This tool has no access to anyone's record, and holds no personal data. Anything about your own claim, balance or history has to come from myGov or from Services Australia directly.",
    "claim_status": "This tool cannot see your claim or when it will be paid.",
    "amount": "This tool will not quote payment amounts. Rates change and depend on your circumstances, so a number from here could be wrong in a way that matters.",
    "wait_time": "This tool has no access to wait times or processing times.",
    "determination": "This tool cannot decide whether you qualify. It can show you what the eligibility rules say, and Services Australia makes the decision.",
    "action_on_record": "This tool cannot lodge, change or cancel anything. It can show you where to do it yourself.",
    "out_of_corpus": "This tool only covers the individuals content on the Services Australia site.",
    "out_of_scope": "That is outside what this tool covers.",
    "low_confidence": "The pages behind this tool do not clearly answer that, and guessing would be worse than saying so.",
    "pii_detected": "That looks like it contains an identifier such as a customer reference number. Nothing was stored and nothing was sent anywhere. Please ask again without it.",
}

OFFERS = {
    "personal_record": ("Sign in to myGov", "https://my.gov.au"),
    "claim_status": ("Check your claim in myGov", "https://my.gov.au"),
    "amount": ("Use the official payment and service finder",
               f"{config.BASE}/payment-and-service-finder"),
    "determination": ("Read the eligibility rules on the payment page", None),
    "action_on_record": ("Sign in to myGov", "https://my.gov.au"),
    "out_of_corpus": ("Services Australia for business", f"{config.BASE}/business"),
}

# Each pattern is narrow on purpose. Widening one of these is a decision to be
# made against the over refusal control set, not in the moment.
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("claim_status", re.compile(
        r"\b(when will (i|my)\b.*\b(get|arrive|be paid|come)|"
        r"(status|progress) of my (claim|application|payment)|"
        r"has my (claim|payment) been|is my (claim|payment) (approved|processed|done)|"
        r"how long until (i|my))", re.I)),
    ("amount", re.compile(
        r"\b(how much (will|do|would|can) (i|we|my)\b|"
        r"what (is|are) the (rate|rates|amount)s?\b|"
        r"how much is (the )?(\w+ ){0,3}(payment|allowance|pension|benefit)\b)", re.I)),
    ("wait_time", re.compile(
        r"\b((phone|call|queue|processing) wait|wait time|how long is the wait|"
        r"how long will i be on hold|current wait)", re.I)),
    ("personal_record", re.compile(
        r"\b(check my (balance|record|account|claim|payments?)|"
        r"why (was|were) my (claim|payment|application)|"
        r"my crn\b|look up my|what did i get paid|my payment history)", re.I)),
    ("action_on_record", re.compile(
        r"\b(can you|could you|please) (lodge|submit|claim|apply|cancel|update|change|fix)\b"
        r"|\b(lodge|submit|apply for) (it|this|the claim|my claim) for me\b", re.I)),
    # Mentioning a business is not out of scope: a sole trader whose business
    # closed is exactly an individuals question. Asking for business support is.
    ("out_of_corpus", re.compile(
        r"(?:\b(?:grants?|subsid\w*|support|assistance|help)\b[^.?!]{0,30}"
        r"\bfor (?:my|our|the) (?:business|company|cafe|shop|restaurant|farm)\b"
        r"|\b(?:my|our) (?:business|company|cafe|shop|restaurant)\b[^.?!]{0,40}"
        r"\b(?:grants?|subsid\w*|eligible for|entitled to)\b"
        r"|\bbusiness grants?\b"
        r"|\bmy abn\b"
        r"|\bas a (?:provider|practice|pharmacy)\b)", re.I)),
    ("out_of_scope", re.compile(
        r"\b(tax structure|negative gearing|investment propert|"
        r"which (shares|stocks)|legal advice|sue |visa application outcome)", re.I)),
]


@dataclass
class Refusal:
    cls: str
    message: str
    offer_text: str | None = None
    offer_url: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        d = {"class": self.cls, "message": self.message, "phone": config.PHONE_GENERAL}
        if self.offer_text:
            d["offer"] = {"text": self.offer_text, "url": self.offer_url}
        if self.detail:
            d["detail"] = self.detail
        return d


def build(cls: str, detail: str | None = None) -> Refusal:
    text, url = OFFERS.get(cls, (None, None))
    return Refusal(cls=cls, message=MESSAGES.get(cls, MESSAGES["out_of_scope"]),
                   offer_text=text, offer_url=url, detail=detail)


def classify(question: str) -> Refusal | None:
    """Deterministic pre retrieval refusal. Returns None when the question may proceed."""
    for cls, pattern in RULES:
        if pattern.search(question):
            return build(cls)
    return None
