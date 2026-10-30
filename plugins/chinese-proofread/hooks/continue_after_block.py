#!/usr/bin/env python3
"""Stop hook: send Claude back to the work after it shows the block.

require_block_first.py asks Claude to write the proofreading block in a reply
with no tool calls, which would end the turn before the request is done. If
that reply has the block, this hook keeps the turn going once. If Claude
skipped the block and finished the work instead, the turn ends as usual.
"""

import json
import sys

from detect_chinese import chat_instruction, set_pending
from require_block_first import BLOCK, CONTINUE, CONTINUE_AGAIN, read_pending

REASON = (
    "The user has seen the proofreading block. Now carry out the user's "
    "request based on the corrected meaning. Do not write the block again. "
    "From here on, "
)


def main():
    try:
        data = json.load(sys.stdin)
        session_id = data.get("session_id")
    except (ValueError, AttributeError):
        return
    prompt_id = data.get("prompt_id")
    if not isinstance(prompt_id, str) or read_pending(session_id) not in (
            CONTINUE + prompt_id, CONTINUE_AGAIN + prompt_id):
        return
    set_pending(session_id, None)
    message = data.get("last_assistant_message")
    if not isinstance(message, str) or BLOCK not in message:
        return
    json.dump({"decision": "block", "reason": REASON + chat_instruction()},
              sys.stdout)


if __name__ == "__main__":
    main()
