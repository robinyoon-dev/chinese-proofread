import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "plugins", "chinese-proofread", "hooks",
)
DETECT = os.path.join(HOOKS_DIR, "detect_chinese.py")
SHOW = os.path.join(HOOKS_DIR, "show_result.py")
WORKER = os.path.join(HOOKS_DIR, "proofread_worker.py")
SESSION = "11111111-2222-3333-4444-555555555555"
BLOCK = "📝 中文校对\n原文: 让他更快\n修正: 让它更快\n---"

sys.path.insert(0, HOOKS_DIR)
import jobs  # noqa: E402
import proofread_worker  # noqa: E402
import show_result  # noqa: E402

FAKE_CLAUDE = f"""\
#!{sys.executable}
import json, os, sys, time
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
with open(os.environ["FAKE_LOG"], "w", encoding="utf-8") as f:
    json.dump({{"args": sys.argv[1:], "stdin": sys.stdin.read(),
               "internal": os.environ.get("CHINESE_PROOFREAD_INTERNAL")}}, f)
sys.stdout.buffer.write(os.environ.get("FAKE_OUTPUT", "").encode("utf-8"))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


class Base(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = home.name
        bin_dir = os.path.join(self.home, "bin")
        os.makedirs(bin_dir)
        claude = os.path.join(bin_dir, "claude")
        with open(claude, "w", encoding="utf-8") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(claude, os.stat(claude).st_mode | stat.S_IEXEC)

        self.log = os.path.join(self.home, "claude.json")
        self.env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("CHINESE_PROOFREAD_")
        }
        self.env.update(HOME=self.home, FAKE_LOG=self.log, FAKE_OUTPUT=BLOCK,
                        PATH=bin_dir + os.pathsep + self.env["PATH"])
        self.folder = os.path.join(
            self.home, ".claude", "chinese-proofread", "jobs", SESSION)

    def run_script(self, script, stdin="", args=(), **env):
        result = subprocess.run(
            [sys.executable, script, *args], input=stdin, capture_output=True,
            text=True, encoding="utf-8", env=dict(self.env, **env),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def files(self):
        try:
            return sorted(os.listdir(self.folder))
        except FileNotFoundError:
            return []

    def write_job(self, name, value):
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        return path


class WorkerTest(Base):
    def run_worker(self, lang="Korean", **env):
        running = self.write_job(
            "1.running", {"prompt": "让他更快", "lang": lang})
        self.run_script(WORKER, args=[running], **env)

    def result(self):
        with open(os.path.join(self.folder, "1.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_block_becomes_a_result(self):
        self.run_worker()
        self.assertEqual(self.result(), {"block": BLOCK})
        self.assertEqual(self.files(), ["1.json"])

    def test_label_stays_for_korean(self):
        block = "📝 中文校对\n修正: 让它更快\n설명:\n- 사물은 它입니다.\n---"
        self.run_worker(FAKE_OUTPUT=block)
        self.assertEqual(self.result(), {"block": block})

    def test_label_is_dropped_for_other_languages(self):
        self.run_worker(
            lang="English",
            FAKE_OUTPUT="📝 中文校对\n修正: 让它更快\n설명:\n- Use 它.\n---")
        self.assertEqual(
            self.result(), {"block": "📝 中文校对\n修正: 让它更快\n- Use 它.\n---"})

    def test_nothing_to_proofread_leaves_no_result(self):
        self.run_worker(FAKE_OUTPUT="NONE\n")
        self.assertEqual(self.files(), [])

    def test_answering_the_prompt_is_a_failure(self):
        self.run_worker(FAKE_OUTPUT="好的，我来修改这个函数。")
        self.assertEqual(self.result(), {"error": "unexpected output"})

    def test_claude_failure_is_reported(self):
        self.run_worker(FAKE_EXIT="1")
        self.assertEqual(self.result(), {"error": "claude exited with 1"})

    def test_missing_claude_is_reported(self):
        self.run_worker(PATH=os.path.join(self.home, "nowhere"))
        self.assertEqual(self.result(), {"error": "claude command not found"})

    def test_timeout_is_reported(self):
        timeout = subprocess.TimeoutExpired("claude", 60)
        with mock.patch("proofread_worker.subprocess.run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                proofread_worker.proofread("让他更快", "Korean")

    def test_broken_job_is_reported(self):
        running = os.path.join(self.home, "2.running")
        with open(running, "w", encoding="utf-8") as f:
            f.write("not json")
        self.run_script(WORKER, args=[running])
        with open(os.path.join(self.home, "2.json"), encoding="utf-8") as f:
            self.assertIn("error", json.load(f))
        self.assertFalse(os.path.exists(running))

    def test_claude_runs_isolated_with_the_prompt_on_stdin(self):
        self.run_worker()
        with open(self.log, encoding="utf-8") as f:
            call = json.load(f)
        self.assertEqual(call["internal"], "1")
        self.assertIn("让他更快", call["stdin"])
        self.assertNotIn("--bare", call["args"])  # --bare never reads OAuth.
        self.assertNotIn("让他更快", " ".join(call["args"]))
        for flag in ["--tools", "--setting-sources"]:
            self.assertEqual(call["args"][call["args"].index(flag) + 1], "")
        self.assertIn("✅ line in Korean", " ".join(call["args"]))
        self.assertTrue(os.path.exists(proofread_worker.PROMPT_FILE))


class DetectStartsJobTest(Base):
    def submit(self, prompt, **env):
        return self.run_script(DETECT, json.dumps(
            {"prompt": prompt, "session_id": SESSION}), **env)

    def wait_for_result(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if any(n.endswith(".json") for n in self.files()):
                return
            time.sleep(0.02)
        self.fail("no result")

    def test_hook_does_not_wait_for_the_proofreading(self):
        started = time.time()
        output = self.submit("帮我重构一下这个函数", FAKE_SLEEP="2")
        self.assertLess(time.time() - started, 1.5)
        self.assertNotEqual(output, "")
        self.assertTrue(any(n.endswith(".running") for n in self.files()))
        self.wait_for_result()

    def test_prompt_reaches_the_shown_result(self):
        self.submit("帮我重构一下这个函数")
        self.wait_for_result()
        output = self.run_script(SHOW, json.dumps(
            {"session_id": SESSION, "hook_event_name": "PostToolUse"}))
        self.assertEqual(json.loads(output), {"systemMessage": BLOCK})

    def test_other_prompts_start_nothing(self):
        self.submit("이 함수를 리팩터링해 줘")
        self.assertEqual(self.files(), [])

    def test_internal_run_starts_nothing(self):
        self.submit("帮我重构一下这个函数", CHINESE_PROOFREAD_INTERNAL="1")
        self.assertEqual(self.files(), [])

    def expected_language(self):
        try:
            with open(os.path.join(self.folder, jobs.REPLY_FILE),
                      encoding="utf-8") as f:
                return json.load(f)["language"]
        except OSError:
            return None

    def test_expected_reply_language(self):
        cases = [
            ({}, "Korean"),
            ({"CHINESE_PROOFREAD_LANG": "English"}, "English"),
            ({"CHINESE_PROOFREAD_CHAT_LANG": "Japanese"}, "Japanese"),
            ({"CHINESE_PROOFREAD_CHAT_LANG": "prompt"}, None),
            ({"CHINESE_PROOFREAD_CHAT_LANG": "Simplified Chinese"}, None),
            ({"CHINESE_PROOFREAD_LANG": "中文"}, None),
        ]
        for env, language in cases:
            with self.subTest(env=env):
                self.submit("帮我重构一下这个函数", **env)
                self.assertEqual(self.expected_language(), language)

    def test_no_expected_language_when_the_prompt_names_chinese(self):
        self.submit("请用中文解释一下这个函数")
        self.assertIsNone(self.expected_language())

    def test_a_later_prompt_clears_the_expected_language(self):
        self.submit("帮我重构一下这个函数")
        self.submit("이 함수를 리팩터링해 줘")
        self.assertIsNone(self.expected_language())


class ShowResultTest(Base):
    def show(self, event="PostToolUse"):
        output = self.run_script(SHOW, json.dumps(
            {"session_id": SESSION, "hook_event_name": event}))
        return json.loads(output)["systemMessage"] if output else None

    def test_result_is_shown_once(self):
        self.write_job("1.json", {"block": BLOCK})
        self.assertEqual(self.show(), BLOCK)
        self.assertIsNone(self.show())
        self.assertEqual(self.files(), [])

    def test_results_are_shown_in_prompt_order(self):
        self.write_job("2.json", {"block": "second"})
        self.write_job("1.json", {"block": "first"})
        self.assertEqual(self.show("Stop"), "first\n\nsecond")

    def test_failure_is_shown(self):
        self.write_job("1.json", {"error": "timed out after 60s"})
        self.assertEqual(
            self.show(), "⚠️ 中文校对: proofreading failed (timed out after 60s)")

    def test_tool_hook_does_not_wait(self):
        self.write_job("1.running", {})
        started = time.time()
        self.assertIsNone(self.show())
        self.assertLess(time.time() - started, 5)
        self.assertEqual(self.files(), ["1.running"])

    def test_stop_waits_for_a_running_job(self):
        running = self.write_job("1.running", {})

        def finish():
            time.sleep(0.5)
            self.write_job("1.json", {"block": BLOCK})
            os.remove(running)

        thread = threading.Thread(target=finish)
        thread.start()
        self.addCleanup(thread.join)
        self.assertEqual(self.show("Stop"), BLOCK)

    def test_stop_gives_up_and_the_result_stays_for_later(self):
        self.write_job("1.running", {})
        with mock.patch("show_result.STOP_WAIT_SECONDS", 0.1):
            show_result.wait_for_jobs(self.folder)
        self.assertEqual(self.files(), ["1.running"])

    def test_dead_worker_counts_as_failure(self):
        running = self.write_job("1.running", {})
        old = time.time() - jobs.STALE_SECONDS - 1
        os.utime(running, (old, old))
        self.assertEqual(
            self.show("Stop"), "⚠️ 中文校对: proofreading failed (no result)")
        self.assertEqual(self.files(), [])

    def test_only_one_process_gets_a_job(self):
        path = self.write_job("1.json", {"block": BLOCK})
        self.assertIsNotNone(show_result.claim(path))
        self.assertIsNone(show_result.claim(path))

    def stop_with_reply(self, reply):
        self.write_job(jobs.REPLY_FILE, {"language": "Korean"})
        output = self.run_script(SHOW, json.dumps({
            "session_id": SESSION, "hook_event_name": "Stop",
            "last_assistant_message": reply}))
        return json.loads(output) if output else None

    def test_chinese_reply_is_rewritten_once(self):
        output = self.stop_with_reply("递归就是函数不断调用自己来解决问题。")
        self.assertEqual(output["decision"], "block")
        self.assertIn("in Korean", output["reason"])
        self.assertEqual(self.files(), [])
        self.assertEqual(self.run_script(SHOW, json.dumps({
            "session_id": SESSION, "hook_event_name": "Stop",
            "last_assistant_message": "递归就是函数不断调用自己来解决问题。"})), "")

    def test_rewrite_keeps_the_result(self):
        self.write_job("1.json", {"block": BLOCK})
        output = self.stop_with_reply("递归就是函数不断调用自己来解决问题。")
        self.assertEqual(output["systemMessage"], BLOCK)
        self.assertEqual(output["decision"], "block")

    def test_chinese_followed_by_english_is_rewritten(self):
        self.assertIn("reason", self.stop_with_reply(
            "递归就是函数不断调用自己来解决问题。\n\n(In English: Recursion is "
            "when a function calls itself.)"))

    def test_other_replies_are_left_alone(self):
        replies = {
            "korean": "재귀(递归)는 함수가 자기 자신을 호출하는 방식입니다.",
            "english": "Recursion (递归) is a function calling itself.",
            "fence": "주석을 추가했습니다.\n```python\n# 这个函数用来计算两个数字的平均值\n```",
            "backticks": "`这个函数用来计算两个数字的平均值`를 넣었습니다.",
            "quoted sentence": "재귀는 함수가 자기 자신을 호출해서 문제를 작게 나누어 "
                               "푸는 방법입니다.\n"
                               "중국어로는 递归就是自己调用自己直到遇到终止条件입니다.",
            "japanese": "再帰処理は関数が自分自身を呼び出して問題を解決する方法です。",
        }
        for name, reply in replies.items():
            with self.subTest(name):
                self.assertIsNone(self.stop_with_reply(reply))

    def test_tool_hook_leaves_the_expected_language(self):
        self.write_job(jobs.REPLY_FILE, {"language": "Korean"})
        self.show()
        self.assertEqual(self.files(), [jobs.REPLY_FILE])

    def test_invalid_input(self):
        for stdin in ["", "not json", "[]", "{}", '{"session_id": "../x"}']:
            with self.subTest(stdin=stdin):
                self.assertEqual(self.run_script(SHOW, stdin), "")


class SweepTest(unittest.TestCase):
    def test_only_old_sessions_are_removed(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, "old")
            new = os.path.join(root, "new")
            os.makedirs(old)
            os.makedirs(new)
            past = time.time() - jobs.KEEP_SECONDS - 1
            os.utime(old, (past, past))
            with mock.patch("jobs.JOBS_DIR", root):
                jobs.sweep()
            self.assertEqual(os.listdir(root), ["new"])


class HooksJsonTest(unittest.TestCase):
    def test_stop_timeout_outlasts_the_wait(self):
        with open(os.path.join(HOOKS_DIR, "hooks.json"), encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]
        self.assertNotIn("PreToolUse", hooks)  # See show_result.py.
        timeout = hooks["Stop"][0]["hooks"][0]["timeout"]
        self.assertGreater(timeout, show_result.STOP_WAIT_SECONDS)


if __name__ == "__main__":
    unittest.main()
