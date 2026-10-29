---
name: toggle
description: 중국어 입력 교정 기능을 켜거나 끄고, 현재 상태를 확인한다. 사용자가 /chinese-proofread:toggle 명령을 직접 입력했을 때만 실행한다.
disable-model-invocation: true
argument-hint: "[on|off|status]"
allowed-tools: Bash(python3:*)
---

# 교정 기능 켜고 끄기

아래는 교정 기능의 상태를 바꾸거나 확인하는 스크립트를 실행한 결과입니다.

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toggle.py $ARGUMENTS`

- 이 결과를 사용자에게 한두 문장으로 전달합니다. 전달할 때는 결과의 `Reply language` 줄에 적힌 언어를 쓰고, 그 줄은 사용자에게 보여 주지 않습니다.
- 상태는 이미 바뀌었으므로 도구를 호출하지 않습니다.
- 결과에 사용법이 출력되었다면, 사용할 수 있는 인자가 `on`, `off`, `status`이고 인자를 생략하면 상태가 반대로 바뀐다는 점을 알려 줍니다.
