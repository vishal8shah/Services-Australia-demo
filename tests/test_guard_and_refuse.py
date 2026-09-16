import json
import unittest
from pathlib import Path

from saal.answer import guard, refuse

GOLDEN = json.loads((Path(__file__).resolve().parent.parent / "evals" / "golden.json").read_text())


class TestGuard(unittest.TestCase):
    def test_detects_identifiers(self):
        self.assertEqual(guard.detect("My CRN is 123 456 789A"), ["crn"])
        self.assertIn("email", guard.detect("write to me at a.b@c.com"))
        self.assertIn("date_of_birth", guard.detect("I was born 14/07/1958"))

    def test_crn_is_not_also_reported_as_a_tfn(self):
        self.assertNotIn("tfn", guard.detect("My CRN is 123456789A"))

    def test_ordinary_questions_are_clean(self):
        for item in GOLDEN["items"]:
            if item["id"] == "R4":
                continue
            self.assertEqual(guard.detect(item["question"]), [], item["id"])

    def test_redaction_removes_the_identifier(self):
        self.assertNotIn("123 456 789A", guard.redact("My CRN is 123 456 789A"))


class TestRefuse(unittest.TestCase):
    def test_every_probe_is_refused_with_the_expected_class(self):
        for item in GOLDEN["items"]:
            if item["type"] != "refusal" or item["id"] == "R4":
                continue  # R4 is caught earlier by the identifier guard
            got = refuse.classify(item["question"])
            self.assertIsNotNone(got, item["id"])
            self.assertIn(got.cls, item["expect_class"], item["id"])

    def test_no_answerable_question_is_pre_refused(self):
        for item in GOLDEN["items"]:
            if item["type"] == "refusal":
                continue
            self.assertIsNone(refuse.classify(item["question"]),
                              f"{item['id']} over refused: {item['question']}")

    def test_a_sole_trader_is_an_individual_not_a_business_enquiry(self):
        self.assertIsNone(refuse.classify("My business closed, I was a sole trader."))
        self.assertEqual(refuse.classify("Is there a grant for my cafe?").cls, "out_of_corpus")

    def test_every_class_has_a_message(self):
        for cls in refuse.CLASSES:
            self.assertTrue(refuse.build(cls).message)


if __name__ == "__main__":
    unittest.main()
