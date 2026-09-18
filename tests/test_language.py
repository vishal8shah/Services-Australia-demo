import json
import unittest
from unittest import mock

from saal import llm
from saal.answer import language
from saal.answer.synthesize import build_user_message


class TestLanguage(unittest.TestCase):
    def test_speech_recogniser_codes_are_normalised(self):
        self.assertEqual(language.normalise("vi-VN"), "vi")
        self.assertEqual(language.normalise("zh-HK"), "yue")
        self.assertEqual(language.normalise("fil-PH"), "fil")
        self.assertIsNone(language.normalise("<script>"))
        self.assertIsNone(language.normalise(""))

    def test_scripts_the_old_detector_missed(self):
        self.assertEqual(language.detect("ਮੇਰੀ ਮਾਂ ਸਾਡੇ ਨਾਲ ਰਹਿਣ ਆ ਰਹੀ ਹੈ"), "pa")
        self.assertEqual(language.detect("எனக்கு வேலை இல்லை"), "ta")

    def test_the_model_is_given_a_language_name_not_a_code(self):
        msg = build_user_message("Mẹ tôi 82 tuổi", [], [], "vi")
        self.assertIn("Answer in Vietnamese.", msg)

    def test_an_undetected_language_is_left_to_the_model(self):
        msg = build_user_message("Mia madre ha 82 anni", [], [], "en")
        self.assertIn("same language the QUESTION is written in", msg)


class TestEffort(unittest.TestCase):
    def _body(self, **kw):
        captured = {}

        def _open(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            from io import BytesIO

            class R(BytesIO):
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R(json.dumps({"stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "{}"}]}).encode())
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=False), \
             mock.patch("urllib.request.urlopen", _open):
            llm.chat("s", "u", provider="anthropic", model="m", **kw)
        return captured["body"]

    def test_effort_is_sent_only_when_asked(self):
        self.assertEqual(self._body(effort="low")["output_config"], {"effort": "low"})
        self.assertNotIn("output_config", self._body())
