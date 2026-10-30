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
SCRIPT = os.path.join(HOOKS_DIR, "require_block_first.py")
STOP_SCRIPT = os.path.join(HOOKS_DIR, "continue_after_block.py")

BLOCK = "📝 中文校对\n原文: 帮我跑测试\n修正: 帮我跑一下测试\n설명:\n- ...\n---"


def user(prompt_id, content):
    return {"type": "user", "promptId": prompt_id,
            "message": {"role": "user", "content": content}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def text(value):
    return {"type": "text", "text": value}


def tool_use(tool_use_id, name="Bash"):
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}


class HookTestCase(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = home.name
        self.env = dict(os.environ, HOME=self.home)
        self.transcript = os.path.join(self.home, "transcript.jsonl")
        self.pending_dir = os.path.join(self.home, ".claude", "chinese-proofread", "pending")

    def set_pending(self, prompt_id="p-1", session_id="s-1"):
        os.makedirs(self.pending_dir, exist_ok=True)
        with open(os.path.join(self.pending_dir, session_id), "w", encoding="utf-8") as f:
            f.write(prompt_id)

    def pending(self, session_id="s-1"):
        try:
            with open(os.path.join(self.pending_dir, session_id), encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def pending_exists(self, session_id="s-1"):
        return self.pending(session_id) is not None

    def write_transcript(self, *entries):
        with open(self.transcript, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def run_script(self, script, stdin):
        result = subprocess.run(
            [sys.executable, script],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout


class GateTest(HookTestCase):
    def run_hook(self, tool_name="Bash", tool_use_id="t-1", prompt_id="p-1", stdin=None):
        if stdin is None:
            stdin = json.dumps({
                "session_id": "s-1", "prompt_id": prompt_id,
                "transcript_path": self.transcript, "hook_event_name": "PreToolUse",
                "tool_name": tool_name, "tool_use_id": tool_use_id,
            })
        return self.run_script(SCRIPT, stdin)

    def assertDenied(self, output):
        decision = json.loads(output)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("📝 中文校对", decision["permissionDecisionReason"])

    def test_denies_tool_call_before_block(self):
        self.set_pending()
        self.write_transcript(
            user("p-1", "帮我跑测试"),
            assistant(tool_use("t-0", "Skill")),
            user("p-1", [{"type": "tool_result", "tool_use_id": "t-0", "content": "skill"}]),
            assistant({"type": "thinking", "thinking": BLOCK}, tool_use("t-1")),
        )
        self.assertDenied(self.run_hook())
        self.assertEqual(self.pending(), "continue:p-1")

    def test_denies_only_once(self):
        self.set_pending()
        self.write_transcript(user("p-1", "帮我跑测试"), assistant(tool_use("t-1")))
        self.assertDenied(self.run_hook())
        self.write_transcript(
            user("p-1", "帮我跑测试"), assistant(tool_use("t-1")),
            user("p-1", [{"type": "tool_result", "tool_use_id": "t-1", "content": "denied"}]),
            assistant(tool_use("t-2")),
        )
        self.assertEqual(self.run_hook(tool_use_id="t-2"), "")

    def test_allows_after_block(self):
        for block in [BLOCK, "📝 中文校对: ✅ 자연스럽습니다."]:
            with self.subTest(block=block):
                self.set_pending()
                self.write_transcript(
                    user("p-1", "帮我跑测试"), assistant(text(block), tool_use("t-1")),
                )
                self.assertEqual(self.run_hook(), "")
                self.assertFalse(self.pending_exists())

    def test_ignores_block_from_earlier_prompt(self):
        self.set_pending("p-2")
        self.write_transcript(
            user("p-1", "帮我跑测试"), assistant(text(BLOCK)),
            user("p-2", "再跑一遍"), assistant(tool_use("t-1")),
        )
        self.assertDenied(self.run_hook(prompt_id="p-2"))

    def test_allows_skill(self):
        self.set_pending()
        self.write_transcript(user("p-1", "帮我跑测试"), assistant(tool_use("t-1", "Skill")))
        self.assertEqual(self.run_hook(tool_name="Skill"), "")
        self.assertTrue(self.pending_exists())

    def test_allows_without_pending_file(self):
        self.write_transcript(user("p-1", "帮我跑测试"), assistant(tool_use("t-1")))
        self.assertEqual(self.run_hook(), "")

    def test_allows_when_pending_file_is_for_another_prompt(self):
        self.set_pending("p-0")
        self.write_transcript(user("p-1", "帮我跑测试"), assistant(tool_use("t-1")))
        self.assertEqual(self.run_hook(), "")
        self.assertTrue(self.pending_exists())

    def test_allows_when_tool_use_never_reaches_transcript(self):
        self.set_pending()
        self.write_transcript(user("p-1", "帮我跑测试"))
        self.assertEqual(self.run_hook(), "")
        # The next call checks again.
        self.assertTrue(self.pending_exists())

    def test_invalid_input(self):
        self.set_pending()
        for stdin in ["", "not json", "{}", "[]", '"text"', '{"prompt_id": "p-1"}']:
            with self.subTest(stdin=stdin):
                self.assertEqual(self.run_hook(stdin=stdin), "")

    def test_broken_transcript_lines_are_skipped(self):
        self.set_pending()
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("not json\n[]\n")
            f.write(json.dumps(user("p-1", "帮我跑测试")) + "\n")
            f.write(json.dumps(assistant(tool_use("t-1"))) + "\n")
        self.assertDenied(self.run_hook())


class ContinueTest(HookTestCase):
    def run_hook(self, message, prompt_id="p-1", stdin=None):
        if stdin is None:
            stdin = json.dumps({
                "session_id": "s-1", "prompt_id": prompt_id, "hook_event_name": "Stop",
                "stop_hook_active": False, "last_assistant_message": message,
            })
        return self.run_script(STOP_SCRIPT, stdin)

    def test_continues_after_block_only_reply(self):
        self.set_pending("continue:p-1")
        output = json.loads(self.run_hook(BLOCK))
        self.assertEqual(output["decision"], "block")
        self.assertFalse(self.pending_exists())

    def test_continues_only_once(self):
        self.set_pending("continue:p-1")
        self.run_hook(BLOCK)
        self.assertEqual(self.run_hook(BLOCK), "")

    def test_stops_when_block_was_skipped(self):
        # Claude retried the call without the block and finished the work.
        self.set_pending("continue:p-1")
        self.assertEqual(self.run_hook("테스트를 작성했습니다."), "")
        self.assertFalse(self.pending_exists())

    def test_stops_without_denial(self):
        for pending in [None, "p-1", "continue:p-0"]:
            with self.subTest(pending=pending):
                if pending is not None:
                    self.set_pending(pending)
                self.assertEqual(self.run_hook(BLOCK), "")

    def test_invalid_input(self):
        self.set_pending("continue:p-1")
        for stdin in ["", "not json", "{}", "[]", '"text"']:
            with self.subTest(stdin=stdin):
                self.assertEqual(self.run_hook(None, stdin=stdin), "")
        self.assertEqual(self.pending(), "continue:p-1")


if __name__ == "__main__":
    unittest.main()
