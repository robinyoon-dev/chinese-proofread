import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "plugins", "chinese-proofread")
SCRIPT = os.path.join(ROOT, "scripts", "history.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import history  # noqa: E402
import jobs  # noqa: E402

KOREAN_BLOCK = (
    "📝 中文校对\n原文: 让他更快\n修正: 让它更快\n설명:\n"
    "- 사물을 가리킬 때는 它(tā)를 씁니다.\n- 문장부호: 마침표를 붙입니다.\n---"
)


def ago(**delta):
    return datetime.datetime.now().astimezone() - datetime.timedelta(**delta)


def record(time, block=KOREAN_BLOCK):
    return json.dumps({
        "v": jobs.HISTORY_VERSION,
        "time": time.isoformat(timespec="seconds"),
        "lang": "Korean",
        "block": block,
    }, ensure_ascii=False)


class ExplanationsTest(unittest.TestCase):
    def test_keeps_only_the_bullets(self):
        self.assertEqual(history.explanations(KOREAN_BLOCK), [
            "사물을 가리킬 때는 它(tā)를 씁니다.",
            "문장부호: 마침표를 붙입니다.",
        ])

    def test_does_not_depend_on_the_label(self):
        block = "📝 中文校对\n原文: 跑\n修正: 运行\n- Use 运行 here.\n---"
        self.assertEqual(history.explanations(block), ["Use 运行 here."])

    def test_word_format(self):
        block = "📝 中文校对\n- 例外 → 异常(yìcháng): 예외는 异常입니다.\n---"
        self.assertEqual(history.explanations(block), ["例外 → 异常(yìcháng): 예외는 异常입니다."])


class ParseDaysTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(history.parse_days([]), history.DEFAULT_DAYS)
        self.assertEqual(history.parse_days(["30"]), 30)
        self.assertIsNone(history.parse_days(["ALL"]))

    def test_rejects_the_rest(self):
        for args in (["0"], ["-1"], ["week"], ["1", "2"]):
            with self.assertRaises(ValueError, msg=args):
                history.parse_days(args)


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        original = jobs.HISTORY_DIR
        jobs.HISTORY_DIR = self.tmp.name
        self.addCleanup(setattr, jobs, "HISTORY_DIR", original)

    def write(self, name, *lines):
        with open(os.path.join(self.tmp.name, name), "w", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def test_reads_only_the_months_of_the_period(self):
        for name in ("2026-09.jsonl", "2026-10.jsonl", "2026-11.jsonl", "notes.txt"):
            self.write(name)
        since = datetime.datetime(2026, 10, 28).astimezone()
        names = [os.path.basename(p) for p in history.month_files(since)]
        self.assertEqual(names, ["2026-10.jsonl", "2026-11.jsonl"])

    def test_all_reads_every_month(self):
        self.write("2026-09.jsonl")
        self.write("2026-11.jsonl")
        self.assertEqual(len(history.month_files(None)), 2)

    def test_no_folder_means_no_records(self):
        jobs.HISTORY_DIR = os.path.join(self.tmp.name, "missing")
        self.assertEqual(history.read_records(None), ([], 0))

    def test_filters_by_time_inside_a_file(self):
        self.write(
            "2026-11.jsonl",
            record(ago(days=8), "old"),
            record(ago(days=6), "new"),
        )
        self.assertEqual(history.read_records(ago(days=7)), (["new"], 0))

    def test_period_across_months(self):
        since = datetime.datetime(2026, 10, 28, 12).astimezone()
        self.write("2026-10.jsonl", record(since + datetime.timedelta(hours=1), "october"))
        self.write("2026-11.jsonl", record(since + datetime.timedelta(days=5), "november"))
        self.assertEqual(history.read_records(since)[0], ["october", "november"])

    def test_skips_lines_it_cannot_use(self):
        future = json.dumps({
            "v": jobs.HISTORY_VERSION + 1,
            "time": ago(hours=1).isoformat(),
            "block": "future",
        })
        self.write(
            "2026-11.jsonl",
            "{half a line",
            '{"v": 1}',
            '[1, 2]',
            '{"v": 1, "time": "yesterday", "block": "x"}',
            '{"v": 1, "time": "2026-11-01T00:00:00+09:00", "block": 3}',
            future,
            record(ago(hours=1), "kept"),
        )
        self.assertEqual(history.read_records(None), (["kept"], 6))


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, ".claude", "chinese-proofread", "history")

    def write(self, *lines):
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, ago().strftime("%Y-%m") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def run_script(self, *args, **env):
        result = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, encoding="utf-8", check=True,
            env={
                **{k: v for k, v in os.environ.items()
                   if not k.startswith("CHINESE_PROOFREAD_")},
                "HOME": self.tmp.name, "PYTHONIOENCODING": "utf-8", **env,
            },
        )
        return result.stdout

    def test_no_history(self):
        out = self.run_script()
        self.assertIn("Period: last 7 days", out)
        self.assertIn("Corrections in the period: 0", out)
        self.assertNotIn("1. ", out)

    def test_numbers_the_lines_and_leaves_the_sentences_out(self):
        self.write(record(ago(hours=2)), record(ago(hours=1)))
        out = self.run_script()
        self.assertIn("Corrections read: 2", out)
        self.assertIn("Explanation lines: 4", out)
        self.assertIn("4. 문장부호: 마침표를 붙입니다.", out)
        self.assertNotIn("让他更快", out)
        self.assertNotIn("让它更快", out)

    def test_stays_under_the_output_limit_and_keeps_the_newest(self):
        count = 60
        block = "📝 中文校对\n- " + "\n- ".join(
            f"교정 {{}}의 설명 {n} " + "中文说明" * 40 for n in range(5)
        ) + "\n---"
        self.write(*(
            record(ago(hours=count - i), block.format(*[i] * 5))
            for i in range(count)
        ))
        out = self.run_script()
        self.assertLess(len(out.encode("utf-8")), history.MAX_OUTPUT_BYTES)
        self.assertIn(f"Corrections in the period: {count}", out)
        read = int(out.split("Corrections read: ")[1].split()[0])
        self.assertLess(read, count)
        self.assertIn(f"교정 {count - 1}의 설명 4", out)
        self.assertIn(f"교정 {count - read}의 설명 0", out)
        self.assertNotIn(f"교정 {count - read - 1}의 설명", out)

    def test_days_argument(self):
        self.write(record(ago(days=20)))
        self.assertIn("Corrections in the period: 0", self.run_script("10"))
        self.assertIn("Corrections in the period: 1", self.run_script("30"))
        self.assertIn("Period: all records", self.run_script("all"))

    def test_bad_argument_prints_usage(self):
        for arg in ("week", "0", "99999999999999"):
            out = self.run_script(arg)
            self.assertIn("Usage: /chinese-proofread:history [days|all]", out)
            self.assertIn("Chat reply language: Korean", out)

    def test_reports_recording_is_off(self):
        out = self.run_script(CHINESE_PROOFREAD_HISTORY="0")
        self.assertIn("CHINESE_PROOFREAD_HISTORY=0 is set", out)

    def test_reports_skipped_lines(self):
        self.write("{half a line")
        self.assertIn("Unreadable records skipped: 1", self.run_script())

    def test_chat_language_follows_the_settings(self):
        out = self.run_script(CHINESE_PROOFREAD_LANG="English")
        self.assertIn("Chat reply language: English", out)
        out = self.run_script(CHINESE_PROOFREAD_CHAT_LANG="prompt")
        self.assertIn("Chat reply language: same as the prompt", out)


if __name__ == "__main__":
    unittest.main()
