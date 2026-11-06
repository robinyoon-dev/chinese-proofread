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

from jobs import (BLOCK, DEFAULT_LEVEL, DEFAULT_PHONETIC, DEFAULT_REGION,
                  INTERNAL_ENV, LEVELS, NOTHING_TO_FIX, REGIONS, WORKER_TIMEOUT,
                  append_history, write_json)
from zhuyin import convert_block

MODEL = "sonnet"
NOTHING_TO_PROOFREAD = "NONE"
TRADITIONAL_BLOCK = BLOCK.replace("对", "對")
PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
PROMPT_FILE = os.path.join(PROMPTS_DIR, "proofread.md")
# The rules are in English; the examples are in the explanation language, and
# any language without its own examples gets the English ones (#35).
LANGUAGES = {"korean": "korean", "한국어": "korean",
             "english": "english", "영어": "english"}
EXAMPLE_LANGUAGE = "english"
# The model did not write these two reliably in languages other than Korean
# (#34), so the code adds them. A language not listed gets neither: a guessed
# translation would be worse than none.
LABELS = {"korean": "설명:", "english": "Explanation:"}
NATURAL = {"korean": "자연스럽습니다.", "english": "Looks natural."}
# A label the model wrote anyway, in whatever language.
MODEL_LABEL = re.compile(r"^(?:설명|說明|说明|explanations?)[ \t]*[:：][ \t]*\n",
                         re.M | re.I)


def language(lang):
    return LANGUAGES.get(lang.strip().lower())


def read_prompt(*parts):
    path = os.path.join(PROMPTS_DIR, *parts)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return "\n\n" + f.read()


def examples(lang, *parts):
    return read_prompt("examples", language(lang) or EXAMPLE_LANGUAGE, *parts)


def rules(folder, name, names, default, lang):
    # A default adds nothing, so it proofreads exactly as before. The name
    # becomes a path, so only a known name gets that far.
    if name == default or name not in names:
        return ""
    return (read_prompt(folder, name + ".md")
            + examples(lang, folder, name + ".md"))


def command(lang, model=MODEL, level=DEFAULT_LEVEL, region=DEFAULT_REGION):
    return [
        "claude", "-p", "--model", model, "--tools", "",
        "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--disable-slash-commands",
        "--system-prompt-file", PROMPT_FILE,
        "--append-system-prompt",
        f"Write the explanations in {lang}, even though the Chinese is in "
        f"another language. Do not explain in Chinese unless {lang} is "
        f"Chinese."
        + examples(lang, "proofread.md")
        + rules("levels", level, LEVELS, DEFAULT_LEVEL, lang)
        + rules("regions", region, REGIONS, DEFAULT_REGION, lang),
    ]


def message(prompt):
    return f"<user_prompt>\n{prompt}\n</user_prompt>\n"


def parse_output(output):
    output = output.strip()
    if output == NOTHING_TO_PROOFREAD:
        return None
    # Told to write traditional characters, the model sometimes turns the
    # heading too; the rest of the code looks for the fixed one.
    if output.startswith(TRADITIONAL_BLOCK):
        output = BLOCK + output[len(TRADITIONAL_BLOCK):]
    # Anything else means the model answered the prompt instead.
    if not output.startswith(BLOCK):
        raise RuntimeError("unexpected output")
    return output


def fit_language(block, lang):
    """Adds the label above the explanations and the sentence of the ✅ line
    in the explanation language."""
    if block is None:
        return None
    key = language(lang)
    lines = block.split("\n")
    if block.startswith(NOTHING_TO_FIX):
        lines[0] = NOTHING_TO_FIX + (" " + NATURAL[key] if key else "")
        return "\n".join(lines)
    lines = MODEL_LABEL.sub("", block).split("\n")
    if key:
        for i, line in enumerate(lines):
            if line.startswith("- "):
                # Word lines stand alone, as in the format of mixed-in words.
                if any(above.startswith("修正") for above in lines[:i]):
                    lines.insert(i, LABELS[key])
                break
    return "\n".join(lines)


def fit_phonetic(block, phonetic):
    # The model always writes pinyin; zhuyin is a fixed mapping from it.
    if block is None or phonetic != "zhuyin":
        return block
    return convert_block(block)


def proofread(prompt, lang, model=MODEL, cwd=None, level=DEFAULT_LEVEL,
              region=DEFAULT_REGION, phonetic=DEFAULT_PHONETIC):
    """Returns the block, None if there is nothing to proofread, or raises
    RuntimeError with the reason."""
    try:
        result = subprocess.run(
            command(lang, model, level, region),
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
    return fit_phonetic(fit_language(parse_output(result.stdout), lang),
                        phonetic)


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
        # A job written before these settings existed uses the defaults.
        block = proofread(job["prompt"], job["lang"],
                          cwd=os.path.dirname(running),
                          level=job.get("level", DEFAULT_LEVEL),
                          region=job.get("region", DEFAULT_REGION),
                          phonetic=job.get("phonetic", DEFAULT_PHONETIC))
        if block is not None:
            write_json(done, {"block": block})
            record(block, job["lang"])
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        write_json(done, {"error": str(e)})
    os.remove(running)


if __name__ == "__main__":
    main()
