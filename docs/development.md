# 개발하기

이 문서는 플러그인의 내부 동작과 저장소 구조, 테스트 방법을 설명합니다. 설치 방법과 사용법은 [README](../README.md)에서, 설계 결정과 평가 결과는 [설계와 평가](design-and-evaluation.md)에서 설명합니다.

## 동작 방식

1. `UserPromptSubmit` 훅이 입력된 프롬프트를 검사하여 중국어인지 판별합니다. 판별 기준은 [중국어 판별 기준](#중국어-판별-기준)에 정리했습니다.
2. 중국어라고 판별되면, 훅은 교정 프로세스를 따로 실행하고 바로 끝납니다. Claude의 컨텍스트에는 교정하지 말라는 지시와 답변 언어만 추가합니다.
3. 교정 프로세스는 `prompts/proofread.md`의 규칙에 따라 `claude -p`로 교정하고, 결과를 세션별 폴더에 저장합니다. 그동안 Claude는 원문을 기준으로 작업합니다.
4. `PostToolUse`, `PostToolUseFailure`, `Stop` 훅이 끝난 결과를 `systemMessage`로 한 번만 표시합니다.
5. 답변이 끝났는데 교정이 실행 중이면 `Stop` 훅이 최대 20초 기다리고, 그래도 끝나지 않으면 다음 턴에 표시합니다. 교정이 실패하면 작업은 그대로 두고 실패 사실만 표시합니다.
6. `Stop` 훅은 최종 답변이 대부분 중국어이면 턴을 한 번 이어 가게 하여, 지정한 언어로 다시 쓰게 합니다.

## 중국어 판별 기준

입력한 프롬프트가 다음 조건을 모두 만족하면 중국어로 판별합니다. 영문 코드와 식별자는 판별에 반영하지 않으므로, 코드가 섞인 중국어 문장도 중국어로 판별됩니다.

- 한자가 4자 이상 있어야 합니다(`MIN_HANZI`). 다만 영문자나 한글이 섞여 있다면 한자가 1자만 있어도 됩니다(`MIN_HANZI_MIXED`). `跑local server.`처럼 모르는 단어를 대신 쓴 짧은 문장과, 한국어나 영어 문장에 섞어 쓴 중국어 단어도 교정하기 위해서입니다. 한자만으로 쓴 `好的` 같은 짧은 대답에는 반응하지 않습니다.
- 히라가나나 가타카나가 없어야 합니다. 둘 중 하나라도 섞여 있으면 일본어로 보고 제외합니다.
- 한자 수와 한글 수를 더한 값에서 한자가 차지하는 비율이 기준값 이상이어야 합니다(`HANZI_RATIO`). 기본값은 0이므로 이 조건은 항상 만족되며, `0.5`로 설정하면 한자가 적은 한국어 문장을 교정 대상에서 뺍니다.

괄호 안의 이름은 각 조건의 기준값을 바꾸는 환경 변수의 이름에서 `CHINESE_PROOFREAD_`를 뺀 것입니다. 위 숫자는 모두 기본값이며, [환경 변수](configuration.md#환경-변수)에 나온 환경 변수로 바꿀 수 있습니다.

한자가 섞인 입력이 인용한 중국어인지는 판별 단계에서 가리지 않고, 교정 에이전트가 판단합니다. 교정할 대상이 없으면 아무것도 표시하지 않습니다.

## 저장소 구조

```
.claude-plugin/marketplace.json            마켓플레이스 정의
plugins/chinese-proofread/
  .claude-plugin/plugin.json               플러그인 정의
  hooks/hooks.json                         UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop 훅 등록
  hooks/detect_chinese.py                  중국어 판별과 교정 프로세스 실행
  hooks/proofread_worker.py                claude -p로 교정하는 별도 프로세스
  hooks/show_result.py                     끝난 교정 결과를 표시하고 중국어 답변을 다시 쓰게 하는 스크립트
  hooks/jobs.py                            교정 작업 파일을 다루는 공용 코드
  scripts/toggle.py                        교정 기능의 상태를 바꾸는 스크립트
  prompts/proofread.md                     교정 규칙과 출력 형식
  skills/toggle/SKILL.md                   교정 기능을 켜고 끄는 명령
tests/test_detect_chinese.py               중국어 판별 스크립트의 테스트
tests/test_parallel_proofread.py           교정 실행과 결과 표시의 테스트
.github/workflows/test.yml                 테스트를 실행하는 GitHub Actions 워크플로
```

## 테스트

훅 스크립트를 수정했다면 커밋하기 전에 저장소 루트에서 다음 명령을 실행합니다. 외부 패키지는 필요하지 않습니다.

```
python3 -m unittest discover -s tests
```

`main` 브랜치에 push하거나 pull request를 열면 GitHub Actions가 Python 3.9와 3.14에서 같은 테스트를 실행합니다.

## 버전 정책

이 플러그인은 유의적 버전을 따르며, 코드 API가 아니라 사용자가 겪는 동작을 기준으로 버전을 올립니다.

| 올리는 자리 | 기준 | 예 |
| --- | --- | --- |
| MAJOR | 기존 사용자가 설정이나 사용법을 바꿔야 하는 변경 | 환경 변수의 이름 변경과 삭제, 토글 스킬의 이름 변경, 필요한 실행 환경의 추가 |
| MINOR | 기존 동작을 유지하면서 기능을 추가하는 변경 | 새로운 설정 추가, 교정 이력 기능 추가 |
| PATCH | 사용법을 유지하면서 동작을 수정하는 변경 | 버그 수정, 판별 오류 수정, 프롬프트의 작은 규칙 수정 |
| 올리지 않음 | 설치된 플러그인에 영향을 주지 않는 변경 | `docs/`, `README.md`, `evals/`, `tests/`만 바뀐 변경 |

다음 경우에는 위 기준에 더해 아래와 같이 판단합니다.

- **교정 출력 형식:** `📝 中文校对` 블록은 사람이 읽는 출력이므로, 형식을 바꾸면 MINOR로 올립니다. 다만 교정 이력처럼 파일에 저장하는 형식은 호환성을 지켜야 하는 대상이므로, 호환되지 않게 바꾸면 MAJOR로 올립니다.
- **기본값 변경:** 설정을 바꾸지 않아도 동작이 달라지므로, 비용이 늘거나 출력 언어가 바뀌는 등 사용자가 바로 체감하는 변경은 MAJOR로 올리고, 판별 기준을 다듬는 변경은 MINOR로 올립니다.
- **프롬프트 수정:** `prompts/proofread.md`를 고쳐서 교정 범위가 눈에 띄게 달라지면 MINOR로 올립니다.

버전은 `plugins/chinese-proofread/.claude-plugin/plugin.json`의 `version` 한 곳에만 적습니다. `marketplace.json`에는 적지 않습니다.

기능 PR에서는 버전을 올리지 않습니다. 배포할 때 전용 PR로 버전을 올리고, `main`에 합친 커밋에 `vX.Y.Z` 태그와 GitHub Release를 만듭니다. 설치된 플러그인의 업데이트는 버전이 올라가야 전달되므로, 플러그인 코드의 변경을 배포하지 않은 채 오래 쌓아 두지 않습니다.
