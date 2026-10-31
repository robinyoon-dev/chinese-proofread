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
"""

import json
import os
import sys
import time

from jobs import BLOCK, STALE_SECONDS, jobs, session_dir

# Keep below the Stop timeout in hooks.json.
STOP_WAIT_SECONDS = 20
FAILED = "⚠️ 中文校对: proofreading failed ({})"


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
    if messages:
        json.dump({"systemMessage": "\n\n".join(messages)}, sys.stdout)


if __name__ == "__main__":
    main()
