#!/usr/bin/env python3
"""UserPromptSubmit hook: ask Claude to proofread prompts written in Chinese.

A prompt counts as Chinese when it has at least MIN_HANZI hanzi, no Japanese
kana, and hanzi make up at least HANZI_RATIO of the hanzi plus Hangul
characters. Latin text (code, identifiers) is ignored on purpose.

A prompt with Latin letters or Hangul needs only MIN_HANZI_MIXED hanzi, so
short prompts like "跑local server" and Chinese words mixed into Korean or
English sentences are still proofread. The skill decides whether the hanzi
were written by the user or quoted. HANZI_RATIO is 0 by default; raising it
skips Korean sentences with only a few hanzi.

Does nothing while proofreading is turned off with the toggle skill.

For a Chinese prompt it also leaves a pending file with the prompt id, so
require_block_first.py can check that the block is shown before the work.

Env:
  CHINESE_PROOFREAD_ENABLED      set to 0 to keep proofreading off
  CHINESE_PROOFREAD_LANG         language for explanations (default: Korean)
  CHINESE_PROOFREAD_MIN_HANZI    minimum hanzi (default: 4)
  CHINESE_PROOFREAD_MIN_HANZI_MIXED
                                 minimum hanzi with Latin letters or Hangul
                                 (default: 1)
  CHINESE_PROOFREAD_HANZI_RATIO  minimum hanzi / (hanzi + Hangul) (default: 0)
"""

import json
import os
import sys

# Keep in sync with STATE_PATH in scripts/toggle.py.
STATE_PATH = os.path.expanduser("~/.claude/chinese-proofread/state.json")
PENDING_DIR = os.path.expanduser("~/.claude/chinese-proofread/pending")


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


def pending_path(session_id):
    # Session ids are UUIDs; anything else could point outside PENDING_DIR.
    if not isinstance(session_id, str) or not session_id.replace("-", "").isalnum():
        return None
    return os.path.join(PENDING_DIR, session_id)


def set_pending(session_id, prompt_id):
    path = pending_path(session_id)
    if path is None:
        return
    try:
        if isinstance(prompt_id, str):
            os.makedirs(PENDING_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(prompt_id)
        else:
            os.remove(path)
    except OSError:
        pass


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
    if not enabled():
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
        set_pending(data.get("session_id"), None)
        return
    set_pending(data.get("session_id"), data.get("prompt_id"))

    context = (
        "The user wrote this prompt in Chinese. Before doing anything else, "
        "apply the chinese-proofread:proofread skill: proofread the user's own "
        "Chinese sentences, including any English or Korean words they used "
        "in place of Chinese words, and the Chinese words they mixed into "
        "Korean or English sentences (even ones that look like Korean "
        f"hanja words), and explain the corrections in {lang}, "
        "then carry out the request based on the corrected meaning. "
        "If the user wrote no Chinese of their own, skip proofreading "
        "without mentioning it."
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
