---
name: language
description: 교정 설명에 쓸 언어를 바꾸거나 현재 언어를 확인한다. 사용자가 /chinese-proofread:language 명령을 직접 입력했을 때만 실행한다.
disable-model-invocation: true
argument-hint: "[language|reset|status]"
allowed-tools: Bash(python3:*)
---

# 설명 언어 바꾸기

아래는 교정 설명의 언어를 바꾸거나 확인하는 스크립트를 실행한 결과입니다.

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/language.py $ARGUMENTS`

- 이 결과를 사용자에게 한두 문장으로 전달합니다. 전달할 때는 결과의 `Chat reply language` 줄에 적힌 언어를 쓰고, 그 줄이 `same as the prompt`라면 사용자가 이 대화에서 쓰는 언어를 씁니다. 지금 설명 언어가 무엇인지는 알려 주되, `Explanation language` 줄과 `Chat reply language` 줄을 그대로 보여 주지는 않습니다. 대화 응답의 언어는 언급하지 않습니다.
- 스크립트가 이미 실행되었으므로 도구를 호출하지 않습니다.
- 결과에 `set to` 줄이나 `reset` 줄이 있을 때만, 바뀐 언어가 다음 입력부터 적용된다고 덧붙입니다. 현재 언어만 확인한 경우에는 현재 언어만 알립니다.
- `CHINESE_PROOFREAD_LANG is set` 줄이 있으면, 환경 변수가 설정되어 있어 저장한 언어 대신 환경 변수의 언어를 쓴다고 알립니다.
- 결과에 `Usage:` 줄이 있을 때만 사용법을 알려 줍니다. 이때는 인자로 `English`나 `Korean` 같은 언어 이름을 쓰고, `reset`은 기본값인 English로 되돌리며, 인자를 생략하거나 `status`를 쓰면 현재 언어를 보여 준다는 점을 알려 줍니다.
