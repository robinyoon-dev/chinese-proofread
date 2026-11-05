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

from jobs import (BLOCK, DEFAULT_LEVEL, INTERNAL_ENV, LEVELS, WORKER_TIMEOUT,
                  append_history, write_json)

MODEL = "sonnet"
NOTHING_TO_PROOFREAD = "NONE"
# The label is part of the Korean template and the model does not translate it
# reliably, so it is dropped for other languages. The lines below it still read
# as explanations.
KOREAN_LABEL = re.compile(r"^설명:[ \t]*\n", re.M)
PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
PROMPT_FILE = os.path.join(PROMPTS_DIR, "proofread.md")


def level_rules(level):
    # The default level adds nothing, so it proofreads exactly as before. The
    # name becomes a path, so only a known level gets that far.
    if level == DEFAULT_LEVEL or level not in LEVELS:
        return ""
    with open(os.path.join(PROMPTS_DIR, "levels", level + ".md"),
              encoding="utf-8") as f:
        return "\n\n" + f.read()


def command(lang, model=MODEL, level=DEFAULT_LEVEL):
    return [
        "claude", "-p", "--model", model, "--tools", "",
        "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--disable-slash-commands",
        "--system-prompt-file", PROMPT_FILE,
        "--append-system-prompt",
        f"Write the explanations and the ✅ line in {lang}, even though the "
        f"Chinese is in another language. Do not explain in Chinese unless "
        f"{lang} is Chinese." + level_rules(level),
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


def proofread(prompt, lang, model=MODEL, cwd=None, level=DEFAULT_LEVEL):
    """Returns the block, None if there is nothing to proofread, or raises
    RuntimeError with the reason."""
    try:
        result = subprocess.run(
            command(lang, model, level),
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


def record(block, lang):
    # The user still gets the result when the history cannot be written.
    try:
        append_history(block, lang)
    except OSError:
        pass


def main():
    running = sys.argv[1]
    done = running[:-len(".running")] + ".json"
    try:
        with open(running, encoding="utf-8") as f:
            job = json.load(f)
        # A job written before levels existed proofreads at the default.
        block = proofread(job["prompt"], job["lang"],
                          cwd=os.path.dirname(running),
                          level=job.get("level", DEFAULT_LEVEL))
        if block is not None:
            write_json(done, {"block": block})
            record(block, job["lang"])
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        write_json(done, {"error": str(e)})
    os.remove(running)


if __name__ == "__main__":
    main()
