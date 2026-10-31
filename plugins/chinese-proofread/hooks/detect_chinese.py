#!/usr/bin/env python3
"""UserPromptSubmit hook: start proofreading for prompts with Chinese in them.

A prompt counts as Chinese when it has at least MIN_HANZI hanzi, no Japanese
kana, and hanzi make up at least HANZI_RATIO of the hanzi plus Hangul
characters. Latin text (code, identifiers) is ignored on purpose.

A prompt with Latin letters or Hangul needs only MIN_HANZI_MIXED hanzi, so
short prompts like "跑local server" and Chinese words mixed into Korean or
English sentences are still proofread. The proofreading agent decides whether
the hanzi were written by the user or quoted. HANZI_RATIO is 0 by default; raising it
skips Korean sentences with only a few hanzi.

Does nothing while proofreading is turned off with the toggle skill.

For a Chinese prompt it starts proofread_worker.py as a separate process, so
the work does not wait for the proofreading and cannot skip it, and tells
Claude to leave the proofreading alone. show_result.py shows the result.

Env:
  CHINESE_PROOFREAD_ENABLED      set to 0 to keep proofreading off
  CHINESE_PROOFREAD_LANG         language for the explanations in the
                                 proofreading block (default: Korean)
  CHINESE_PROOFREAD_CHAT_LANG    language for replies to the user: unset for
                                 CHINESE_PROOFREAD_LANG, "prompt" for the
                                 language of the request, or a language name
  CHINESE_PROOFREAD_MIN_HANZI    minimum hanzi (default: 4)
  CHINESE_PROOFREAD_MIN_HANZI_MIXED
                                 minimum hanzi with Latin letters or Hangul
                                 (default: 1)
  CHINESE_PROOFREAD_HANZI_RATIO  minimum hanzi / (hanzi + Hangul) (default: 0)
  CHINESE_PROOFREAD_INTERNAL     set for the proofreading process itself
"""

import json
import os
import subprocess
import sys

from jobs import INTERNAL_ENV, new_job, session_dir, sweep, write_json

# Keep in sync with STATE_PATH in scripts/toggle.py.
STATE_PATH = os.path.expanduser("~/.claude/chinese-proofread/state.json")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "proofread_worker.py")


def count(text, *ranges):
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in ranges))


def enabled():
    if os.environ.get("CHINESE_PROOFREAD_ENABLED") == "0":
        return False
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f).get("enabled") is not False
    except (OSError, ValueError, AttributeError):
        return True


def env_number(name, default, convert):
    # An invalid value falls back to the default instead of failing the hook.
    try:
        return convert(os.environ[name])
    except (KeyError, ValueError):
        return default


def start_proofreading(session_id, prompt, lang):
    folder = session_dir(session_id)
    if folder is None:
        return
    sweep()
    job = new_job(folder)
    running = job + ".running"
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        write_json(running, {"prompt": prompt, "lang": lang})
        # Nothing may stay attached to this hook, or Claude Code would wait
        # for the worker before starting the work.
        subprocess.Popen(
            [sys.executable, WORKER, running],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as e:
        try:
            write_json(job + ".json", {"error": str(e)})
            os.remove(running)
        except OSError:
            pass


def chat_language(lang):
    chat_lang = os.environ.get("CHINESE_PROOFREAD_CHAT_LANG", "").strip()
    if not chat_lang:
        return f"in {lang}"
    if chat_lang.lower() == "prompt":
        return "in the language the user wrote the request in"
    return f"in {chat_lang}"


def practicing_note():
    # Short answers came back in Chinese without this: the question being in
    # Chinese outweighed the language instruction.
    if os.environ.get("CHINESE_PROOFREAD_CHAT_LANG", "").strip().lower() == "prompt":
        return ""
    return ("This holds even though the request is in Chinese: the user is "
            "practicing Chinese and did not ask for a reply in Chinese.")


def chat_instruction():
    lang = os.environ.get("CHINESE_PROOFREAD_LANG", "Korean")
    return (
        f"write everything you say to the user {chat_language(lang)}, "
        "including direct answers to questions, progress updates, questions "
        "back to the user, and the final summary, "
        "unless the user asks for another language. This does not apply to "
        "what the work produces, such as code, code comments, commit "
        "messages, and file contents, which follow the request and the "
        "repository's conventions."
    )


def is_chinese(prompt, min_hanzi=4, min_hanzi_mixed=1, hanzi_ratio=0.0):
    hanzi = count(prompt, (0x4E00, 0x9FFF), (0x3400, 0x4DBF))
    kana = count(prompt, (0x3040, 0x30FF))
    hangul = count(prompt, (0xAC00, 0xD7A3))
    latin = count(prompt, (0x41, 0x5A), (0x61, 0x7A))

    if latin > 0 or hangul > 0:
        min_hanzi = min(min_hanzi, min_hanzi_mixed)

    if (
        hanzi == 0
        or hanzi < min_hanzi
        or kana > 0
        or hanzi / (hanzi + hangul) < hanzi_ratio
    ):
        return False
    return True


def main():
    if os.environ.get(INTERNAL_ENV) or not enabled():
        return

    try:
        data = json.load(sys.stdin)
        prompt = data.get("prompt", "")
    except (ValueError, AttributeError):
        return
    if not isinstance(prompt, str):
        return

    min_hanzi = env_number("CHINESE_PROOFREAD_MIN_HANZI", 4, int)
    min_hanzi_mixed = env_number("CHINESE_PROOFREAD_MIN_HANZI_MIXED", 1, int)
    hanzi_ratio = env_number("CHINESE_PROOFREAD_HANZI_RATIO", 0.0, float)
    lang = os.environ.get("CHINESE_PROOFREAD_LANG", "Korean")

    if not is_chinese(prompt, min_hanzi, min_hanzi_mixed, hanzi_ratio):
        return
    start_proofreading(data.get("session_id"), prompt, lang)

    context = (
        "This prompt has Chinese in it. A separate process proofreads it and "
        "shows the result to the user, so do not proofread or correct the "
        "Chinese yourself and do not mention proofreading. Carry out the "
        "request. Only if it can be read in more than one way and the "
        "readings lead to different work, ask which one the user means "
        "before changing anything; when details are merely missing, make a "
        "reasonable choice and do the work. "
        "If the Chinese is only quoted, pasted, or handled as code or data, "
        "answer in the language of the user's own words: add 中 to the list "
        "and translate \"你好\" to English both get a reply in English. "
        "Otherwise, the reply language rule applies: "
        + chat_instruction()
        + " "
        + practicing_note()
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
