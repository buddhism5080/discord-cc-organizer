import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "discordctl.py"
spec = importlib.util.spec_from_file_location("discordctl_under_test", MODULE_PATH)
discordctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discordctl)


class TitleContextTests(unittest.TestCase):
    def test_collect_title_context_keeps_whole_messages_under_limit(self):
        history = [
            {"role": "user", "content": "A" * 6000},
            {"role": "user", "content": "B" * 3900},
            {"role": "user", "content": "C" * 500},
        ]

        result = discordctl.collect_title_context_from_history(history, max_chars=10000)

        self.assertEqual(result, ("A" * 6000) + "\n\n" + ("B" * 3900))

    def test_collect_title_context_keeps_single_oversized_message_whole(self):
        history = [{"role": "user", "content": "X" * 12000}]

        result = discordctl.collect_title_context_from_history(history, max_chars=10000)

        self.assertEqual(result, "X" * 12000)

    def test_collect_title_context_ignores_assistant_messages(self):
        history = [
            {"role": "assistant", "content": "ignore me"},
            {"role": "user", "content": "real task"},
        ]

        result = discordctl.collect_title_context_from_history(history)

        self.assertEqual(result, "real task")

    def test_llm_title_sends_full_unsplit_prompt_payload(self):
        prompt = ("A" * 6000) + "\n\n" + ("B" * 3900)
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": "生成标题"}}]
                }).encode("utf-8")

        def fake_urlopen(req, timeout=20):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch.object(
            discordctl,
            "openai_config",
            return_value={"base_url": "http://example.test", "api_key": "k", "model": "m"},
        ), mock.patch.object(discordctl.urllib.request, "urlopen", side_effect=fake_urlopen):
            title = discordctl.llm_title(prompt)

        self.assertEqual(title, "生成标题")
        self.assertEqual(captured["payload"]["messages"][1]["content"], prompt)


if __name__ == "__main__":
    unittest.main()
