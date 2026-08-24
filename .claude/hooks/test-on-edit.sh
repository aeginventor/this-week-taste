#!/usr/bin/env bash
# 파이프라인·스크래퍼·테스트를 고치면 곧바로 테스트를 돌린다.
#
# 왜 필요한가: CLAUDE.md 7장이 경고하는 사고(소스 고유 어휘가 공유 코드에 새는 것)는
# 예외를 던지지 않는다. 조용히 틀린 숫자를 낸다. 테스트가 유일한 방어선인데
# 사람이 기억해서 돌려야 하면 잊는다. 전체가 0.2초라 매번 돌려도 비용이 없다.
#
# PostToolUse 훅. 표준입력으로 {"tool_input": {"file_path": ...}} 를 받는다.
set -uo pipefail

path=$(jq -r '.tool_input.file_path // empty')
[ -n "$path" ] || exit 0

case "$path" in
  */pipeline/*.py|*/scrapers/*.py|*/tests/*.py) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -x .venv/bin/python ] || exit 0

if ! output=$(.venv/bin/python -m pytest tests/ -q 2>&1); then
  # exit 2 = 결과를 Claude에게 되돌려준다. 조용히 넘어가지 않는다 (CLAUDE.md 2.4).
  echo "테스트 실패 — 방금 고친 곳을 확인할 것" >&2
  echo "$output" | tail -30 >&2
  exit 2
fi
exit 0
