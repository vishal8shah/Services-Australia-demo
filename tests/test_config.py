"""The env file loader. A secret handling path deserves tests more than most."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from saal.config import _load_env_file

SAMPLE = """
# a comment
OPENAI_API_KEY=sk-from-file
export SAAL_LLM_PROVIDER=openai
QUOTED="with spaces"
SINGLE='single quoted'
WITH_COMMENT=gpt-4o-mini  # the fast one
NOT_AN_ASSIGNMENT
EMPTY=
"""


class TestEnvFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / ".env"
        self.path.write_text(SAMPLE)
        self.addCleanup(self.dir.cleanup)

    def load(self, environ=None):
        with mock.patch.dict(os.environ, environ or {}, clear=True):
            loaded = _load_env_file(self.path)
            return loaded, dict(os.environ)

    def test_reads_values_and_strips_export(self):
        _loaded, env = self.load()
        self.assertEqual(env["OPENAI_API_KEY"], "sk-from-file")
        self.assertEqual(env["SAAL_LLM_PROVIDER"], "openai")

    def test_handles_quotes_and_trailing_comments(self):
        _loaded, env = self.load()
        self.assertEqual(env["QUOTED"], "with spaces")
        self.assertEqual(env["SINGLE"], "single quoted")
        self.assertEqual(env["WITH_COMMENT"], "gpt-4o-mini")

    def test_skips_comments_blanks_and_malformed_lines(self):
        _loaded, env = self.load()
        self.assertNotIn("NOT_AN_ASSIGNMENT", env)
        self.assertEqual(env["EMPTY"], "")

    def test_the_shell_always_wins_over_the_file(self):
        """A stale file quietly overriding the key you just exported is an hour
        of debugging that should never be available to anyone."""
        _loaded, env = self.load({"OPENAI_API_KEY": "sk-from-shell"})
        self.assertEqual(env["OPENAI_API_KEY"], "sk-from-shell")

    def test_a_missing_file_is_not_an_error(self):
        self.assertFalse(_load_env_file(Path(self.dir.name) / "nope.env"))


class TestSecretsAreIgnored(unittest.TestCase):
    def test_gitignore_covers_env_files_but_not_the_example(self):
        rules = (Path(__file__).resolve().parent.parent / ".gitignore").read_text()
        self.assertIn(".env", rules)
        self.assertIn("!.env.example", rules)


if __name__ == "__main__":
    unittest.main()


class TestPreflight(unittest.TestCase):
    """The checks that run before everything else, so they cannot be the thing
    that breaks on a machine nobody has tested on."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "preflight", Path(__file__).resolve().parent.parent / "scripts" / "preflight.py")
        self.preflight = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.preflight)

    def test_an_old_python_is_named_with_the_fix(self):
        problem = self.preflight.python_problem((3, 9, 6), "/usr/bin/python3")
        self.assertIn("3.9", problem)
        self.assertIn("/usr/bin/python3", problem)
        self.assertIn("PYTHON=python3.12", problem)

    def test_a_new_enough_python_passes(self):
        self.assertIsNone(self.preflight.python_problem((3, 12, 1), "/x/python3"))
        self.assertIsNone(self.preflight.python_problem((4, 0, 0), "/x/python3"))

    def test_missing_fts5_is_reported_not_raised(self):
        def no_fts5():
            raise RuntimeError("no such module: fts5")

        problem = self.preflight.fts5_problem(no_fts5)
        self.assertIn("FTS5", problem)
        self.assertIn("brew install", problem)

    def test_this_machine_passes_both(self):
        self.assertEqual(self.preflight.problems(), [])
