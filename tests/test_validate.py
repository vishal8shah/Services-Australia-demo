import unittest

from saal.answer.validate import strip_forbidden, validate
from saal.retrieve.search import Hit
from saal.store import Chunk


def hit(chunk_id, text, title="Carer Payment", url="https://x/cp"):
    return Hit(chunk=Chunk(chunk_id=chunk_id, url=url, title=title,
                           heading_path=f"{title} > Who can get it", ordinal=0, text=text,
                           page_last_updated="2026-07-14"),
               score=0.5, lexical=0.5, vector=0.5, coverage=0.8, margin=0.4, facets=[])


HITS = [hit("c_1", "You give constant care to someone in their home."),
        hit("c_2", "Claim online using your Centrelink account.")]


def response(**over):
    base = {
        "payments": [{
            "name": "Carer Payment",
            "one_liner": "For people who give constant care.",
            "distinguisher": None,
            "eligibility_signals": [{"text": "You give constant care.", "source_ids": ["c_1"]}],
            "source_ids": ["c_1"],
        }],
        "next_actions": [{"order": 1, "text": "Claim online.", "url": "https://x/cp",
                          "source_ids": ["c_2"]}],
        "not_answered": [],
    }
    base.update(over)
    return base


class TestValidator(unittest.TestCase):
    def test_a_clean_response_passes(self):
        result = validate(response(), HITS)
        self.assertTrue(result.ok, result.errors)

    def test_rule_1_rejects_an_invented_chunk_id(self):
        r = response()
        r["payments"][0]["source_ids"] = ["c_999"]
        r["payments"][0]["eligibility_signals"][0]["source_ids"] = ["c_999"]
        result = validate(r, HITS)
        self.assertFalse(result.ok)
        self.assertTrue(any("rule 1" in e for e in result.errors), result.errors)

    def test_rule_2_rejects_an_unsourced_claim(self):
        r = response()
        r["payments"][0]["eligibility_signals"][0]["source_ids"] = [""]
        result = validate(r, HITS)
        self.assertTrue(any("rule 2" in e for e in result.errors), result.errors)

    def test_rule_3_rejects_a_payment_its_sources_never_mention(self):
        r = response()
        r["payments"][0]["name"] = "Carer Supplement"
        result = validate(r, HITS)
        self.assertFalse(result.ok)
        self.assertTrue(any("rule 3" in e for e in result.errors), result.errors)

    def test_rule_4_strips_a_url_that_is_not_from_a_cited_source(self):
        r = response()
        r["next_actions"][0]["url"] = "https://elsewhere.example/claim"
        result = validate(r, HITS)
        self.assertTrue(result.ok, result.errors)
        self.assertIsNone(result.response["next_actions"][0]["url"])
        self.assertTrue(any("rule 4" in w for w in result.warnings))

    def test_rule_5_rejects_a_malformed_response(self):
        result = validate({"payments": "not a list"}, HITS)
        self.assertFalse(result.ok)
        self.assertEqual(result.refusal_class, "low_confidence")

    def test_rule_6_removes_dollar_figures_and_processing_times(self):
        r = response()
        r["payments"][0]["one_liner"] = ("For people who give care. You get $144.80 a fortnight.")
        r["next_actions"][0]["text"] = ("Claim online. Claims take 21 days to process.")
        result = validate(r, HITS)
        self.assertTrue(result.ok, result.errors)
        self.assertNotIn("144.80", result.response["payments"][0]["one_liner"])
        self.assertNotIn("21 days", result.response["next_actions"][0]["text"])
        self.assertTrue(result.response["not_answered"])

    def test_rule_6_keeps_a_notification_obligation(self):
        kept, removed = strip_forbidden("Tell us within 14 days if your income changes.")
        self.assertEqual(removed, [])
        self.assertIn("14 days", kept)

    def test_a_failed_validation_never_returns_a_partial_answer(self):
        r = response()
        r["payments"][0]["name"] = "Invented Payment"
        result = validate(r, HITS)
        self.assertFalse(result.ok)
        self.assertEqual(result.refusal_class, "low_confidence")


if __name__ == "__main__":
    unittest.main()
