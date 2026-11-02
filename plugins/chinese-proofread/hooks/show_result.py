#!/usr/bin/env python3
"""PostToolUse and Stop hook: show finished proofreading to the user, once.

A hook's systemMessage is the only output the user sees while the work goes
on, and hooks run only around tool calls and at the end of the turn, so a
result waits for the next of those. PreToolUse is not used: its message shows
up only when the tool has finished, and is lost if the user declines the call.

At the end of the turn this hook waits for a running job, because a short
answer usually finishes before the proofreading. A job that takes longer is
shown in the next turn. An interrupted turn runs no Stop hook; the same applies.

Prints every finished job, so a result left over from an earlier turn is shown
first. Parallel tool calls run this hook at the same time, so a job belongs to
the process that manages to rename it.

The reply language is an instruction Claude does not always follow, however it
is worded, so at the end of the turn this hook also reads the final reply. If
it is mostly Chinese the turn goes on once to rewrite it. Removing the expected
language first means a turn is rewritten at most once.
"""

import json
import os
import re
import sys
import time
import unicodedata

from jobs import REPLY_FILE, STALE_SECONDS, jobs, session_dir

# Keep below the Stop timeout in hooks.json.
STOP_WAIT_SECONDS = 20
FAILED = "⚠️ 中文校对: proofreading failed ({})"
MIN_REPLY_HANZI = 10
REWRITE = (
    "Your last reply is in Chinese, but this user reads replies in {language}. "
    "Write that reply again in {language}, without tools and without "
    "mentioning this note. Leave out any version in Chinese. If the user asked "
    "for that text in Chinese, say nothing more."
)
# Claude Code greys out hook messages, and a hook cannot learn the terminal's
# background, so one fixed pair must read on both themes. 22 lifts the dim that
# dark-ansi adds, and 231 is white even where a palette redefines 97.
STYLE = "\x1b[22;38;5;231;48;5;240m"
RESET = "\x1b[0m"
# Claude Code indents a hook message by 5 columns. One more keeps a row on one
# line where the terminal draws an emoji wider than this code counts it.
MARGIN = 6
MIN_WIDTH = 20


def char_width(char):
    if char == "\ufe0f":
        return 1  # Turns the character before it into a wide emoji.
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


def text_width(text):
    return sum(char_width(char) for char in text)


def block_width(lines):
    """COLUMNS is set by Claude Code and follows the window size."""
    try:
        width = int(os.environ["COLUMNS"]) - MARGIN
    except (KeyError, ValueError):
        width = 0
    if width < MIN_WIDTH:
        return max(text_width(line) for line in lines)
    return width


def wrapped(line, width):
    # A row that Claude Code wraps ends short of the others, so it is wrapped
    # here. Chinese has no spaces to break at, so any character may end a row;
    # a space counts only past the middle, or a label such as "原文:" would
    # take up a row of its own.
    rows = []
    row = ""
    for char in line:
        if text_width(row) + char_width(char) > width:
            head, _, tail = row.rpartition(" ")
            if text_width(head) * 2 < width:
                head, tail = row, ""
            rows.append(head)
            row = tail
        row += char
    rows.append(row)
    return rows


def styled(text):
    # Claude Code keeps escape codes under NO_COLOR, so it is honoured here.
    if os.environ.get("NO_COLOR"):
        return text
    lines = text.split("\n")
    width = block_width(lines)
    # The blank line leaves "Stop says: " alone on the first line, so that
    # every row of the block starts at the same column.
    rows = [""]
    for line in lines:
        if not line:
            rows.append("")
            continue
        # A background ends with the text, so spaces fill out the row, as
        # Claude Code does for the user's own messages.
        for row in wrapped(line, width):
            padding = " " * (width - text_width(row))
            rows.append(f"{STYLE}{row}{padding}{RESET}")
    return "\n".join(rows)


def claim(path):
    mine = f"{path}.{os.getpid()}"
    try:
        os.rename(path, mine)
    except OSError:
        return None
    return mine


def read_result(path):
    mine = claim(path)
    if mine is None:
        return None
    try:
        with open(mine, encoding="utf-8") as f:
            result = json.load(f)
        os.remove(mine)
    except (OSError, ValueError):
        return FAILED.format("unreadable result")
    if isinstance(result, dict) and isinstance(result.get("block"), str):
        return result["block"]
    reason = result.get("error") if isinstance(result, dict) else None
    return FAILED.format(reason or "unreadable result")


def dead(path):
    try:
        return time.time() - os.path.getmtime(path) > STALE_SECONDS
    except OSError:
        return False


def read_dead_job(path):
    mine = claim(path)
    if mine is None:
        return None
    try:
        os.remove(mine)
    except OSError:
        pass
    return FAILED.format("no result")


def wait_for_jobs(folder):
    deadline = time.time() + STOP_WAIT_SECONDS
    while time.time() < deadline:
        if all(dead(path) for path in jobs(folder, ".running")):
            return
        time.sleep(0.1)


def mostly_chinese(reply):
    # Code and quoted text in backticks may be in any language. The whole reply
    # counts, because a long reply may quote a Chinese sentence; a word stands
    # for a Latin run so that an English gloss does not hide a Chinese reply.
    # Kana rule out Chinese, as in is_chinese().
    text = re.sub(r"```.*?```|`[^`\n]*`", "", reply, flags=re.S)
    if re.search(r"[\u3040-\u30ff]", text):
        return False
    hanzi = len(re.findall(r"[\u4e00-\u9fff]", text))
    others = len(re.findall(r"[\uac00-\ud7a3]|[A-Za-z]+", text))
    return hanzi >= MIN_REPLY_HANZI and hanzi > others


def reply_to_rewrite(folder, data):
    """Returns the expected language if the final reply came out in Chinese."""
    mine = claim(os.path.join(folder, REPLY_FILE))
    if mine is None:
        return None
    try:
        with open(mine, encoding="utf-8") as f:
            language = json.load(f)["language"]
        os.remove(mine)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    reply = data.get("last_assistant_message")
    if isinstance(reply, str) and mostly_chinese(reply):
        return language
    return None


def main():
    try:
        data = json.load(sys.stdin)
        folder = session_dir(data.get("session_id"))
    except (ValueError, AttributeError):
        return
    if folder is None:
        return
    if data.get("hook_event_name") == "Stop":
        wait_for_jobs(folder)

    messages = [read_result(path) for path in jobs(folder, ".json")]
    messages += [read_dead_job(path) for path in jobs(folder, ".running")
                 if dead(path)]
    messages = [message for message in messages if message]
    output = {}
    if messages:
        output["systemMessage"] = styled("\n\n".join(messages))
    if data.get("hook_event_name") == "Stop":
        language = reply_to_rewrite(folder, data)
        if language:
            output["decision"] = "block"
            output["reason"] = REWRITE.format(language=language)
    if output:
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
