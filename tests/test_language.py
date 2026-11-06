import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "plugins", "chinese-proofread", "scripts",
)


class CommandTest(unittest.TestCase):
    """#36: the language and toggle skills share STATE_PATH."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        self.state = os.path.join(
            self.home, ".claude", "chinese-proofread", "state.json")

    def run_script(self, name, *args, **env):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, name), *args],
            capture_output=True, text=True, encoding="utf-8", check=True,
            env={
                **{k: v for k, v in os.environ.items()
                   if not k.startswith("CHINESE_PROOFREAD_")},
                "HOME": self.home, "PYTHONIOENCODING": "utf-8", **env,
            },
        )
        return result.stdout

    def read_state(self):
        with open(self.state, encoding="utf-8") as f:
            return json.load(f)

    def test_default_is_english(self):
        out = self.run_script("language.py")
        self.assertIn("Explanation language: English", out)
        self.assertIn("Chat reply language: English", out)
        self.assertFalse(os.path.exists(self.state))

    def test_set_and_reset(self):
        out = self.run_script("language.py", "korean")
        self.assertIn("Explanation language: Korean", out)
        self.assertEqual(self.read_state(), {"lang": "Korean"})
        out = self.run_script("language.py", "Traditional", " Chinese")
        self.assertIn("Explanation language: Traditional Chinese", out)
        out = self.run_script("language.py", "reset")
        self.assertIn("Explanation language: English", out)
        self.assertEqual(self.read_state(), {})

    def test_rejects_what_is_not_a_language_name(self):
        for arg in ("prompt", "Korean.", "x" * 31, "Say hi; then English"):
            with self.subTest(arg=arg):
                out = self.run_script("language.py", arg)
                self.assertIn("Usage: /chinese-proofread:language", out)
                self.assertFalse(os.path.exists(self.state))

    def test_environment_comes_first(self):
        out = self.run_script("language.py", "Korean",
                              CHINESE_PROOFREAD_LANG="Japanese")
        self.assertIn("CHINESE_PROOFREAD_LANG is set", out)
        self.assertIn("Explanation language: Japanese", out)
        self.assertEqual(self.read_state(), {"lang": "Korean"})

    def test_chat_language(self):
        self.run_script("language.py", "Korean")
        out = self.run_script("language.py", CHINESE_PROOFREAD_CHAT_LANG="prompt")
        self.assertIn("Chat reply language: same as the prompt", out)
        self.assertIn("Chat reply language: Korean", self.run_script("toggle.py", "status"))

    def test_toggle_keeps_the_language(self):
        self.run_script("language.py", "Korean")
        self.run_script("toggle.py", "off")
        self.assertEqual(self.read_state(), {"lang": "Korean", "enabled": False})
        self.run_script("language.py", "reset")
        self.assertEqual(self.read_state(), {"enabled": False})


if __name__ == "__main__":
    unittest.main()
