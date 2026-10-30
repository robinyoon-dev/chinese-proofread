import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "plugins", "chinese-proofread", "hooks",
)
SCRIPT = os.path.join(HOOKS_DIR, "detect_chinese.py")

sys.path.insert(0, HOOKS_DIR)
from detect_chinese import is_chinese  # noqa: E402


class IsChineseTest(unittest.TestCase):
    def test_chinese(self):
        for prompt in [
            "帮我重构一下这个函数，让它运行得更快",
            "把 `parse_config()` 改成异步函数",
            "幫我把這個函數改成非同步",
        ]:
            with self.subTest(prompt=prompt):
                self.assertTrue(is_chinese(prompt))

    def test_not_chinese(self):
        for prompt in [
            "",
            "refactor this function",
            "이 함수를 리팩터링해 줘",
            "この関数を非同期に変更してください",
            "好的",
            "谢谢你",
        ]:
            with self.subTest(prompt=prompt):
                self.assertFalse(is_chinese(prompt))

    def test_min_hanzi_boundary(self):
        self.assertTrue(is_chinese("我知道了"))
        self.assertFalse(is_chinese("我知道了", min_hanzi=5))

    def test_latin_without_hangul_needs_fewer_hanzi(self):
        self.assertTrue(is_chinese("跑local server."))
        self.assertTrue(is_chinese("帮我fix一下这个bug"))

    def test_words_mixed_into_korean_or_english(self):
        # 9-5: the skill corrects Chinese words in other languages too, so a
        # single hanzi is enough once Latin letters or Hangul appear.
        for prompt in [
            "设置 画面에 暗黑 模式 추가해 줘",
            "이 函数는 返回值를 바꿔서 처리해야 합니다",
            "로그인 按键 좀 키워 줘",
            "跑로컬 서버",
            "this API is too 慢",
        ]:
            with self.subTest(prompt=prompt):
                self.assertTrue(is_chinese(prompt))

    def test_hanzi_ratio_skips_korean_with_few_hanzi(self):
        # For users who write Korean hanja words: CHINESE_PROOFREAD_HANZI_RATIO.
        self.assertFalse(is_chinese("이 函数는 返回值를 바꿔서 처리해야 합니다",
                                    hanzi_ratio=0.5))
        self.assertTrue(is_chinese("帮我把로컬 서버跑起来", hanzi_ratio=0.5))

    def test_min_hanzi_mixed_above_min_hanzi(self):
        # README: a larger MIN_HANZI_MIXED falls back to MIN_HANZI.
        self.assertFalse(is_chinese("跑local server.", min_hanzi_mixed=5))
        self.assertTrue(is_chinese("帮我跑一下local server", min_hanzi_mixed=10))

    def test_zero_min_hanzi(self):
        for prompt in ["", "hello", "안녕하세요"]:
            with self.subTest(prompt=prompt):
                self.assertFalse(is_chinese(prompt, min_hanzi=0, min_hanzi_mixed=0))
        self.assertTrue(is_chinese("好", min_hanzi=0))

    @unittest.expectedFailure
    def test_known_limit_japanese_without_kana(self):
        # Known limit: Japanese written only in kanji passes as Chinese.
        self.assertFalse(is_chinese("本日休業"))


class HookTest(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = home.name
        self.env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("CHINESE_PROOFREAD_")
        }
        # Keep the real ~/.claude state file out of the tests.
        self.env["HOME"] = self.home

    def run_hook(self, stdin, **env):
        result = subprocess.run(
            [sys.executable, SCRIPT],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(self.env, **env),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def run_prompt(self, prompt, **env):
        return self.run_hook(json.dumps({"prompt": prompt}), **env)

    def write_state(self, text):
        path = os.path.join(self.home, ".claude", "chinese-proofread")
        os.makedirs(path)
        with open(os.path.join(path, "state.json"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_chinese_prompt(self):
        output = json.loads(self.run_prompt("帮我重构一下这个函数"))["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        self.assertIn("chinese-proofread:proofread", output["additionalContext"])
        self.assertIn("in Korean", output["additionalContext"])

    def test_lang(self):
        output = self.run_prompt("帮我重构一下这个函数", CHINESE_PROOFREAD_LANG="English")
        self.assertIn("in English", output)

    def test_not_chinese_prompt(self):
        self.assertEqual(self.run_prompt("이 함수를 리팩터링해 줘"), "")

    def test_hanzi_ratio_setting(self):
        prompt = "이 函数는 返回值를 바꿔서 처리해야 합니다"
        self.assertNotEqual(self.run_prompt(prompt), "")
        self.assertEqual(
            self.run_prompt(prompt, CHINESE_PROOFREAD_HANZI_RATIO="0.5"), ""
        )

    def test_invalid_input(self):
        for stdin in [
            "", "not json", "{}", "[]", '"text"', '{"prompt": null}', '{"prompt": 123}',
        ]:
            with self.subTest(stdin=stdin):
                self.assertEqual(self.run_hook(stdin), "")

    def test_invalid_number_settings_fall_back_to_defaults(self):
        for name in [
            "CHINESE_PROOFREAD_MIN_HANZI",
            "CHINESE_PROOFREAD_MIN_HANZI_MIXED",
            "CHINESE_PROOFREAD_HANZI_RATIO",
        ]:
            for value in ["abc", ""]:
                with self.subTest(name=name, value=value):
                    self.assertNotEqual(
                        self.run_prompt("帮我重构一下这个函数", **{name: value}), ""
                    )
                    self.assertEqual(
                        self.run_prompt("이 함수를 리팩터링해 줘", **{name: value}), ""
                    )

    def test_zero_min_hanzi(self):
        for prompt in ["", "hello"]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    self.run_prompt(prompt, CHINESE_PROOFREAD_MIN_HANZI="0"), ""
                )

    def test_disabled_by_env(self):
        output = self.run_prompt("帮我重构一下这个函数", CHINESE_PROOFREAD_ENABLED="0")
        self.assertEqual(output, "")

    def test_disabled_by_state_file(self):
        self.write_state('{"enabled": false}')
        self.assertEqual(self.run_prompt("帮我重构一下这个函数"), "")

    def test_broken_state_file_counts_as_enabled(self):
        self.write_state("not json")
        self.assertNotEqual(self.run_prompt("帮我重构一下这个函数"), "")


if __name__ == "__main__":
    unittest.main()
