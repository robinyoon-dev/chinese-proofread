# 교정 품질 평가 시범 실행

이 문서는 `TODO.md`의 6-3에서 진행한 0단계 시범 실행의 결과를 기록합니다. 시범 실행의 목적은 평가 세트를 만들기 전에 `claude plugin eval`의 내장 레퍼런스에 나오지 않는 동작을 직접 확인하는 것이었습니다.

## 실행 환경

- **날짜**: 2026-10-29
- **대상 커밋**: `d44b72d` (플러그인 파일은 이 커밋과 같습니다)
- **Claude Code**: 2.1.312
- **로그인 방식**: claude.ai Max 구독. API 키는 설정되어 있지 않습니다.
- **모델**: Sonnet 5.5(`claude-sonnet-5-5`)로 2회, Opus 5.5(`claude-opus-5-5`)로 1회 실행했습니다.
- **실행 위치**: 저장소를 수정하지 않도록, 플러그인을 Claude의 임시 작업 폴더(scratchpad)에 복사하여 실행했습니다. 실행 결과와 복사한 파일은 저장소에 남기지 않았습니다.

## 시범 케이스

케이스는 하나만 만들었습니다.

- **입력**: `帮我fix一下utils.py里的bug`
- **작업 폴더**: `scaffold_script`로 `utils.py`와 `test_utils.py`를 만들었습니다. `utils.py`의 `average()`는 평균에 `+ 1`을 더하는 버그를 포함합니다.
- **허용한 도구**: `Read`, `Edit`, `Skill`, `Glob`, `Grep`
- **채점자**:

| 이름 | 종류 | 확인하는 내용 |
|---|---|---|
| `hook-fired` | `regex` (파일 내용) | 훅이 지시문을 출력했는지 확인합니다. 아래 "훅 실행 여부"에 적은 표시 파일을 검사합니다. |
| `skill-used` | `tool_used` | `proofread` 스킬을 불러왔는지 확인합니다. |
| `block-format` | `regex` (`last_message`) | 마지막 응답에 `📝 中文校对`가 있는지 확인합니다. |
| `block-anywhere` | `regex` (`trace`) | 응답의 어느 텍스트 블록에서든 `📝 中文校对`로 시작하는 블록이 있는지 확인합니다. |
| `edited` | `tool_used` | `Edit`을 한 번 이상 호출했는지 확인합니다. |
| `file-fixed` | `regex` (파일 내용) | 실행이 끝난 뒤의 `utils.py`에 `+ 1`이 남아 있지 않은지 확인합니다. |

실행 명령은 다음과 같습니다.

```
claude plugin eval ./plugins/chinese-proofread --model sonnet --ablation none --runs 1 \
  --scaffold --allow-tools Edit --trust-plugin --no-publish --keep-temp \
  --output-dir <결과 폴더> --json <결과 파일>
```

## 확인한 동작

### eval 폴더의 위치

- 플러그인 바깥에 eval 폴더를 둘 수 없습니다. `plugin.json`의 `experimental.evals`에 `../../evals/quality`를 지정하면 다음 경고가 출력되고, 기본 위치인 `evals/`를 대신 사용합니다.

  ```
  Warning: ignoring experimental.evals "../../evals/quality" in .../plugin.json — it must stay inside the plugin root (no ..); using evals/ (fix the manifest or pass --eval-dir)
  ```

- 따라서 평가 케이스를 플러그인 폴더(`plugins/chinese-proofread/evals/`) 안에 두면, 6-1의 테스트 파일과 마찬가지로 사용자가 플러그인을 설치할 때 평가 파일까지 함께 받게 됩니다.

### 훅 실행 여부

- eval 실행에서도 플러그인의 `UserPromptSubmit` 훅이 실행됩니다.
- eval이 남기는 실행 기록(`trace.jsonl`)에는 훅 이벤트와 훅이 추가한 지시문이 기록되지 않습니다. 그래서 실행 기록만으로는 훅이 실행되었는지 알 수 없었습니다.
- 복사한 플러그인의 `detect_chinese.py`를 수정하여, 훅이 실행되면 작업 폴더에 `hook-ran.txt`를 쓰고 지시문을 출력할 때 `context` 줄을 덧붙이게 했습니다. 세 번의 실행에서 모두 이 파일에 `context` 줄이 기록되었습니다. 이 수정은 확인용으로만 사용했고, 저장소의 훅은 수정하지 않았습니다.

### 작업 폴더 준비

- `scaffold_script`는 `--scaffold` 옵션을 지정했을 때만 실행되며, 실행 위치는 모델이 작업하는 폴더입니다.
- 채점자의 `target`에 `{source: file, path: utils.py}`를 지정하면, 실행이 끝난 뒤의 파일 내용을 검사할 수 있습니다.

### Bash 도구 사용 제한

- 이 컴퓨터에서는 Bash를 허용한 eval을 실행할 수 없습니다. `--allow-tools Bash`를 지정하면 모델을 호출하기 전에 다음 오류로 실행이 실패합니다.

  ```
  the Docker (~/.docker, DOCKER_CONFIG) credential store on this machine holds a symbolic link inside it (at or under its "contexts" entry), so the Bash sandbox cannot reliably exclude it — a Bash-granting evaluation cannot run here
  ```

- 원인은 Docker Desktop의 WSL 연동 기능이 `~/.docker/contexts`를 Windows 쪽 폴더를 가리키는 심볼릭 링크로 만들어 두었기 때문입니다. 환경 변수 `DOCKER_CONFIG`를 빈 폴더로 바꾸어도 eval이 `~/.docker`를 함께 검사하므로 오류가 계속 발생했습니다. Docker 설정은 수정하지 않았습니다.
- 따라서 지금은 `Read`와 `Edit`만으로 끝나는 작업에서만 작업 계속 수행률을 측정할 수 있습니다. 9-1의 `跑local server.`처럼 명령을 실행해야 하는 작업은 측정할 수 없습니다.

### 결과 파일에 기록되는 정보

- `aggregate-result.json`과 `--json`으로 저장한 결과 파일에는 실행마다 점수, 턴 수, 비용(`costUsd`), 채점 모델의 비용(`judgeCostUsd`), 실행 시간, 채점자별 판정과 이유가 기록됩니다.
- 실행 전체에 지정한 모델은 `suite.modelOverride`에 기록되고, 실제로 사용한 모델 ID는 `trace.jsonl`의 첫 줄(`system`의 `init` 이벤트)에 기록됩니다.

## 실행 결과

| 모델 | `hook-fired` | `skill-used` | `block-format` | `block-anywhere` | `edited` | `file-fixed` | 턴 수 | 비용 |
|---|---|---|---|---|---|---|---|---|
| Sonnet 5.5 (1회차) | 통과하지 못함* | 통과 | 통과하지 못함 | 채점자 없음 | 통과 | 통과 | 6 | $0.051 |
| Sonnet 5.5 (2회차) | 통과 | 통과 | 통과하지 못함 | 통과하지 못함 | 통과 | 통과 | 6 | $0.051 |
| Opus 5.5 | 통과 | 통과 | 통과 | 통과 | 통과 | 통과 | 6 | $0.101 |

\* 1회차의 `hook-fired`는 실행 기록에서 훅의 지시문을 찾는 채점자였습니다. 실행 기록에는 훅의 지시문이 남지 않으므로, 이 채점자가 통과하지 못한 것은 훅이 실행되지 않았다는 뜻이 아닙니다. 2회차부터는 표시 파일을 검사하는 채점자로 바꾸었습니다.

### Sonnet에서 교정 블록이 최종 답변에 나오지 않은 문제

- Sonnet으로 실행한 두 번 모두, 모델은 `proofread` 스킬을 불러왔지만 최종 답변에 교정 블록을 출력하지 않았습니다. 대신 도구를 호출하는 사이에 남기는 진행 메모에만 교정 판단을 적었습니다. 두 번째 실행의 진행 메모는 다음과 같습니다.

  ```
  문장이 자연스러우며, fix는 修复로 바꿔도 무방하다는 점을 확인했습니다. 이제 utils.py를 읽어 버그를 찾아보겠습니다.
  ```

- 최종 답변은 버그를 고친 내용만 설명했고, `📝 中文校对`로 시작하는 블록은 응답의 어느 텍스트 블록에도 없었습니다.
- Opus는 최종 답변의 맨 앞에 다음 블록을 출력한 뒤 버그를 고친 내용을 설명했습니다.

  ```
  📝 中文校对: ✅ 자연스럽습니다.
  - fix는 중국어로 修(xiū) 또는 修复(xiūfù)라고 합니다. 이 문장에서는 `帮我修一下utils.py里的bug`처럼 써도 자연스럽습니다.
  ---
  ```

- 이 결과가 사실이라면, Sonnet을 쓰는 사용자는 교정 결과를 전혀 보지 못할 수 있습니다. 다만 다음 두 가지를 아직 확인하지 않았습니다.
  - 실행 횟수가 두 번뿐이므로, 이 동작이 얼마나 자주 일어나는지는 알 수 없습니다.
  - 대화형 세션에서 진행 메모가 사용자에게 표시되는지 확인하지 않았습니다. 진행 메모가 표시되더라도 정해진 출력 형식은 지켜지지 않습니다.
- `SKILL.md`를 바로 수정하면 수정하기 전의 기준 점수를 남길 수 없으므로, 1단계에서 Sonnet과 Opus의 기준 점수를 먼저 기록한 뒤에 수정합니다.

## 다음 단계에 반영할 내용

- 평가 케이스는 저장소 루트의 `evals/quality/`에 둡니다. 실행할 때는 플러그인과 평가 케이스를 임시 폴더에 함께 복사한 뒤 eval을 실행하는 스크립트를 사용합니다. 이렇게 하면 사용자가 플러그인을 설치할 때 평가 파일을 받지 않습니다.
- 교정 블록의 형식은 `last_message`와 `trace`를 대상으로 하는 채점자를 함께 두어 검사합니다. 두 채점자를 함께 두면 교정 블록을 생략한 경우와 중간 텍스트에만 출력한 경우를 구분할 수 있습니다.
- 훅의 실행 여부는 이번 시범 실행에서 확인했으므로, 평가 세트에는 표시 파일을 쓰는 훅 수정과 `hook-fired` 채점자를 넣지 않습니다. 훅의 판별 정확도는 6-2에서 이미 측정했습니다.
- Bash를 허용할 수 없으므로, 1단계의 작업 계속 수행률은 `Read`와 `Edit`만으로 끝나는 작업으로 측정합니다. 명령을 실행해야 하는 작업은 Docker 설정 문제를 해결하거나 다른 환경에서 실행할 수 있을 때 추가합니다.
- 실측한 비용을 기준으로 하면, 1단계의 약 90회 실행은 Sonnet 기준으로 약 $5입니다. 1단계를 Sonnet으로 실행할 때는 `--max-cost-usd 10`을 지정합니다.
