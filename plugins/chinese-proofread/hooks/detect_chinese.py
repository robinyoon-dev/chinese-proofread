#!/usr/bin/env python3
"""UserPromptSubmit hook: ask Claude to proofread prompts written in Chinese.

A prompt counts as Chinese when it has at least MIN_HAN Han characters, no
Japanese kana, and Han characters make up at least HAN_RATIO of the Han plus
Hangul characters. Latin text (code, identifiers) is ignored on purpose.

Env:
  CHINESE_PROOFREAD_LANG       language for explanations (default: Korean)
  CHINESE_PROOFREAD_MIN_HAN    minimum Han characters (default: 4)
  CHINESE_PROOFREAD_HAN_RATIO  minimum Han / (Han + Hangul) (default: 0.5)
"""

import json
import os
import sys


def count(text, *ranges):
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in ranges))


def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except (ValueError, AttributeError):
        return

    min_han = int(os.environ.get("CHINESE_PROOFREAD_MIN_HAN", "4"))
    han_ratio = float(os.environ.get("CHINESE_PROOFREAD_HAN_RATIO", "0.5"))
    lang = os.environ.get("CHINESE_PROOFREAD_LANG", "Korean")

    han = count(prompt, (0x4E00, 0x9FFF), (0x3400, 0x4DBF))
    kana = count(prompt, (0x3040, 0x30FF))
    hangul = count(prompt, (0xAC00, 0xD7A3))

    if han < min_han or kana > 0 or han / (han + hangul) < han_ratio:
        return

    context = (
        "The user wrote this prompt in Chinese. Before doing anything else, "
        "apply the chinese-proofread:proofread skill: proofread the user's own "
        f"Chinese sentences and explain the corrections in {lang}, then carry "
        "out the request based on the corrected meaning."
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
