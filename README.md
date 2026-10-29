# chinese-proofread

Claude Code에 중국어로 요청을 입력하면, Claude가 먼저 그 중국어 문장이 자연스러운지 점검하고 교정한 다음에 요청을 수행하도록 만드는 플러그인입니다.

## 동작 방식

1. `UserPromptSubmit` 훅이 입력된 프롬프트를 검사하여 중국어인지 판별합니다.
2. 중국어라고 판별되면, 훅은 `proofread` 스킬을 먼저 적용하라는 지시를 Claude의 컨텍스트에 추가합니다.
3. Claude는 사용자가 쓴 문장을 교정한 결과를 응답의 맨 앞에 보여 주고, 교정된 의미를 기준으로 원래 요청을 수행합니다.

출력 예시는 다음과 같습니다.

```
📝 中文校对
原文: 帮我重构一下这个函数，让他更快
修正: 帮我重构一下这个函数，让它运行得更快
설명:
- 사물을 가리킬 때는 他 대신 它를 씁니다.
- 更快만 쓰면 무엇이 빨라지는지가 불분명하므로 运行得更快로 씁니다.
---
(이후 리팩터링 작업 진행)
```

판별 기준은 다음과 같습니다. 영문 코드와 식별자는 판별에 반영하지 않으므로, 코드가 섞인 중국어 문장도 중국어로 판별됩니다.

- 한자가 4자 이상 있어야 합니다.
- 히라가나나 가타카나가 섞여 있으면 일본어로 보고 제외합니다.
- 한자 수와 한글 수를 더한 값에서 한자가 차지하는 비율이 50% 이상이어야 합니다.

## 설치

Claude Code에서 다음 명령을 실행합니다.

```
/plugin marketplace add <github-owner>/chinese-proofread
/plugin install chinese-proofread@chinese-proofread
```

훅 스크립트를 실행하려면 `python3`가 설치되어 있어야 합니다.

## 설정

환경 변수로 동작을 조정할 수 있습니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `CHINESE_PROOFREAD_LANG` | `Korean` | 교정 설명에 사용할 언어입니다. |
| `CHINESE_PROOFREAD_MIN_HANZI` | `4` | 중국어로 판별하는 데 필요한 최소 한자 수입니다. |
| `CHINESE_PROOFREAD_HANZI_RATIO` | `0.5` | 한자와 한글을 합한 글자 수에서 한자가 차지해야 하는 최소 비율입니다. |

예를 들어 설명을 영어로 받으려면 `~/.claude/settings.json`에 다음 내용을 추가합니다.

```json
{
  "env": {
    "CHINESE_PROOFREAD_LANG": "English"
  }
}
```

## 저장소 구조

```
.claude-plugin/marketplace.json            마켓플레이스 정의
plugins/chinese-proofread/
  .claude-plugin/plugin.json               플러그인 정의
  hooks/hooks.json                         UserPromptSubmit 훅 등록
  hooks/detect_chinese.py                  중국어 판별 스크립트
  skills/proofread/SKILL.md                교정 절차와 출력 형식
```

## 한계

- 한글 없이 한자만으로 쓴 일본어 문장은 중국어로 판별될 수 있습니다.
- 한국어 요청 안에 중국어 문장을 길게 인용하면 중국어 입력으로 판별될 수 있습니다. 이 경우에도 스킬의 규칙에 따라, 사용자가 교정을 요청하지 않은 인용문은 교정하지 않습니다.
