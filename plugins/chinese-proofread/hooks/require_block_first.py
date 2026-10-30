#!/usr/bin/env python3
"""PreToolUse hook: make Claude show the proofreading block before the work.

detect_chinese.py leaves a pending file with the prompt id when it asks for
proofreading. While that file is there, the first tool call other than Skill
is denied if no reply text since the prompt has the block. Sonnet tends to
write the corrections only in its thinking and go straight to the tools, so
the user would not see them until the work is done.

After one denial Sonnet often notes in its thinking that it has proofread
and makes the same call again, so a call is denied up to twice. The second
denial says that thinking does not count; after it, calls are allowed.

Sonnet does write the block in a reply that has no tool calls, so the denial
asks for exactly that, and continue_after_block.py then sends Claude back to
the work instead of letting the turn end there.

The reply text reaches the transcript a few dozen ms after this hook starts,
so the hook first waits for its own tool_use to show up there. If it does not
show up in time, the call is allowed and the next call checks again.
"""

import json
import sys
import time

from detect_chinese import pending_path, set_pending

BLOCK = "📝 中文校对"
# Prefixes of the pending file after the first and the second denial; see
# continue_after_block.py.
CONTINUE = "continue:"
CONTINUE_AGAIN = "continue2:"
WAIT_SECONDS = 2.0
WRITE_BLOCK = (
    "Your next message must have no tool calls: write only the block from "
    "the chinese-proofread:proofread skill as text (the corrections, or the "
    "✅ line if the Chinese is natural). You will continue the work after "
    "that. Only if the user wrote no Chinese of their own, make this call "
    "again without mentioning proofreading."
)
REASON = (
    "Not run yet: none of the text you have written for this prompt has the "
    "📝 中文校对 block, and your thinking is hidden from the user. Correcting "
    "the Chinese in your thinking, or noting there that you have proofread "
    "it, does not show it to the user. " + WRITE_BLOCK
)
REASON_AGAIN = (
    "Still not run: you made the call again without writing the 📝 中文校对 "
    "block as text. The user still has not seen any correction, because "
    "proofreading in your thinking is not shown. " + WRITE_BLOCK
)


def read_pending(session_id):
    path = pending_path(session_id)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def reply_texts(transcript_path, prompt_id, tool_use_id):
    """Text blocks Claude wrote since the prompt, or None if tool_use_id has
    not reached the transcript yet."""
    texts = []
    found = False
    started = False
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, TypeError, ValueError):
        return None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "user" and entry.get("promptId") == prompt_id:
            started = True
        if not started or entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(block.get("text") or "")
            elif block.get("type") == "tool_use" and block.get("id") == tool_use_id:
                found = True
    return texts if found else None


def main():
    try:
        data = json.load(sys.stdin)
        session_id = data.get("session_id")
    except (ValueError, AttributeError):
        return
    if data.get("tool_name") == "Skill":
        return
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        return
    pending = read_pending(session_id)
    if pending == prompt_id:
        reason, next_pending = REASON, CONTINUE + prompt_id
    elif pending == CONTINUE + prompt_id:
        reason, next_pending = REASON_AGAIN, CONTINUE_AGAIN + prompt_id
    else:
        return

    deadline = time.time() + WAIT_SECONDS
    texts = reply_texts(data.get("transcript_path"), prompt_id, data.get("tool_use_id"))
    while texts is None and time.time() < deadline:
        time.sleep(0.02)
        texts = reply_texts(data.get("transcript_path"), prompt_id, data.get("tool_use_id"))
    if texts is None:
        return

    if any(BLOCK in text for text in texts):
        set_pending(session_id, None)
        return
    # Deny at most twice, so a prompt with nothing to proofread costs two
    # retries at most.
    set_pending(session_id, next_pending)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
