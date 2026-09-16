import unittest

from saal.answer.facets import decompose
from saal.retrieve.search import content_terms, coverage, fts_query, rrf, search
from saal.store import Chunk
from saal.testing import fixture_conn


class TestPieces(unittest.TestCase):
    def test_fts_query_survives_user_punctuation(self):
        self.assertIn('"rent"', fts_query('I rent "privately" - and I am on a payment!'))
        self.assertEqual(fts_query("!!!"), "")

    def test_coverage_counts_content_words_only(self):
        chunk = Chunk("c_1", "u", "Rent Assistance", "Rent Assistance > Who can get it", 0,
                      "You pay rent to a private landlord.", "2026-01-01")
        self.assertEqual(coverage(content_terms("I pay rent to a private landlord"), chunk), 1.0)
        self.assertEqual(coverage(content_terms("flood disaster recovery"), chunk), 0.0)

    def test_rrf_rewards_agreement_between_rankings(self):
        fused = rrf([[("a", 1.0), ("b", 0.9)], [("b", 1.0), ("c", 0.1)]], k=60)
        self.assertGreater(fused["b"], fused["a"])


class TestSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = fixture_conn()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_a_payment_name_retrieves_its_own_page(self):
        hits = search(self.conn, "Carer Allowance")
        self.assertEqual(hits[0].chunk.title, "Carer Allowance")
        self.assertGreater(hits[0].confidence, 0.5)

    def test_facets_surface_a_family_the_whole_sentence_misses(self):
        """The reason decomposition exists: one sentence, two situations."""
        question = "Mum is 82 and moving in with us, I have dropped to three days a week."
        plain = {h.chunk.title for h in search(self.conn, question)}
        with_facets = {h.chunk.title for h in search(self.conn, question,
                                                    facets=decompose(question))}
        self.assertNotIn("Carer Payment", plain)
        self.assertIn("Carer Payment", with_facets)
        self.assertIn("Carer Allowance", with_facets)

    def test_facets_never_vote_out_the_sentences_own_best_hit(self):
        """A fragment gets less of a vote than the whole question. Regression:
        unweighted fusion let three facets bury JobSeeker Payment entirely."""
        question = "I lost my job last month, I have two kids in childcare and I rent."
        plain = {h.chunk.title for h in search(self.conn, question)}
        with_facets = {h.chunk.title for h in search(self.conn, question,
                                                    facets=decompose(question))}
        self.assertIn("JobSeeker Payment", plain)
        self.assertIn("JobSeeker Payment", with_facets)

    def test_an_unrelated_question_scores_below_the_floor(self):
        hits = search(self.conn, "how do I register a trademark for my brand")
        confidence = max((h.confidence for h in hits), default=0.0)
        self.assertLess(confidence, 0.3)

    def test_every_hit_carries_its_source_date(self):
        for h in search(self.conn, "Age Pension"):
            self.assertTrue(h.chunk.url)
            self.assertTrue(h.chunk.page_last_updated)


if __name__ == "__main__":
    unittest.main()
