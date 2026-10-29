#!/usr/bin/env python3
"""Turn Chinese proofreading on or off, or show the current state.

Run by the toggle skill when it loads. The state is shared by every project
and session, and detect_chinese.py reads it on each prompt.

Usage: toggle.py [on|off|status]   (no argument flips the current state)

Env:
  CHINESE_PROOFREAD_ENABLED  set to 0 to keep proofreading off regardless of
                             the state file
"""

import json
import os
import sys

# Keep in sync with STATE_PATH in hooks/detect_chinese.py.
STATE_PATH = os.path.expanduser("~/.claude/chinese-proofread/state.json")


def read_enabled():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f).get("enabled") is not False
    except (OSError, ValueError, AttributeError):
        return True


def write_enabled(enabled):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"enabled": enabled}, f)
    os.replace(tmp, STATE_PATH)


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
            write_enabled(enabled)
            print("Proofreading turned " + ("on." if enabled else "off."))

        if os.environ.get("CHINESE_PROOFREAD_ENABLED") == "0":
            print(
                "CHINESE_PROOFREAD_ENABLED=0 is set, so proofreading stays off "
                "until that variable is removed."
            )
    print("Reply language: " + os.environ.get("CHINESE_PROOFREAD_LANG", "Korean"))


if __name__ == "__main__":
    main()
