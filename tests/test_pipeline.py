import unittest

from saal import config, pipeline
from saal.testing import fixture_conn


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = fixture_conn()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def ask(self, question, **kw):
        return pipeline.answer(question, conn=self.conn, **kw)

    def test_an_answer_carries_a_source_and_a_date_for_every_payment(self):
        out = self.ask("What is the difference between Carer Payment and Carer Allowance?")
        self.assertIsNone(out["refusal"])
        self.assertTrue(out["payments"])
        source_ids = {s["id"] for s in out["sources"]}
        for payment in out["payments"]:
            self.assertTrue(set(payment["source_ids"]) & source_ids)
        for source in out["sources"]:
            self.assertTrue(source["url"])
            self.assertIn("page_last_updated", source)

    def test_an_identifier_stops_the_request_before_retrieval(self):
        out = self.ask("My CRN is 123 456 789A, what can I claim?")
        self.assertEqual(out["refusal"]["class"], "pii_detected")
        self.assertEqual(out["sources"], [])
        self.assertEqual(out["meta"].get("hits"), None)

    def test_an_amount_question_is_refused_and_offered_the_estimator(self):
        out = self.ask("How much will I get for Carer Payment?")
        self.assertEqual(out["refusal"]["class"], "amount")
        self.assertIn("payment-and-service-finder", out["refusal"]["offer"]["url"])

    def test_an_unsupported_question_refuses_rather_than_guessing(self):
        out = self.ask("How do I register a trademark for my brand?")
        self.assertEqual(out["refusal"]["class"], "low_confidence")
        self.assertEqual(out["payments"], [])

    def test_the_refusal_message_names_the_phone_number(self):
        out = self.ask("When will my payment arrive?")
        self.assertEqual(out["refusal"]["phone"], config.PHONE_GENERAL)

    def test_no_answer_path_returns_prose_outside_the_contract(self):
        out = self.ask("What documents do I need to prove my identity?")
        self.assertEqual(
            set(out) - {"language", "query", "query_facets", "refusal", "payments",
                        "next_actions", "sources", "not_answered", "confidence", "meta",
                        "stale_sources"},
            set())

    def test_language_is_detected_from_the_question(self):
        self.assertEqual(self.ask("我照顾我的母亲")["language"], "zh")
        self.assertEqual(self.ask("What can I claim?")["language"], "en")

    def test_a_validator_failure_becomes_a_refusal_not_a_partial_answer(self):
        class BrokenProvider:
            name = "broken"

            def answer(self, question, facets, hits, language="en"):
                return {"payments": [{"name": "Invented Payment", "one_liner": "x",
                                      "eligibility_signals": [{"text": "y",
                                                               "source_ids": [hits[0].chunk.chunk_id]}],
                                      "source_ids": [hits[0].chunk.chunk_id]}],
                        "next_actions": [], "not_answered": []}

        out = self.ask("What documents do I need to prove my identity?",
                       provider=BrokenProvider())
        self.assertEqual(out["refusal"]["class"], "low_confidence")
        self.assertEqual(out["payments"], [])
        self.assertTrue(any("rule 3" in e for e in out["meta"]["validator_errors"]))


if __name__ == "__main__":
    unittest.main()
