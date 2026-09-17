"""Transport tests with a fake urlopen: request shape, parsing, and failure modes.

These are the tests that would otherwise only run when someone has a key, a
network and a working balance, which is to say the morning of the demo.
"""
import io
import json
import unittest
import urllib.error
from unittest import mock

from saal import llm
from saal.answer.providers import ProviderError, get_provider
from saal.retrieve.expand import get_expander

KEYS = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "sk-ant-test"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(payload, captured):
    def _open(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode())
        return FakeResponse(json.dumps(payload).encode())
    return _open


OPENAI_REPLY = {"choices": [{"message": {"content": '{"payments": []}'}}]}
ANTHROPIC_REPLY = {"content": [{"type": "text", "text": '{"payments": []}'}]}


class TestChat(unittest.TestCase):
    def test_openai_request_shape(self):
        captured = {}
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("urllib.request.urlopen", fake_urlopen(OPENAI_REPLY, captured)):
            text = llm.chat("sys", "user", provider="openai", model="gpt-test")
        self.assertIn("/v1/chat/completions", captured["url"])
        self.assertEqual(captured["headers"]["authorization"], "Bearer sk-test")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")
        self.assertEqual(text, '{"payments": []}')

    def test_anthropic_request_shape(self):
        captured = {}
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("urllib.request.urlopen", fake_urlopen(ANTHROPIC_REPLY, captured)):
            text = llm.chat("sys", "user", provider="anthropic", model="claude-test")
        self.assertIn("/v1/messages", captured["url"])
        self.assertEqual(captured["headers"]["x-api-key"], "sk-ant-test")
        self.assertEqual(captured["body"]["system"], "sys")
        self.assertEqual(text, '{"payments": []}')

    def test_json_mode_off_omits_the_response_format(self):
        captured = {}
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("urllib.request.urlopen", fake_urlopen(OPENAI_REPLY, captured)):
            llm.chat("sys", "user", provider="openai", json_mode=False)
        self.assertNotIn("response_format", captured["body"])

    def test_a_missing_key_is_named_in_the_error(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.chat("sys", "user", provider="openai")
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_the_provider_error_body_is_surfaced(self):
        def raising(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", {},
                io.BytesIO(b'{"error":{"message":"The model gpt-nope does not exist"}}'))

        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("urllib.request.urlopen", raising):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.chat("sys", "user", provider="openai", model="gpt-nope")
        self.assertIn("does not exist", str(ctx.exception))


class TestParseJson(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(llm.parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_and_prefaced(self):
        self.assertEqual(llm.parse_json('Here you go:\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_array(self):
        self.assertEqual(llm.parse_json('["constant care", "income test"]'),
                         ["constant care", "income test"])

    def test_no_json_at_all(self):
        with self.assertRaises(llm.LLMError):
            llm.parse_json("I cannot help with that.")


class TestProviderWiring(unittest.TestCase):
    def test_openai_provider_returns_the_parsed_object(self):
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.answer.providers.chat", return_value='{"payments": [], "next_actions": []}'):
            out = get_provider("openai").answer("q", [], [], "en")
        self.assertEqual(out["payments"], [])

    def test_a_non_object_response_is_a_provider_error(self):
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.answer.providers.chat", return_value='["not", "an", "object"]'):
            with self.assertRaises(ProviderError):
                get_provider("openai").answer("q", [], [], "en")

    def test_a_missing_key_fails_at_construction_not_at_question_time(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(llm.LLMError):
                get_provider("openai")

    def test_the_expander_parses_a_phrase_list(self):
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.retrieve.expand.chat",
                        return_value='["constant care", "income test"]'):
            self.assertEqual(get_expander("openai").expand("Mum is moving in"),
                             ["constant care", "income test"])

    def test_the_expander_unwraps_an_object_wrapped_list(self):
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.retrieve.expand.chat",
                        return_value='{"phrases": ["constant care"]}'):
            self.assertEqual(get_expander("openai").expand("x"), ["constant care"])

    def test_a_failing_expander_returns_nothing_rather_than_failing_the_question(self):
        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.retrieve.expand.chat", side_effect=llm.LLMError("429")):
            self.assertEqual(get_expander("openai").expand("x"), [])


if __name__ == "__main__":
    unittest.main()


class TestDoctor(unittest.TestCase):
    def test_a_broken_key_is_reported_as_a_failure(self):
        from saal import doctor

        with mock.patch.dict("os.environ",
                             {**KEYS, "SAAL_LLM_PROVIDER": "openai"}, clear=False), \
             mock.patch("saal.config.LLM_PROVIDER", "openai"), \
             mock.patch("saal.doctor.chat", side_effect=llm.LLMError("openai 401: bad key")):
            self.assertEqual(doctor.main(), 1)

    def test_a_working_setup_reports_success(self):
        from saal import doctor

        with mock.patch.dict("os.environ", KEYS, clear=False), \
             mock.patch("saal.config.LLM_PROVIDER", "openai"), \
             mock.patch("saal.doctor.chat", return_value='{"ok": true}'):
            self.assertEqual(doctor.main(), 0)
