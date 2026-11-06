#!/usr/bin/env python3
"""Print the explanation lines of past corrections for the history skill.

Run by the history skill when it loads. The script counts; the model that reads
this output sorts the lines into error types. Only the explanation lines are
printed: the skill does not need the sentences, and they cost the most.

Usage: history.py [days|all]   (default: the last 7 days)

Env:
  CHINESE_PROOFREAD_HISTORY    0 means new corrections are not being recorded
  CHINESE_PROOFREAD_CHAT_LANG  shown as the chat reply language
  CHINESE_PROOFREAD_LANG       the chat reply language if the above is unset,
                               before the one the language skill saved
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))

import jobs  # noqa: E402
import toggle  # noqa: E402

DEFAULT_DAYS = 7
# Claude Code replaces skill output it finds too long with a short preview and
# a file path: 24KB came through whole and 33KB did not (2.1.316).
MAX_OUTPUT_BYTES = 24000


def month_files(since):
    """Returns the monthly files that can hold records from since onwards, in
    order. Each name is the month it was written in, so the rest are skipped."""
    try:
        names = sorted(os.listdir(jobs.HISTORY_DIR))
    except OSError:
        return []
    first = since.strftime("%Y-%m") + ".jsonl" if since else ""
    return [os.path.join(jobs.HISTORY_DIR, n) for n in names
            if n.endswith(".jsonl") and n >= first]


def read_records(since):
    """Returns the records from since onwards, oldest first, and how many lines
    could not be used."""
    records, skipped = [], 0
    for path in month_files(since):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
                time = datetime.datetime.fromisoformat(record["time"])
                block = record["block"]
                if record["v"] != jobs.HISTORY_VERSION or not isinstance(block, str):
                    raise ValueError
                if since is None or time >= since:
                    records.append(block)
            except (ValueError, KeyError, TypeError):
                skipped += 1
    return records, skipped


def explanations(block):
    """Returns the bullet lines of a block. Bullets are the one part of the
    format that does not depend on the explanation language."""
    lines = (line.strip() for line in block.splitlines())
    return [line[2:].strip() for line in lines if line.startswith("- ")]


def newest_lines(records):
    """Returns the explanation lines of as many of the newest records as fit
    in MAX_OUTPUT_BYTES, oldest first, and how many records that was."""
    kept, size = [], 0
    for block in reversed(records):
        lines = explanations(block)
        # The room for the number in front of each line is a rough guess.
        size += sum(len(line.encode("utf-8")) + 8 for line in lines)
        if size > MAX_OUTPUT_BYTES:
            break
        kept.append(lines)
    return [line for lines in reversed(kept) for line in lines], len(kept)


def parse_days(args):
    """Returns the number of days, None for all, or raises ValueError."""
    if not args:
        return DEFAULT_DAYS
    if len(args) == 1 and args[0].lower() == "all":
        return None
    days = int(args[0]) if len(args) == 1 else 0
    if days < 1:
        raise ValueError
    return days


def main():
    chat_lang = toggle.languages()[1]
    try:
        days = parse_days(sys.argv[1:])
        now = datetime.datetime.now().astimezone()
        # Raises OverflowError if the days reach past the first year.
        since = None if days is None else now - datetime.timedelta(days=days)
    except (ValueError, OverflowError):
        print("Unknown argument: " + " ".join(sys.argv[1:]))
        print("Usage: /chinese-proofread:history [days|all]")
        print("Chat reply language: " + chat_lang)
        return

    records, skipped = read_records(since)
    lines, read = newest_lines(records)

    print("Period: " + ("all records" if days is None else f"last {days} days"))
    print(f"Corrections in the period: {len(records)}")
    print(f"Corrections read: {read}")
    print(f"Explanation lines: {len(lines)}")
    if skipped:
        print(f"Unreadable records skipped: {skipped}")
    if os.environ.get("CHINESE_PROOFREAD_HISTORY") == "0":
        print("CHINESE_PROOFREAD_HISTORY=0 is set, so new corrections are not recorded.")
    print("Chat reply language: " + chat_lang)
    if lines:
        print()
        print("Explanation lines:")
    for number, line in enumerate(lines, 1):
        print(f"{number}. {line}")


if __name__ == "__main__":
    main()
