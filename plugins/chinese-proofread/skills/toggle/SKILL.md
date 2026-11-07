---
name: toggle
description: Turn Chinese input proofreading on or off, or check its current state. Run only when the user types the /chinese-proofread:toggle command.
disable-model-invocation: true
argument-hint: "[on|off|status]"
allowed-tools: Bash(python3:*)
---

# Turn proofreading on or off

Below is the output of the script that changes or checks the state of proofreading.

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toggle.py $ARGUMENTS`

- Report this result to the user in one or two sentences. Write your reply in the language given on the `Chat reply language` line of the output; if that line says `same as the prompt`, use the language the user writes in during this conversation. Do not show the `Explanation language` and `Chat reply language` lines to the user, and do not mention the language of chat replies.
- The state has already changed, so do not call any tools.
- If the output shows usage, tell the user that the available arguments are `on`, `off`, and `status`, and that omitting the argument flips the current state.
