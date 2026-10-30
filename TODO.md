# 앞으로 할 일

남은 작업은 GitHub 이슈로 관리합니다. 이 문서에는 남은 작업의 목록과 진행 순서, 작업하는 동안 계속 지킬 규칙만 남깁니다.

정리하기 전의 작업 목록은 [커밋 `b768c62`의 `TODO.md`](https://github.com/robinyoon-dev/chinese-proofread/blob/b768c62/TODO.md)에 있습니다. 그 버전에는 완료한 작업의 진행 기록과 남은 작업의 세부 계획이 들어 있습니다. `docs/design-decisions.md`와 `docs/eval-results.md`에서 `TODO.md`의 번호(예: 6-3, 9-5)로 언급한 항목은 모두 그 버전의 번호를 가리킵니다.

## 남은 작업

| 이전 번호 | 작업 | 이슈 |
|---|---|---|
| 11 | 교정 결과를 작업 전에 보여 주기 | [#1](https://github.com/robinyoon-dev/chinese-proofread/issues/1) |
| 없음 | 작업 답변의 언어를 설정으로 정할 수 있게 하기 | [#2](https://github.com/robinyoon-dev/chinese-proofread/issues/2) |
| 6-3 | 교정 품질 평가의 2~4단계 진행하기 | [#3](https://github.com/robinyoon-dev/chinese-proofread/issues/3) |
| 3 | 학습 수준에 따라 교정 방식을 바꾸는 설정 추가하기 | [#4](https://github.com/robinyoon-dev/chinese-proofread/issues/4) |
| 4 | 대만식 표현을 기준으로 교정하는 설정 추가하기 | [#5](https://github.com/robinyoon-dev/chinese-proofread/issues/5) |
| 2 | 교정 이력을 기록하고 요약하기 | [#6](https://github.com/robinyoon-dev/chinese-proofread/issues/6) |

## 진행 순서

1. [#1](https://github.com/robinyoon-dev/chinese-proofread/issues/1)을 먼저 진행합니다. #1은 교정 블록의 출력 위치를 바꾸므로, 그 전에 남긴 점수는 이후의 점수와 비교하기 어렵기 때문입니다.
2. [#3](https://github.com/robinyoon-dev/chinese-proofread/issues/3)에서 `SKILL.md`가 바뀌기 전의 기준 점수를 남깁니다.
3. [#4](https://github.com/robinyoon-dev/chinese-proofread/issues/4)와 [#5](https://github.com/robinyoon-dev/chinese-proofread/issues/5)를 함께 진행합니다. 두 작업은 모두 환경 변수를 훅에서 전달하고 `SKILL.md`에 규칙을 추가하는 구조이기 때문입니다. 이때 출력 형식에 오류 유형 태그를 추가할지도 함께 정합니다.
4. [#6](https://github.com/robinyoon-dev/chinese-proofread/issues/6)은 오류 유형 태그를 포함한 출력 형식이 확정된 뒤에 마지막으로 시작합니다.

[#2](https://github.com/robinyoon-dev/chinese-proofread/issues/2)는 #1의 시험에서 드러난 문제이며, 아직 진행 순서를 정하지 않았습니다.

## 계속 지킬 규칙

- 설계 결정은 `docs/design-decisions.md`에 기록합니다. 이슈를 진행하면서 새로운 결정을 내리면, 결정과 이유와 대안과 트레이드오프를 그 자리에서 추가합니다. 시간이 지나면 검토했던 대안을 잊어버리기 쉬우므로 미루지 않습니다.
- 각 항목의 "대안"에는 실제로 검토했던 방법만 적습니다.
- 평가 결과가 나오면 관련된 설계 결정 항목에 수치를 근거로 덧붙입니다.
- 판별 규칙을 바꾸고 판별 정확도를 다시 평가할 때는, 새 확인용 문장을 먼저 추가합니다. 지금의 확인용 세트는 이미 한 번 사용했으므로, 그 결과를 보고 규칙을 고르면 수치가 실제보다 좋게 나오기 때문입니다.
