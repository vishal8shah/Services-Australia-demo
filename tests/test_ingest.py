import unittest

from saal.ingest.chunk import chunk_page, split_section
from saal.ingest.extract import Section, extract
from saal.store import chunk_id_for

PAGE = """<html><head><title>Carer Payment | Services Australia</title>
<meta name="dcterms.modified" content="2026-07-14T10:00:00Z"></head>
<body>
<nav class="main-nav"><a href="/">Home</a><a href="/individuals">Individuals</a></nav>
<h1>Carer Payment</h1><p>A payment if you give constant care.</p>
<h2>Who can get it</h2><ul><li>You give constant care.</li><li>You meet an income test.</li></ul>
<h3>Care receiver rules</h3><p>The person you care for must meet a care receiver test.</p>
<h2>How to claim</h2><p>Claim online using your Centrelink account.</p>
<footer><p>Page last updated: 14 July 2026</p><p>Print this page</p></footer>
<script>var tracking = 1;</script></body></html>"""


class TestExtract(unittest.TestCase):
    def setUp(self):
        self.page = extract(PAGE, "https://x/carer-payment")

    def test_title_and_date(self):
        self.assertEqual(self.page.title, "Carer Payment")
        self.assertEqual(self.page.page_last_updated, "2026-07-14")

    def test_navigation_and_scripts_are_dropped(self):
        blob = "\n".join(s.text for s in self.page.sections)
        self.assertNotIn("tracking", blob)
        self.assertNotIn("Individuals", blob)
        self.assertNotIn("Print this page", blob)

    def test_heading_path_is_kept(self):
        paths = [s.heading_path for s in self.page.sections]
        self.assertIn("Carer Payment > Who can get it", paths)
        self.assertIn("Carer Payment > Who can get it > Care receiver rules", paths)

    def test_date_falls_back_to_page_text(self):
        html = PAGE.replace('<meta name="dcterms.modified" content="2026-07-14T10:00:00Z">', "")
        self.assertEqual(extract(html, "https://x/a").page_last_updated, "2026-07-14")

    def test_missing_date_is_none(self):
        html = "<html><body><h1>A</h1><p>Some text here.</p></body></html>"
        self.assertIsNone(extract(html, "https://x/a").page_last_updated)


class TestChunk(unittest.TestCase):
    def test_long_paragraph_splits_on_sentences(self):
        section = Section("H", "This is a sentence. " * 300)
        parts = split_section(section, 1800)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 1800 for p in parts))

    def test_short_child_section_merges_into_its_parent(self):
        page = extract(PAGE, "https://x/carer-payment")
        chunks = chunk_page(page, max_chars=1800, min_chars=200)
        paths = [c.heading_path for c in chunks]
        self.assertNotIn("Carer Payment > Who can get it > Care receiver rules", paths)
        self.assertIn("care receiver test", " ".join(c.text for c in chunks))

    def test_chunk_ids_are_stable_across_runs(self):
        a = chunk_page(extract(PAGE, "https://x/cp"))
        b = chunk_page(extract(PAGE, "https://x/cp"))
        self.assertEqual([c.chunk_id for c in a], [c.chunk_id for c in b])

    def test_chunk_id_changes_with_location_not_wording(self):
        same = chunk_id_for("https://x/cp", "A > B", 0)
        self.assertEqual(same, chunk_id_for("https://x/cp", "A > B", 0))
        self.assertNotEqual(same, chunk_id_for("https://x/cp", "A > C", 0))


if __name__ == "__main__":
    unittest.main()
