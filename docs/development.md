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
