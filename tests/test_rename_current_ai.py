import argparse
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "discordctl.py"
spec = importlib.util.spec_from_file_location("discordctl_under_test", MODULE_PATH)
discordctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discordctl)


class DummyArgs(argparse.Namespace):
    pass


class RenameCurrentAiTests(unittest.TestCase):
    def test_build_parser_includes_rename_current_ai_and_excludes_auto_rename_hook(self):
        parser = discordctl.build_parser()

        subparsers_action = next(action for action in parser._actions if getattr(action, "choices", None))
        choices = subparsers_action.choices.keys()

        self.assertIn("rename-current-ai", choices)
        self.assertNotIn("auto-rename-hook", choices)

    def test_rename_current_ai_dry_run_returns_suggested_name(self):
        with mock.patch.object(discordctl, "load_cc_token", return_value="token"), \
             mock.patch.object(
                 discordctl,
                 "context_for_target",
                 return_value={"channel": {"id": "123", "name": "old", "type_name": "public_thread"}},
             ), \
             mock.patch.object(discordctl, "title_context_for_thread", return_value="rename me"), \
             mock.patch.object(discordctl, "suggest_title", return_value=("新标题", "llm")), \
             mock.patch.object(discordctl, "patch_channel") as patch_channel, \
             mock.patch.object(discordctl, "save_state", side_effect=AssertionError("manual rename should not write watcher state")):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                discordctl.cmd_rename_current_ai(DummyArgs(channel_id=None, dry_run=True, json=True))

        out = json.loads(buffer.getvalue())
        self.assertEqual(out["action"], "rename-current-ai")
        self.assertEqual(out["new_name"], "新标题")
        patch_channel.assert_not_called()

    def test_rename_current_ai_renames_current_thread(self):
        with mock.patch.object(discordctl, "load_cc_token", return_value="token"), \
             mock.patch.object(
                 discordctl,
                 "context_for_target",
                 return_value={"channel": {"id": "123", "name": "old", "type_name": "public_thread"}},
             ), \
             mock.patch.object(discordctl, "title_context_for_thread", return_value="rename me"), \
             mock.patch.object(discordctl, "suggest_title", return_value=("新标题", "llm")), \
             mock.patch.object(discordctl, "patch_channel") as patch_channel:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                discordctl.cmd_rename_current_ai(DummyArgs(channel_id=None, dry_run=False, json=True))

        out = json.loads(buffer.getvalue())
        self.assertEqual(out["new_name"], "新标题")
        patch_channel.assert_called_once_with("123", "token", {"name": "新标题"})

    def test_rename_current_ai_rejects_non_thread(self):
        with mock.patch.object(discordctl, "load_cc_token", return_value="token"), \
             mock.patch.object(
                 discordctl,
                 "context_for_target",
                 return_value={"channel": {"id": "123", "name": "old", "type_name": "text"}},
             ):
            with self.assertRaisesRegex(discordctl.DiscordSkillError, "only supported for Discord threads"):
                discordctl.cmd_rename_current_ai(DummyArgs(channel_id=None, dry_run=True, json=True))

    def test_title_context_for_thread_falls_back_when_no_session_record(self):
        with mock.patch.object(discordctl, "find_cc_session_record_by_thread_id", return_value=None):
            result = discordctl.title_context_for_thread("123", fallback="fallback name")

        self.assertEqual(result, "fallback name")


if __name__ == "__main__":
    unittest.main()
