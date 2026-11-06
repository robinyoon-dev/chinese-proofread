#!/usr/bin/env python3
"""Set the language of the explanations, or show it.

Run by the language skill when it loads. The language is saved in STATE_PATH,
so the next prompt uses it without a restart. CHINESE_PROOFREAD_LANG still
comes first when it is set.

Usage: language.py [<language>|reset|status]   (no argument shows it)

Env:
  CHINESE_PROOFREAD_LANG       comes before the saved language
  CHINESE_PROOFREAD_CHAT_LANG  shown as the chat reply language
"""

import os
import sys

import toggle

jobs = toggle.jobs
# A language name, not a sentence: the value goes into the prompts.
MAX_LENGTH = 30
USAGE = "Usage: /chinese-proofread:language [<language>|reset|status]"


def valid(name):
    return (0 < len(name) <= MAX_LENGTH
            and all(ch.isalpha() or ch in " -" for ch in name)
            and name.lower() != "prompt")


def main():
    name = " ".join(" ".join(sys.argv[1:]).split())
    action = name.lower()
    if action in ("", "status"):
        pass
    elif action == "reset":
        jobs.write_state(lang=None)
        print("Explanation language reset to the default.")
    elif valid(name):
        name = name[0].upper() + name[1:]
        jobs.write_state(lang=name)
        print("Explanation language set to " + name + ".")
    else:
        print("Unknown argument: " + name)
        print(USAGE)

    if os.environ.get("CHINESE_PROOFREAD_LANG", "").strip():
        print(
            "CHINESE_PROOFREAD_LANG is set, so it is used instead of the saved "
            "language until that variable is removed."
        )
    lang, chat_lang = toggle.languages()
    print("Explanation language: " + lang)
    print("Chat reply language: " + chat_lang)


if __name__ == "__main__":
    main()
