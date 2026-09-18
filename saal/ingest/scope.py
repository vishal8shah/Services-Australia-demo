"""Which sitemap urls belong in the corpus, and which payment family each serves.

The site used to file this content under /individuals/<branch>/. It no longer
does: every page now sits at the root, and a 4,300 url sitemap mixes payment
pages with forms, audio translations, provider guidance and dated disaster
events. So scope is decided by the slug, and it takes two things to get in: the
page names a payment the golden suite asks about, and it is one of the standard
page types every payment has (who can get it, how much, how to claim, ...).
The landing page for each payment is in by exact slug. A short list of cross
cutting topics (nominees, proof of identity, compensation) is in by exact slug
too, because they have no payment name to match on. See D14.
"""
from __future__ import annotations

import re

# Slug fragments per family, drawn from the payment names in evals/golden.json.
FAMILIES: dict[str, tuple[str, ...]] = {
    "work": ("jobseeker-payment", "special-benefit", "work-bonus", "rent-assistance"),
    "study": ("youth-allowance", "austudy", "abstudy", "assistance-for-isolated-children"),
    "family": ("family-tax-benefit", "parenting-payment", "parental-leave-pay",
               "newborn-upfront-payment", "child-care-subsidy", "child-support-assessment"),
    "caring": ("carer-payment", "carer-allowance", "carer-supplement",
               "child-disability-assistance-payment"),
    "ageing": ("age-pension", "commonwealth-seniors-health-card", "pensioner-concession-card"),
    "disability": ("disability-support-pension", "mobility-allowance"),
    "health": ("low-income-health-care-card", "health-care-card"),
    "bereavement": ("bereavement-payment",),
    "crisis": ("crisis-payment",),
}

# Whole slugs, for topics a person asks about that are not a payment name.
TOPICS: dict[str, tuple[str, ...]] = {
    "crisis": ("natural-disaster-support", "what-financial-help-available-for-disasters",
               "understanding-government-disaster-support", "additional-help-for-natural-disasters",
               "how-to-manage-my-current-payment-or-card-during-disaster", "social-work-services",
               "social-work-services-if-youre-experiencing-violence",
               "social-work-services-for-your-mental-health"),
    "ageing": ("aged-care-calculation-your-cost-care",
               "who-should-apply-for-aged-care-calculation-your-cost-care",
               "how-to-apply-for-aged-care-calculation-your-cost-care",
               "aged-care-calculation-your-cost-care-if-you-get-income-support-payment",
               "you-own-your-own-home-for-aged-care-calculation-your-cost-care"),
    "general": ("someone-to-act-for-you-with-centrelink-or-aged-care",
                "acting-arrangements-for-centrelink-or-aged-care",
                "add-or-cancel-someone-to-act-for-you-with-centrelink-or-aged-care",
                "how-to-prove-your-identity-with-centrelink", "proving-your-identity-online-for-centrelink",
                "proving-your-identity-person-for-centrelink-payment",
                "proving-your-identity-over-phone-with-centrelink",
                "how-compensation-affects-payments", "when-you-get-lump-sum-compensation",
                "when-you-get-periodic-compensation", "how-we-treat-lump-sum-compensation",
                "how-we-treat-periodic-compensation", "relationship-changes",
                "updating-your-relationship-status", "confirm-your-relationship-status-when-making-claim",
                "living-arrangements"),
}

PAGE_TYPES = re.compile(
    r"^(who-can-get|how-much|how-to-claim|how-to-apply|how-to-manage|how-to-report|when-youll-get"
    r"|income-and-assets-tests?-for|income-test-for|assets-test-for|change-circumstances"
    r"|residence-rules-for|what-your-commitments|while-you-wait|choosing-between|how-to-keep"
    r"|how-to-prepare|when-to-claim)")

# Disaster Recovery Payment and Allowance have no evergreen page, only one set of
# pages per declared event: a landing page named for the event and its date, and
# payment pages ending in the payment's code. They expire as events close, so a
# recrawl is what keeps them honest. Added for golden item X2, see D17.
DISASTER_CODE = re.compile(r"(^|-)(agdrp|dra|drp)(-you-can-get)?$")
DISASTER_EVENT = re.compile(r"(flood|bushfire|cyclone|^tc-|-tc-|storm|rainfall|fire).*"
                            r"-(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-(20)?\d{2}$")

# Audience or format, not content for a person: checked before anything else.
EXCLUDE = re.compile(r"translation|providers|corrective-services|organisations|professionals"
                     r"|for-staff|employer|business")


def slug_of(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1].lower()


def families_of(url: str) -> list[str]:
    """Every family a url serves, in FAMILIES order. Empty means out of scope."""
    slug = slug_of(url)
    if not slug or EXCLUDE.search(slug):
        return []
    typed = bool(PAGE_TYPES.match(slug))
    out = [f for f, keys in FAMILIES.items()
           if any(slug == k or (typed and k in slug) for k in keys)]
    out += [f for f, slugs in TOPICS.items() if slug in slugs and f not in out]
    if (DISASTER_CODE.search(slug) or DISASTER_EVENT.search(slug)) and "crisis" not in out:
        out.append("crisis")
    return out


def in_scope(url: str) -> bool:
    return bool(families_of(url))
