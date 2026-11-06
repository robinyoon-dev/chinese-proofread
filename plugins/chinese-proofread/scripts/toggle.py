#!/usr/bin/env python3
"""Turn Chinese proofreading on or off, or show the current state.

Run by the toggle skill when it loads. The state is shared by every project
and session, and detect_chinese.py reads it on each prompt.

Usage: toggle.py [on|off|status]   (no argument flips the current state)

Env:
  CHINESE_PROOFREAD_ENABLED    set to 0 to keep proofreading off regardless
                               of the state file
  CHINESE_PROOFREAD_LANG       shown as the explanation language, before
                               the one the language skill saved
  CHINESE_PROOFREAD_CHAT_LANG  shown as the chat reply language
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))

import jobs  # noqa: E402


def read_enabled():
    return jobs.read_state().get("enabled") is not False


def languages():
    """Returns the explanation language and the chat reply language."""
    lang = jobs.language()
    chat_lang = os.environ.get("CHINESE_PROOFREAD_CHAT_LANG", "").strip()
    if not chat_lang:
        chat_lang = lang
    elif chat_lang.lower() == "prompt":
        chat_lang = "same as the prompt"
    return lang, chat_lang


def main():
    args = sys.argv[1:]
    action = args[0].lower() if args else "flip"
    if len(args) > 1 or action not in ("on", "off", "status", "flip"):
        print("Unknown argument: " + " ".join(args))
        print("Usage: /chinese-proofread:toggle [on|off|status]")
    else:
        enabled = read_enabled()
        if action == "status":
            print("Proofreading is " + ("on." if enabled else "off."))
        else:
            enabled = {"on": True, "off": False, "flip": not enabled}[action]
            jobs.write_state(enabled=enabled)
            print("Proofreading turned " + ("on." if enabled else "off."))

        if os.environ.get("CHINESE_PROOFREAD_ENABLED") == "0":
            print(
                "CHINESE_PROOFREAD_ENABLED=0 is set, so proofreading stays off "
                "until that variable is removed."
            )
    lang, chat_lang = languages()
    print("Explanation language: " + lang)
    print("Chat reply language: " + chat_lang)


if __name__ == "__main__":
    main()
