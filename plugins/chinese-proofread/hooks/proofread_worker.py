#!/usr/bin/env python3
"""Proofread one prompt in a separate claude -p, apart from the work.

detect_chinese.py starts this with the path of a .running job. The result
goes to a .json job for show_result.py; a prompt with nothing to proofread
leaves no result. A failure is a result too, so the user hears about it.

--bare would be the shorter way to isolate claude -p, but it never reads OAuth,
so it fails for subscription users. --setting-sources "" keeps the user's
plugins and their hooks out; INTERNAL_ENV is the second guard against recursion.

Usage: proofread_worker.py <job>.running
"""

import json
import os
import re
import subprocess
import sys

from jobs import BLOCK, INTERNAL_ENV, WORKER_TIMEOUT, write_json

MODEL = "sonnet"
NOTHING_TO_PROOFREAD = "NONE"
# The label is part of the Korean template and the model does not translate it
# reliably, so it is dropped for other languages. The lines below it still read
# as explanations.
KOREAN_LABEL = re.compile(r"^설명:[ \t]*\n", re.M)
PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts", "proofread.md",
)


def command(lang, model=MODEL):
    return [
        "claude", "-p", "--model", model, "--tools", "",
        "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--disable-slash-commands",
        "--system-prompt-file", PROMPT_FILE,
        "--append-system-prompt",
        f"Write the explanations and the ✅ line in {lang}, even though the "
        f"Chinese is in another language. Do not explain in Chinese unless "
        f"{lang} is Chinese.",
    ]


def message(prompt):
    return f"<user_prompt>\n{prompt}\n</user_prompt>\n"


def parse_output(output):
    output = output.strip()
    if output == NOTHING_TO_PROOFREAD:
        return None
    # Anything else means the model answered the prompt instead.
    if not output.startswith(BLOCK):
        raise RuntimeError("unexpected output")
    return output


def fit_language(block, lang):
    if block is None or lang.strip().lower() in ("korean", "한국어"):
        return block
    return KOREAN_LABEL.sub("", block)


def proofread(prompt, lang, model=MODEL, cwd=None):
    """Returns the block, None if there is nothing to proofread, or raises
    RuntimeError with the reason."""
    try:
        result = subprocess.run(
            command(lang, model),
            input=message(prompt),
            capture_output=True, text=True, encoding="utf-8",
            timeout=WORKER_TIMEOUT, cwd=cwd,
            env=dict(os.environ, **{INTERNAL_ENV: "1"}),
        )
    except FileNotFoundError:
        raise RuntimeError("claude command not found")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timed out after {WORKER_TIMEOUT}s")
    if result.returncode != 0:
        raise RuntimeError(f"claude exited with {result.returncode}")
    return fit_language(parse_output(result.stdout), lang)


def main():
    running = sys.argv[1]
    done = running[:-len(".running")] + ".json"
    try:
        with open(running, encoding="utf-8") as f:
            job = json.load(f)
        block = proofread(job["prompt"], job["lang"], cwd=os.path.dirname(running))
        if block is not None:
            write_json(done, {"block": block})
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        write_json(done, {"error": str(e)})
    os.remove(running)


if __name__ == "__main__":
    main()
