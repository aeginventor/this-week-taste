# 공식 발표 추출 실험 — 동결 보관

이 실험은 운영 수집기로 채택하지 않았다. 개발 밖 발표 11편에서 유용한 상품 연결은 0건이었다.
모델이 맞힌 상대 날짜를 코드가 지운 실패도 남았다. 같은 자료의 규칙을 더 보강해 성과로 바꾸지 않는다.
당시 결과와 AI가 만든 정답 후보의 한계는 [평가 기록](../../learning/sessions/2026-09-10-동결평가와-GitHub-보존.md)에 있다.

## 남긴 것과 뺀 것

- 다섯 스크립트·회귀 반례·합성 픽스처를 바이트 변경 없이 옮겼다. 날짜/제품 계열 규칙은 이 실험에 한정한다.
- 초기 수동 주장 연결기와 고정 8건 비교 스크립트는 중복 구현이라 현재 실행 경로에서 뺐다. 측정표·당시 한계와 원래 Git 파일은 보존한다.
- `manifest.json`은 옛 경로·원래 커밋·현재 경로·SHA-256을 연결한다. 비공개 `freeze.json`의 과거 지문은 바꾸지 않는다.
- 운영 `pipeline/`, `make test`, 스케줄은 이 디렉터리를 사용하지 않는다. 수집·추출 명령은 동결 당시 구현이며 새 실행 절차가 아니다.

## 네트워크 없이 재현

저장 원본과 응답은 비공개 데이터 저장소의 `research/launch-automation-2026-09-10/`에 있다.
모델·실행 파일·원문은 공개 저장소에 넣지 않는다. 새 수집이나 모델 호출 없이 저장 응답을 재생한다.

이 디렉터리에서 다음을 실행한다. `PYTHONPATH`에는 코드 저장소의 절대 경로를 지정한다.

```sh
PYTHONPATH=/absolute/code/repo /absolute/code/repo/.venv/bin/python -m pytest tests/ -q
PYTHONPATH=/absolute/code/repo /absolute/code/repo/.venv/bin/python -m scripts.evaluate_newsroom_period --root /private/replay-copy/period-once --catalog /private/replay-copy/starbucks-W36.json
```

평가기는 결과 파일을 기록하므로 원본 대신 임시 사본에서 실행한다. 목록의 재사용 문서도 개발 사본과 함께 복원한다.
`freeze.json`에 맞는 W36 카탈로그는 비공개 데이터 커밋 `9f22daa`의 `snapshots/2026-W36/starbucks.json`이다.
다른 주차로 바꾸면 코드가 거부해야 한다. 재생 성공은 원시 모델을 다시 호출해 같은 답을 얻었다는 뜻이 아니다.
Ollama/Qwen을 다시 실행할 때는 출처·버전·취약점·노출 설정을 새로 확인한다.
[이번 점검 결과](../../docs/local-model-audit-2026-09-10.md)는 서명 검사 환경 차이와 미확인 수정 범위를 함께 기록한다.

## 원래 이력

- 개발·API 연구: 코드 `e5aa0ce`, 데이터 `d466891`.
- 동결 평가: 코드 `10865a1`, 데이터 `aa31313`.
- 양쪽 저장소의 `archive/redesign-evaluation-20260910` 태그가 각각 코드 `10865a1`·데이터 `aa31313`과 그 앞 이력을 보존한다. `manifest.json`과 원래 `freeze.json`의 커밋·파일 지문은 그대로다.
- 현재 작업 브랜치는 `refactor/collection-review`다. 앞선 정리의 커밋을 다시 만들지 않고 브랜치 이름을 옮겼다. 옛 원격 브랜치 삭제는 별도 확인 대상이며 재현 근거는 보존 태그에서도 찾을 수 있다.

기록에 있는 당시 추천과 승인 대기 문구는 과거 상태다. 현재 추천을 대신하지 않는다.
