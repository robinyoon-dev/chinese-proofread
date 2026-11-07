---
name: language
description: Change or check the language used for proofreading explanations. Run only when the user types the /chinese-proofread:language command.
disable-model-invocation: true
argument-hint: "[language|reset|status]"
allowed-tools: Bash(python3:*)
---

# Change the explanation language

Below is the output of the script that changes or checks the language of proofreading explanations.

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/language.py $ARGUMENTS`

- Report this result to the user in one or two sentences. Write your reply in the language given on the `Chat reply language` line of the output; if that line says `same as the prompt`, use the language the user writes in during this conversation. Tell the user what the current explanation language is, but do not show the `Explanation language` and `Chat reply language` lines as they are. Do not mention the language of chat replies.
- The script has already run, so do not call any tools.
- Only if the output has a `set to` line or a `reset` line, add that the new language applies from the next input. If the user only checked the current language, just tell them the current language.
- If there is a `CHINESE_PROOFREAD_LANG is set` line, tell the user that an environment variable is set, so its language is used instead of the saved one.
- Only if the output has a `Usage:` line, explain the usage: the argument is a language name such as `English` or `Korean`, `reset` returns to the default (English), and omitting the argument or using `status` shows the current language.
