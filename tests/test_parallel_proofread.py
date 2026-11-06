import datetime
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
        # Most tests compare the text; StyleTest covers the colors.
        self.env.update(HOME=self.home, FAKE_LOG=self.log, FAKE_OUTPUT=BLOCK,
                        NO_COLOR="1",
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
    def run_worker(self, lang="Korean", level=None, region=None,
                   phonetic=None, prompt="让他更快", **env):
        job = {"prompt": prompt, "lang": lang}
        for key, value in [("level", level), ("region", region),
                           ("phonetic", phonetic)]:
            if value is not None:
                job[key] = value
        running = self.write_job("1.running", job)
        self.run_script(WORKER, args=[running], **env)

    def system_prompt(self):
        with open(self.log, encoding="utf-8") as f:
            args = json.load(f)["args"]
        return args[args.index("--append-system-prompt") + 1]

    def result(self):
        with open(os.path.join(self.folder, "1.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_block_becomes_a_result(self):
        self.run_worker()
        self.assertEqual(self.result(), {"block": BLOCK})
        self.assertEqual(self.files(), ["1.json"])

    def test_label_is_added_in_the_explanation_language(self):
        for lang, label in [("Korean", "설명:"), (" english ", "Explanation:")]:
            with self.subTest(lang=lang):
                self.run_worker(
                    lang=lang,
                    FAKE_OUTPUT="📝 中文校对\n修正: 让它更快\n- 它(tā)\n---")
                self.assertEqual(self.result(), {
                    "block": f"📝 中文校对\n修正: 让它更快\n{label}\n- 它(tā)\n---"})

    def test_label_of_the_model_is_replaced(self):
        for written in ["설명:", "Explanation:", "Explanations：", "설명:"]:
            with self.subTest(written=written):
                self.run_worker(
                    lang="English",
                    FAKE_OUTPUT=f"📝 中文校对\n修正: 让它更快\n{written}\n- Use 它.\n---")
                self.assertEqual(self.result(), {
                    "block": "📝 中文校对\n修正: 让它更快\nExplanation:\n- Use 它.\n---"})

    def test_word_lines_get_no_label(self):
        block = "📝 中文校对\n- 按键 → 按钮(ànniǔ): 버튼입니다.\n---"
        self.run_worker(FAKE_OUTPUT=block)
        self.assertEqual(self.result(), {"block": block})

    def test_other_languages_get_no_label(self):
        self.run_worker(
            lang="Japanese",
            FAKE_OUTPUT="📝 中文校对\n修正: 让它更快\n설명:\n- 它を使います。\n---")
        self.assertEqual(self.result(), {
            "block": "📝 中文校对\n修正: 让它更快\n- 它を使います。\n---"})

    def test_natural_line_is_written_in_the_explanation_language(self):
        for lang, line in [("Korean", "📝 中文校对: ✅ 자연스럽습니다."),
                           ("English", "📝 中文校对: ✅ Looks natural."),
                           ("Japanese", "📝 中文校对: ✅")]:
            for output in ["📝 中文校对: ✅", "📝 中文校对: ✅ 자연스럽습니다.",
                           "📝 中文校对: ✅ 自然流畅"]:
                with self.subTest(lang=lang, output=output):
                    self.run_worker(lang=lang, FAKE_OUTPUT=output)
                    self.assertEqual(self.result(), {"block": line})

    def test_examples_follow_the_explanation_language(self):
        for lang, example in [("Korean", "사물을 가리킬 때는"),
                              ("English", "to refer to a thing"),
                              ("Japanese", "to refer to a thing")]:
            with self.subTest(lang=lang):
                self.run_worker(lang=lang, level="beginner", region="taiwan")
                prompt = self.system_prompt()
                self.assertIn(f"explanations in {lang}", prompt)
                self.assertIn(example, prompt)
        self.assertNotIn("사물", prompt)
        self.assertNotIn("대만에서는 번체자를 씁니다", prompt)

    def test_nothing_to_proofread_leaves_no_result(self):
        self.run_worker(FAKE_OUTPUT="NONE\n")
        self.assertEqual(self.files(), [])

    def history_dir(self):
        return os.path.join(
            self.home, ".claude", "chinese-proofread", "history")

    def history_files(self):
        try:
            names = sorted(os.listdir(self.history_dir()))
        except FileNotFoundError:
            return []
        return [os.path.join(self.history_dir(), n) for n in names]

    def history(self):
        entries = []
        for path in self.history_files():
            with open(path, encoding="utf-8") as f:
                entries += [json.loads(line) for line in f]
        return entries

    def test_correction_is_recorded(self):
        self.run_worker()
        entry, = self.history()
        self.assertEqual(entry["v"], 1)
        self.assertEqual(entry["lang"], "Korean")
        self.assertEqual(entry["block"], BLOCK)
        self.assertIsNotNone(
            datetime.datetime.fromisoformat(entry["time"]).tzinfo)

    def test_history_is_private(self):
        self.run_worker()
        path, = self.history_files()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_history_leaves_the_prompt_out(self):
        running = self.write_job(
            "1.running", {"prompt": "秘密 token=abc", "lang": "Korean"})
        self.run_script(WORKER, args=[running])
        path, = self.history_files()
        with open(path, encoding="utf-8") as f:
            self.assertNotIn("abc", f.read())

    def test_corrections_add_up(self):
        self.run_worker()
        self.run_worker()
        self.assertEqual(len(self.history()), 2)

    def test_only_corrections_are_recorded(self):
        for output in ("📝 中文校对: ✅ 자연스럽습니다.", "NONE\n", "好的。"):
            self.run_worker(FAKE_OUTPUT=output)
        self.run_worker(FAKE_EXIT="1")
        self.assertEqual(self.history_files(), [])

    def test_history_can_be_turned_off(self):
        self.run_worker(CHINESE_PROOFREAD_HISTORY="0")
        self.assertEqual(self.result(), {"block": BLOCK})
        self.assertEqual(self.history_files(), [])

    def test_history_failure_keeps_the_result(self):
        os.makedirs(os.path.dirname(self.history_dir()))
        with open(self.history_dir(), "w", encoding="utf-8"):
            pass  # A file where the folder should be.
        self.run_worker()
        self.assertEqual(self.result(), {"block": BLOCK})
        self.assertEqual(self.files(), ["1.json"])

    def test_parallel_workers_keep_lines_whole(self):
        block = "📝 中文校对\n修正: " + "它" * 20000 + "\n---"
        workers = [
            subprocess.Popen(
                [sys.executable, WORKER,
                 self.write_job(f"{i}.running",
                                {"prompt": "让他更快", "lang": "Korean"})],
                env=dict(self.env, FAKE_OUTPUT=block))
            for i in range(8)
        ]
        for worker in workers:
            self.assertEqual(worker.wait(), 0)
        self.assertEqual([e["block"] for e in self.history()], [block] * 8)

    def test_default_level_adds_no_rules(self):
        self.run_worker(level="intermediate")
        with_level = self.system_prompt()
        self.run_worker()
        self.assertEqual(self.system_prompt(), with_level)
        self.assertNotIn("# 학습 수준", with_level)

    def test_level_rules_are_appended(self):
        for level, heading in [("beginner", "# 학습 수준: 초급"),
                               ("advanced", "# 학습 수준: 고급")]:
            with self.subTest(level=level):
                self.run_worker(level=level)
                prompt = self.system_prompt()
                self.assertIn("explanations in Korean", prompt)
                self.assertIn(heading, prompt)

    def test_unknown_level_in_a_job_is_the_default(self):
        self.run_worker(level="../proofread")
        self.assertNotIn("# 학습 수준", self.system_prompt())
        self.assertEqual(self.result(), {"block": BLOCK})

    def test_default_region_adds_no_rules(self):
        self.run_worker(region="mainland")
        with_region = self.system_prompt()
        self.run_worker()
        self.assertEqual(self.system_prompt(), with_region)
        self.assertNotIn("# 교정 기준 지역", with_region)

    def test_region_rules_are_appended_after_the_level(self):
        self.run_worker(level="advanced", region="taiwan")
        prompt = self.system_prompt()
        self.assertIn("explanations in Korean", prompt)
        self.assertLess(prompt.index("# 학습 수준: 고급"),
                        prompt.index("# 교정 기준 지역: 대만"))

    def test_unknown_region_in_a_job_is_the_default(self):
        self.run_worker(region="../levels/advanced")
        self.assertNotIn("# 교정 기준 지역", self.system_prompt())
        self.assertNotIn("# 학습 수준", self.system_prompt())
        self.assertEqual(self.result(), {"block": BLOCK})

    def test_zhuyin_replaces_the_pinyin(self):
        block = "📝 中文校对\n原文: 让他更快\n修正: 让它更快\n설명:\n- 它(tā)를 씁니다.\n---"
        self.run_worker(phonetic="zhuyin", FAKE_OUTPUT=block)
        shown = block.replace("(tā)", "(ㄊㄚ)")
        self.assertEqual(self.result(), {"block": shown})
        self.assertEqual([e["block"] for e in self.history()], [shown])
        # The model is not told about zhuyin; it always writes pinyin.
        with open(self.log, encoding="utf-8") as f:
            self.assertNotIn("zhuyin", " ".join(json.load(f)["args"]))

    def test_pinyin_stays_by_default(self):
        block = "📝 中文校对\n修正: 让它更快\n설명:\n- 它(tā)를 씁니다.\n---"
        self.run_worker(FAKE_OUTPUT=block)
        self.assertEqual(self.result(), {"block": block})

    def test_traditional_heading_is_the_block(self):
        self.run_worker(region="taiwan",
                        FAKE_OUTPUT="📝 中文校對: ✅ 자연스럽습니다.")
        self.assertEqual(self.result(), {"block": "📝 中文校对: ✅ 자연스럽습니다."})

    def test_bare_check_mark_is_nothing_to_fix(self):
        # #35: with the rules in Korean, the model sometimes dropped the
        # heading or translated it.
        for output in ["✅", "✅ ", "📝 중국어 교정: ✅"]:
            with self.subTest(output=output):
                self.run_worker(FAKE_OUTPUT=output)
                self.assertEqual(self.result(),
                                 {"block": "📝 中文校对: ✅ 자연스럽습니다."})

    def test_check_mark_after_other_text_is_a_failure(self):
        self.run_worker(FAKE_OUTPUT="好的。\n✅")
        self.assertEqual(self.result(), {"error": "unexpected output"})

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
        # Not a sentence from the examples in the instructions.
        self.run_worker(prompt="把这个文件删掉")
        with open(self.log, encoding="utf-8") as f:
            call = json.load(f)
        self.assertEqual(call["internal"], "1")
        self.assertIn("把这个文件删掉", call["stdin"])
        self.assertNotIn("--bare", call["args"])  # --bare never reads OAuth.
        self.assertNotIn("把这个文件删掉", " ".join(call["args"]))
        for flag in ["--tools", "--setting-sources"]:
            self.assertEqual(call["args"][call["args"].index(flag) + 1], "")
        self.assertIn("explanations in Korean", " ".join(call["args"]))
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

    def test_level_reaches_the_proofreading(self):
        self.submit("帮我重构一下这个函数", CHINESE_PROOFREAD_LEVEL=" Advanced ")
        self.wait_for_result()
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("# 학습 수준: 고급",
                          " ".join(json.load(f)["args"]))

    def test_region_and_phonetic_reach_the_proofreading(self):
        self.submit("帮我重构一下这个函数", CHINESE_PROOFREAD_REGION="Taiwan",
                    CHINESE_PROOFREAD_PHONETIC=" zhuyin ",
                    FAKE_OUTPUT="📝 中文校对\n설명:\n- 函式(hánshì)\n---")
        self.wait_for_result()
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("# 교정 기준 지역: 대만",
                          " ".join(json.load(f)["args"]))
        result = [n for n in self.files() if n.endswith(".json")][0]
        with open(os.path.join(self.folder, result), encoding="utf-8") as f:
            self.assertIn("函式(ㄏㄢˊ ㄕˋ)", json.load(f)["block"])

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


class StyleTest(Base):
    def show(self, columns="", **env):
        output = self.run_script(SHOW, json.dumps(
            {"session_id": SESSION, "hook_event_name": "PostToolUse"}),
            NO_COLOR="", COLUMNS=columns, **env)
        return json.loads(output)["systemMessage"]

    def row(self, text):
        return f"{show_result.STYLE}{text}{show_result.RESET}"

    def test_rows_fill_the_window(self):
        self.write_job("1.json", {"block": "first\n让它"})
        width = 30 - show_result.MARGIN
        self.assertEqual(self.show("30"), "\n".join([
            "", self.row("first".ljust(width)),
            self.row("让它" + " " * (width - 4))]))

    def test_rows_stop_at_the_maximum_width(self):
        self.write_job("1.json", {"block": "first\n" + "让" * 40})
        width = show_result.MAX_WIDTH
        self.assertEqual(self.show("200"), "\n".join([
            "", self.row("first".ljust(width)),
            self.row("让" * (width // 2)), self.row("让" * 4 + " " * (width - 8))]))

    def test_rows_match_without_the_window_size(self):
        self.write_job("1.json", {"block": "first\nsecond line"})
        for columns in ("", "abc", "10"):
            with self.subTest(columns=columns):
                self.write_job("1.json", {"block": "first\nsecond line"})
                self.assertEqual(self.show(columns), "\n".join([
                    "", self.row("first      "), self.row("second line")]))

    def test_long_chinese_is_wrapped_into_full_rows(self):
        self.write_job("1.json", {"block": "让" * 30})
        rows = self.show("30").split("\n")[1:]
        self.assertEqual(rows, [
            self.row("让" * 12), self.row("让" * 12), self.row("让" * 6 + " " * 12)])

    def test_long_line_breaks_at_a_space(self):
        self.assertEqual(show_result.wrapped("first second", 8), ["first", "second"])

    def test_short_label_stays_with_the_text_after_it(self):
        self.assertEqual(
            show_result.wrapped("原文: 让他更快一点", 12),
            ["原文: 让他更", "快一点"])

    def test_emoji_with_a_selector_counts_as_wide(self):
        self.assertEqual(show_result.text_width("⚠️"), 2)

    def test_lines_between_results_stay_empty(self):
        self.write_job("1.json", {"block": "first"})
        self.write_job("2.json", {"block": "second"})
        self.assertEqual(self.show(), "\n".join([
            "", self.row("first "), "", self.row("second")]))

    def test_failure_is_styled(self):
        self.write_job("1.json", {"error": "timed out after 60s"})
        self.assertIn(show_result.STYLE, self.show())

    def test_no_color_leaves_the_block_as_it_is(self):
        self.write_job("1.json", {"block": BLOCK})
        output = self.run_script(SHOW, json.dumps(
            {"session_id": SESSION, "hook_event_name": "PostToolUse"}),
            NO_COLOR="1", COLUMNS="30")
        self.assertEqual(json.loads(output)["systemMessage"], BLOCK)


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


class HistoryFileTest(unittest.TestCase):
    def test_each_month_gets_a_file(self):
        zone = datetime.timezone(datetime.timedelta(hours=9))
        times = [
            datetime.datetime(2026, 10, 31, 23, 59, 59, tzinfo=zone),
            datetime.datetime(2026, 11, 1, 0, 0, 0, tzinfo=zone),
        ]
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(jobs, "HISTORY_DIR", folder), \
                mock.patch.object(jobs, "datetime") as clock, \
                mock.patch.dict(os.environ, CHINESE_PROOFREAD_HISTORY="1"):
            clock.datetime.now.return_value.astimezone.side_effect = times
            jobs.append_history(BLOCK, "Korean")
            jobs.append_history(BLOCK, "Korean")
            self.assertEqual(sorted(os.listdir(folder)),
                             ["2026-10.jsonl", "2026-11.jsonl"])
            with open(os.path.join(folder, "2026-10.jsonl"),
                      encoding="utf-8") as f:
                entry, = [json.loads(line) for line in f]
        self.assertEqual(entry["time"], "2026-10-31T23:59:59+09:00")


class LevelTest(unittest.TestCase):
    def test_level_comes_from_the_environment(self):
        cases = [(None, "intermediate"), ("beginner", "beginner"),
                 ("ADVANCED", "advanced"), ("hsk4", "intermediate"),
                 ("", "intermediate")]
        for value, expected in cases:
            env = {} if value is None else {"CHINESE_PROOFREAD_LEVEL": value}
            with self.subTest(value=value), \
                    mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(jobs.level(), expected)


class RegionTest(unittest.TestCase):
    def test_region_comes_from_the_environment(self):
        cases = [(None, "mainland"), ("taiwan", "taiwan"),
                 (" TAIWAN ", "taiwan"), ("hongkong", "mainland")]
        for value, expected in cases:
            env = {} if value is None else {"CHINESE_PROOFREAD_REGION": value}
            with self.subTest(value=value), \
                    mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(jobs.region(), expected)

    def test_phonetic_comes_from_the_environment(self):
        cases = [(None, "pinyin"), ("zhuyin", "zhuyin"),
                 ("Zhuyin", "zhuyin"), ("bopomofo", "pinyin")]
        for value, expected in cases:
            env = {} if value is None else {"CHINESE_PROOFREAD_PHONETIC": value}
            with self.subTest(value=value), \
                    mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(jobs.phonetic(), expected)


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
