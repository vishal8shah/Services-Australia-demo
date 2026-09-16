"""The answer key and the human readable suite must not drift apart."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "evals" / "golden.json").read_text())
MARKDOWN = (ROOT / "evals" / "golden_questions.md").read_text()
ROW_ID = re.compile(r"^\|\s*([A-Z]{1,2}\d+)\s*\|", re.M)


class TestGoldenSuite(unittest.TestCase):
    def test_ids_match_the_markdown_suite(self):
        in_json = {i["id"] for i in GOLDEN["items"]}
        in_md = set(ROW_ID.findall(MARKDOWN))
        self.assertEqual(in_json - in_md, set(), "in golden.json but not documented")
        self.assertEqual(in_md - in_json, set(), "documented but not runnable")

    def test_ids_are_unique(self):
        ids = [i["id"] for i in GOLDEN["items"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_answer_item_expects_at_least_one_family(self):
        for item in GOLDEN["items"]:
            if item["type"] == "answer":
                self.assertTrue(item["expect"], item["id"])

    def test_every_refusal_probe_names_its_classes(self):
        from saal.answer.refuse import CLASSES
        for item in GOLDEN["items"]:
            if item["type"] == "refusal":
                self.assertTrue(item["expect_class"], item["id"])
                for cls in item["expect_class"]:
                    self.assertIn(cls, CLASSES, item["id"])

    def test_the_gates_are_the_ones_the_plan_commits_to(self):
        gates = GOLDEN["gates"]
        self.assertEqual(gates["citation_faithfulness"], 1.0)
        self.assertEqual(gates["fabricated_payment_rate"], 0.0)
        self.assertEqual(gates["refusal_precision"], 1.0)


if __name__ == "__main__":
    unittest.main()
