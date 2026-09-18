import unittest

from saal.ingest.scope import families_of, in_scope

BASE = "https://www.servicesaustralia.gov.au/"


class TestScope(unittest.TestCase):
    """Slug shapes taken from the live sitemap on Day 0, flat at the root."""

    def test_a_payment_landing_page_is_in(self):
        self.assertEqual(families_of(BASE + "carer-payment"), ["caring"])

    def test_a_standard_page_type_naming_a_payment_is_in(self):
        for slug in ("who-can-get-jobseeker-payment", "how-much-carer-allowance-you-can-get",
                     "income-and-assets-test-for-carer-payment",
                     "when-youll-get-your-first-youth-allowance-for-job-seekers-payment"):
            with self.subTest(slug=slug):
                self.assertTrue(in_scope(BASE + slug))

    def test_a_payment_name_without_a_page_type_is_out(self):
        """The long tail: statistics, strategies, electorate data."""
        for slug in ("child-support-electorate-data-june-2008", "family-tax-benefit-balancing-outcomes",
                     "dont-let-your-childs-abstudy-payment-stop"):
            with self.subTest(slug=slug):
                self.assertFalse(in_scope(BASE + slug))

    def test_audience_and_format_exclusions_win_over_a_payment_name(self):
        for slug in ("claiming-carer-payment-and-carer-allowance-audio-translation",
                     "rent-assistance-resources-for-housing-providers",
                     "who-can-get-abstudy-lawful-custody-allowance-education-providers-and-corrective-services"):
            with self.subTest(slug=slug):
                self.assertFalse(in_scope(BASE + slug))

    def test_forms_and_disaster_news_are_out(self):
        for slug in ("sa391", "claims-close-soon-for-queensland-rainfall-and-flooding-february-to-march-2026",
                     "disaster-recovery-payment-and-disaster-recovery-allowance-privacy-notice"):
            with self.subTest(slug=slug):
                self.assertFalse(in_scope(BASE + slug))

    def test_declared_disaster_event_pages_are_in(self):
        for slug in ("vic-bushfires-jan-2026", "wa-tc-narelle-mar-2026-agdrp",
                     "who-can-get-vic-bushfires-jan-2026-dra",
                     "how-much-qld-rainfall-and-flooding-feb-to-mar-26-nz-drp-you-can-get"):
            with self.subTest(slug=slug):
                self.assertEqual(families_of(BASE + slug), ["crisis"])

    def test_cross_cutting_topics_are_in_by_exact_slug(self):
        self.assertEqual(families_of(BASE + "someone-to-act-for-you-with-centrelink-or-aged-care"),
                         ["general"])
        self.assertEqual(families_of(BASE + "natural-disaster-support"), ["crisis"])

    def test_a_page_can_serve_two_families(self):
        self.assertEqual(families_of(BASE + "choosing-between-carer-payment-and-age-pension"),
                         ["caring", "ageing"])

    def test_trailing_slash_and_query_do_not_change_the_answer(self):
        self.assertEqual(families_of(BASE + "age-pension/?utm=x"), ["ageing"])
