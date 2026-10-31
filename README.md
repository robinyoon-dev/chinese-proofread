# chinese-proofread

Claude Code에 중국어로 요청을 입력하면, 별도의 교정 에이전트가 작업과 동시에 그 문장이 자연스러운지 점검하여 결과를 화면에 보여 주는 플러그인입니다. 작업은 Claude가 평소처럼 진행합니다.

Claude Code로 개발하면서 중국어를 배우는 한국어 사용자를 대상으로 만들었으므로, 교정 설명과 답변은 기본적으로 한국어로 출력합니다. 두 언어는 [설정](#설정)에서 각각 바꿀 수 있습니다.

케이스 40개를 3회씩 실행하여 정규식으로 채점한 평가에서 Sonnet의 오류 검출은 45/45, 과잉 교정 없음은 144/144였습니다. 교정 설명의 내용은 검증하지 않았습니다. 자세한 내용은 [설계와 평가](docs/design-and-evaluation.md)에 정리했습니다.

<img src="docs/images/readme-hero.png" width="880" alt="중국어 요청 让这个function跑的更快가 Claude의 요청 수행과 교정 에이전트의 문장 교정으로 나뉘어 동시에 진행되고, Claude가 작업을 이어 가는 도중에 让这个函数跑得更快로 고친 교정 결과와 설명이 표시되는 흐름">

## 시작하기

### 필요한 것

- `python3`: 훅 스크립트를 실행합니다.
- 로그인된 `claude` 명령: 교정을 실행합니다.

중국어로 판별된 입력마다 작업과 별도로 Sonnet 호출이 한 번 듭니다. 평가에서 1회당 평균 약 $0.005였고, 프롬프트 캐시가 없으면 약 $0.012까지 듭니다.

### 설치

Claude Code에서 다음 두 명령을 한 줄씩 실행합니다. 두 줄을 한 번에 붙여 넣으면 제대로 실행되지 않습니다.

```
/plugin marketplace add robinyoon-dev/chinese-proofread
```

```
/plugin install chinese-proofread@chinese-proofread
```

<details>
<summary>업데이트와 삭제</summary>

터미널에서 다음 명령을 실행하여 업데이트합니다. 바뀐 내용은 Claude Code를 다시 시작해야 적용됩니다.

```
claude plugin marketplace update chinese-proofread
claude plugin update chinese-proofread@chinese-proofread
```

터미널에서 다음 명령을 실행하여 삭제합니다. 잠시 끄는 용도라면 [켜고 끄기](#켜고-끄기)의 명령이 더 편리합니다.

```
claude plugin uninstall chinese-proofread@chinese-proofread
claude plugin marketplace remove chinese-proofread
```

</details>

## 교정 결과 예시

위 이미지에 나온 요청을 입력하면 다음과 같이 출력됩니다. 설명에서 언급하는 중국어 단어에는 성조 부호로 표기한 한어병음을 덧붙이고, 두 문장을 비교하는 `原文`과 `修正` 줄에는 붙이지 않습니다.

```
📝 中文校对
原文: 让这个function跑的更快
修正: 让这个函数跑得更快
설명:
- function은 중국어로 函数(hánshù)라고 합니다.
- 동사 뒤에 정도를 나타내는 보어를 붙일 때는 的(de) 대신 得(de)를 씁니다.
---
```

한국어나 영어 문장에 중국어 단어를 섞어 쓰면, 고친 단어만 알려 줍니다. 고칠 단어가 없으면 `✅` 줄 한 줄만 출력합니다.

```
📝 中文校对
- 例外 → 异常(yìcháng): 프로그래밍에서 말하는 예외는 중국어로 异常이라고 합니다. 例外(lìwài)는 규칙에서 벗어난 경우를 뜻합니다.
---
```

- 교정은 보통 몇 초 안에 끝나며, 결과는 도구 호출이 끝날 때나 답변이 끝날 때 표시됩니다. 따라서 짧은 요청에서는 답변 뒤에, 긴 작업에서는 작업 도중에 나옵니다.
- 블록 앞에 붙는 `Stop says:`나 `PostToolUse:Bash says:`는 어느 훅이 표시했는지를 나타내는 Claude Code의 문구입니다.
- Claude는 사용자가 쓴 원문을 기준으로 작업하며 교정 결과를 보지 못하므로, 교정 내용에 대해 Claude에게 물어도 답할 수 없습니다.

## 무엇을 교정하나요

| 교정합니다 | 교정하지 않습니다 |
|---|---|
| 직접 쓴 중국어 문장 | 따옴표나 백틱으로 감싼 중국어 |
| 한국어나 영어 문장에 섞어 쓴 중국어 단어 | 번역해 달라고 한 중국어 |
| 중국어 문장에서 `function`처럼 영어나 한국어로 대신 쓴 단어 | 붙여 넣은 로그와 파일 안의 중국어 |

- 목적이 중국어 학습이므로, `fix`, `commit`, `edge case`처럼 영어로도 흔히 쓰는 단어라도 중국어 표현이 있다면 알려 줍니다.
- 코드, 명령어, 파일 경로, 식별자, 약어(`API`, `JSON`, `PR`), 제품이나 서비스의 이름, 브랜치 이름, `bug`처럼 영어로 굳어진 단어는 바꾸지 않습니다.
- 한국어 문장에 쓴 한자는 중국어를 시도한 것으로 보고 교정합니다. 예를 들어 `中國語`를 쓰면 중국어로는 `中文`이라고 한다고 알려 줍니다. 중국어를 공부하지 않으면 이런 교정이 필요 없을 수 있으므로, [설정](#설정)의 `CHINESE_PROOFREAD_HANZI_RATIO`로 줄일 수 있습니다.

## 켜고 끄기

설치 직후에는 교정 기능이 켜져 있습니다. 중국어 자료를 다루는 동안에는 다음 명령으로 잠시 끌 수 있습니다.

```
/chinese-proofread:toggle off      교정 기능을 끕니다.
/chinese-proofread:toggle on       교정 기능을 다시 켭니다.
/chinese-proofread:toggle status   현재 상태를 확인합니다.
/chinese-proofread:toggle          현재 상태를 반대로 바꿉니다.
```

변경한 상태는 다음 입력부터 바로 반영되며, 모든 프로젝트와 세션에 함께 적용됩니다. 특정 프로젝트에서만 항상 끄는 방법은 [특정 프로젝트에서 항상 끄기](docs/configuration.md#특정-프로젝트에서-항상-끄기)에서 설명합니다.

## 설정

자주 쓰는 환경 변수는 다음과 같습니다. 전체 목록은 [환경 변수](docs/configuration.md#환경-변수)에서, 언어가 적용되는 범위는 [답변 언어](docs/configuration.md#답변-언어)에서 설명합니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `CHINESE_PROOFREAD_LANG` | `Korean` | 교정 설명에 사용할 언어입니다. |
| `CHINESE_PROOFREAD_CHAT_LANG` | (없음) | 대화 응답에 사용할 언어입니다. 지정하지 않으면 교정 설명과 같은 언어를 쓰고, `prompt`로 설정하면 요청을 쓴 언어를 씁니다. |
| `CHINESE_PROOFREAD_HANZI_RATIO` | `0` | `0.5`로 설정하면 한자가 적은 한국어 문장을 교정 대상에서 뺍니다. |

예를 들어 설명을 영어로 받으려면 `~/.claude/settings.json`에 다음 내용을 추가하고 Claude Code를 다시 시작합니다.

```json
{
  "env": {
    "CHINESE_PROOFREAD_LANG": "English"
  }
}
```

## 알아 둘 점

- 교정 설명과 한어병음은 모델이 생성하므로 틀릴 수 있습니다. 특히 다음자(多音字)나 성조 변화가 있는 단어에서는 성조가 틀릴 수 있습니다.
- 교정 에이전트는 프롬프트만 보므로, 이전 대화나 `@파일`의 내용을 알지 못합니다.
- 교정 결과가 작업 전에 나온다고 보장하지 못합니다. 긴 명령이 도는 동안에는 표시되지 않고, 답변이 끝난 뒤 20초 안에 교정이 끝나지 않으면 다음 턴에 표시됩니다.
- 교정 결과는 대화형 세션의 화면에 표시합니다. `claude -p`의 최종 답변에는 나오지 않습니다.
- 한자가 한 글자라도 있는 한국어나 영어 요청에는 훅이 반응하므로, 교정할 대상이 없어도 Sonnet 호출이 한 번 듭니다.
- Claude가 최종 답변을 중국어로 쓰면 지정한 언어로 한 번 다시 쓰게 합니다. 이때 표시되는 `Stop hook error:`는 Claude Code가 붙이는 문구이며 실제 오류가 아닙니다.

그 밖의 한계는 [그 밖의 한계](docs/configuration.md#그-밖의-한계)에서, 교정을 실행하지 못할 때의 표시는 [교정을 실행하지 못할 때](docs/configuration.md#교정을-실행하지-못할-때)에서 설명합니다.

## 문서

- [설정과 세부 동작](docs/configuration.md): 환경 변수 전체, 답변 언어 규칙, 나머지 한계를 설명합니다.
- [개발하기](docs/development.md): 플러그인의 동작 방식, 중국어 판별 기준, 저장소 구조, 테스트 방법을 설명합니다.
- [설계와 평가](docs/design-and-evaluation.md): 주요 설계 결정과 평가 결과를 요약했습니다.
- [설계 결정 기록](docs/design-decisions.md): 결정마다 검토한 대안과 트레이드오프를 기록했습니다.
- [평가 결과](docs/eval-results.md): 평가마다 날짜, 대상 커밋, 모델, 수치를 기록했습니다.

## 라이선스

[MIT License](LICENSE)로 배포합니다.
