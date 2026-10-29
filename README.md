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
- 사물을 가리킬 때는 他(tā) 대신 它(tā)를 씁니다.
- 更快(gèng kuài)만 쓰면 무엇이 빨라지는지가 불분명하므로 运行得更快(yùnxíng de gèng kuài)로 씁니다.
---
(이후 리팩터링 작업 진행)
```

설명에서 언급하는 중국어 단어에는 성조 부호로 표기한 한어병음을 덧붙입니다. `原文`과 `修正` 줄에는 두 문장을 쉽게 비교할 수 있도록 병음을 붙이지 않습니다.

중국어로 어떻게 말하는지 모르는 단어를 영어나 한국어로 대신 써도 됩니다. Claude는 그 단어를 중국어로 어떻게 말하는지 먼저 알려 주고, 그다음에 요청을 수행합니다.

```
📝 中文校对
原文: 跑local server.
修正: 把本地服务器跑起来。
설명:
- local server는 중국어로 本地服务器(běndì fúwùqì)라고 합니다. 줄여서 本地服务(běndì fúwù)라고도 합니다.
- 跑(pǎo)는 프로그램을 실행한다는 뜻으로 개발자들이 구어에서 흔히 씁니다. 실행해 달라고 지시할 때는 把(bǎ) 구문과 跑起来(pǎo qǐlái)를 함께 쓰면 더 자연스럽습니다.
---
(이후 로컬 서버 실행)
```

`bug`, `commit`처럼 중국어권 개발자도 영어를 그대로 쓰는 단어는 바꾸지 않습니다.

판별 기준은 다음과 같습니다. 영문 코드와 식별자는 판별에 반영하지 않으므로, 코드가 섞인 중국어 문장도 중국어로 판별됩니다.

- 한자가 4자 이상 있어야 합니다. 다만 영문자가 섞여 있고 한글이 없다면 한자가 1자만 있어도 됩니다. `跑local server.`처럼 모르는 단어를 영어로 대신 쓴 짧은 문장도 교정하기 위해서입니다.
- 히라가나나 가타카나가 섞여 있으면 일본어로 보고 제외합니다.
- 한자 수와 한글 수를 더한 값에서 한자가 차지하는 비율이 50% 이상이어야 합니다.

## 설치

Claude Code에서 다음 명령을 실행합니다.

```
/plugin marketplace add <github-owner>/chinese-proofread
/plugin install chinese-proofread@chinese-proofread
```

훅 스크립트를 실행하려면 `python3`가 설치되어 있어야 합니다.

## 켜고 끄기

중국어 학습과 관계없이 중국어 자료를 다루는 동안에는 교정 기능을 잠시 끌 수 있습니다. 설치 직후에는 기능이 켜져 있습니다.

```
/chinese-proofread:toggle off      교정 기능을 끕니다.
/chinese-proofread:toggle on       교정 기능을 다시 켭니다.
/chinese-proofread:toggle status   현재 상태를 확인합니다.
/chinese-proofread:toggle          현재 상태를 반대로 바꿉니다.
```

- 변경한 상태는 다음 입력부터 바로 반영되며, Claude Code를 다시 시작할 필요가 없습니다.
- 상태는 `~/.claude/chinese-proofread/state.json`에 저장되므로, 모든 프로젝트와 세션에 함께 적용되고 Claude Code를 다시 시작해도 유지됩니다.
- 이 명령은 사용자가 직접 입력할 때만 실행됩니다. Claude가 스스로 판단하여 기능을 끄거나 켜지는 않습니다.

### 특정 프로젝트에서 항상 끄기

중국어 문서를 다루는 저장소처럼 특정 프로젝트에서는 교정 기능을 항상 끄고 싶다면, 그 프로젝트의 `.claude/settings.json`에 다음 내용을 추가합니다.

```json
{
  "env": {
    "CHINESE_PROOFREAD_ENABLED": "0"
  }
}
```

- 이 환경 변수를 설정하면 `/chinese-proofread:toggle on`으로 켜 둔 상태와 관계없이 기능이 꺼집니다. `status`를 실행하면 환경 변수 때문에 꺼져 있다는 사실도 함께 알려 줍니다.
- 환경 변수를 추가하거나 바꾼 뒤에는 Claude Code를 다시 시작해야 반영됩니다.
- 모든 프로젝트에서 항상 끄려면 같은 내용을 `~/.claude/settings.json`에 추가합니다. 다만 잠시 끄는 용도라면 환경 변수보다 `/chinese-proofread:toggle off`가 더 편리합니다.

## 설정

환경 변수로 동작을 조정할 수 있습니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `CHINESE_PROOFREAD_ENABLED` | (없음) | `0`으로 설정하면 `toggle` 명령으로 저장한 상태와 관계없이 교정 기능을 끕니다. |
| `CHINESE_PROOFREAD_LANG` | `Korean` | 교정 설명에 사용할 언어입니다. |
| `CHINESE_PROOFREAD_MIN_HANZI` | `4` | 중국어로 판별하는 데 필요한 최소 한자 수입니다. |
| `CHINESE_PROOFREAD_MIN_HANZI_MIXED` | `1` | 영문자가 섞여 있고 한글이 없는 입력에 적용하는 최소 한자 수입니다. `CHINESE_PROOFREAD_MIN_HANZI`보다 크게 설정하면 `CHINESE_PROOFREAD_MIN_HANZI` 값을 씁니다. |
| `CHINESE_PROOFREAD_HANZI_RATIO` | `0.5` | 한자와 한글을 합한 글자 수에서 한자가 차지해야 하는 최소 비율입니다. |

숫자를 받는 설정에 숫자가 아닌 값을 넣으면 그 설정은 기본값으로 동작합니다.

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
  scripts/toggle.py                        교정 기능의 상태를 바꾸는 스크립트
  skills/proofread/SKILL.md                교정 절차와 출력 형식
  skills/toggle/SKILL.md                   교정 기능을 켜고 끄는 명령
tests/test_detect_chinese.py               중국어 판별 스크립트의 테스트
.github/workflows/test.yml                 테스트를 실행하는 GitHub Actions 워크플로
```

## 테스트

판별 스크립트를 수정했다면 커밋하기 전에 저장소 루트에서 다음 명령을 실행합니다. 외부 패키지는 필요하지 않습니다.

```
python3 -m unittest discover -s tests
```

`main` 브랜치에 push하거나 pull request를 열면 GitHub Actions가 Python 3.9와 3.14에서 같은 테스트를 실행합니다.

## 한계

- 한글 없이 한자만으로 쓴 일본어 문장은 중국어로 판별될 수 있습니다.
- 설명에 덧붙이는 한어병음은 모델이 생성하므로, 다음자(多音字)나 성조 변화가 있는 단어에서는 성조가 틀릴 수 있습니다.
- 모르는 단어를 한국어로 대신 쓴 문장은 한자가 적으면 중국어로 판별되지 않습니다. 예를 들어 `跑로컬 서버`는 한자가 1자이고 한글이 4자이므로 비율 조건을 통과하지 못합니다. `帮我把로컬 서버跑起来`처럼 한자가 더 많은 문장은 판별됩니다.
- 영어 요청 안에 한자가 한 글자라도 있으면 중국어 입력으로 판별될 수 있습니다. 이 경우에는 스킬이 교정할 대상이 없다고 판단하고 교정 블록을 출력하지 않습니다.
- 한국어 요청 안에 중국어 문장을 길게 인용하면 중국어 입력으로 판별될 수 있습니다. 이 경우에도 스킬의 규칙에 따라, 사용자가 교정을 요청하지 않은 인용문은 교정하지 않습니다.
