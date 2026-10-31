#!/usr/bin/env python3
"""Stop hook: send Claude back to the work after it shows the block.

require_block_first.py asks Claude to write the proofreading block in a reply
with no tool calls, which would end the turn before the request is done. If
that reply has the block, this hook keeps the turn going once.

A denied Claude can also give up without the block and report that a hook is
blocking it, which Opus did, so a turn that ends after a denial is kept going
once as well, with the gate lifted. If Claude got past the denials and
finished the work, the pending file is gone and the turn ends as usual.
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
GATE_LIFTED = (
    "Your tool calls are no longer blocked. Carry out the user's request "
    "now, based on the corrected meaning, without mentioning the hook. If "
    "the request is already done, stop without repeating it. From here on, "
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
    has_block = isinstance(message, str) and BLOCK in message
    reason = REASON if has_block else GATE_LIFTED
    json.dump({"decision": "block", "reason": reason + chat_instruction()},
              sys.stdout)


if __name__ == "__main__":
    main()
