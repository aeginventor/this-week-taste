"""워크플로의 cron 슬롯과 실행 묶음이 어긋나지 않는가 (CLAUDE.md 7장 2번).

**이 자리는 이미 한 번 터졌다.** 예전 선택식은 cron 문자열 하나와 소스 id 하나를
동시에 박아 두었다.

    SELECTION: ${{ github.event.schedule == '0 5 * * 1' && 'ONLY=gs25' || 'SKIP=gs25' }}

cron을 하나라도 늘리면 새 슬롯이 **예외 없이** `SKIP=gs25`로 떨어져, 시각 창이
걸린 소스가 영영 수집되지 않는다. 지금 식은 소스 id를 지웠지만 cron 목록은
여전히 두 곳(`schedule`과 선택식)에 적혀 있다. 한쪽만 고치는 날이 온다.

그리고 그 결과는 조용하다 — 워크플로는 성공하고 그 소스만 없는 주가 발행된다.
2.4가 닿지 않는 종류의 실패다.
"""

import re
from pathlib import Path

import pytest
import yaml

from pipeline import sources

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/weekly.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")
# PyYAML은 `on:`을 불리언 True로 읽는다 (YAML 1.1의 유산).
PARSED = yaml.safe_load(TEXT)


def crons() -> list[str]:
    return [entry["cron"] for entry in PARSED[True]["schedule"]]


def windowed_crons() -> list[str]:
    """선택식의 `fromJSON([...])` 배열. 여기 든 슬롯이 창 안 묶음으로 간다."""
    match = re.search(r"fromJSON\('(\[.*?\])'\)", TEXT)
    assert match, "GROUP 선택식에서 fromJSON 배열을 찾지 못했다"
    return yaml.safe_load(match.group(1))


def test_창안_슬롯이_전부_실제_cron이다():
    """배열에만 있고 schedule에 없는 슬롯은 **영원히 발화하지 않는다.**"""
    없는것 = set(windowed_crons()) - set(crons())
    assert not 없는것, f"schedule에 없는 cron을 창 안으로 적었다: {sorted(없는것)}"


def 슬롯별_묶음() -> dict[str, set[str]]:
    """자동화가 도는 묶음 → 그 묶음을 깨우는 cron 슬롯.

    `local`은 사람이 도는 몫이라 슬롯이 없는 것이 정상이다 (ADR-0017).
    """
    창안 = set(windowed_crons())
    return {"actions-windowed": 창안, "actions-anytime": set(crons()) - 창안}


@pytest.mark.parametrize("name", 슬롯별_묶음())
def test_소스가_있는_묶음에는_슬롯이_둘_이상이다(name):
    """2026-08-31에 cron 두 슬롯이 **모두** 발화하지 않았다.

    안 돈 실행은 로그도 Issue도 남기지 않아 감시로는 잡을 수 없다. 대책이 다중화뿐이다 —
    2.6의 멱등이 재실행을 사실상 공짜로 만든다(요청 0건, 0.07초).
    """
    if not sources.group(name):
        pytest.skip(f"{name}에 소스가 없다")
    assert len(슬롯별_묶음()[name]) >= 2, f"{name}의 슬롯이 둘 미만이다"


@pytest.mark.parametrize("name", 슬롯별_묶음())
def test_소스가_없는_묶음에는_슬롯이_없다(name):
    """빈 묶음에 슬롯을 남겨두면 **매주 그만큼 실패한다.**

    `collect-all`이 빈 선택을 성공으로 넘기지 않기 때문이다(2.4). 그 실패는 고칠 수
    있는 것이 없는 실패라, 진짜 이상 상황을 가리는 잡음이 된다.

    2026-08-31에 gs25가 빠지면서 `actions-windowed`가 비었다. 그런 소스가 다시
    생기면 슬롯도 같이 돌아온다 — 어느 쪽이든 이 둘은 함께 움직인다.
    """
    if sources.group(name):
        pytest.skip(f"{name}에 소스가 있다")
    assert not 슬롯별_묶음()[name], f"{name}에 소스가 없는데 cron 슬롯이 남아 있다"


@pytest.mark.parametrize("cron", crons())
def test_정각을_피한다(cron):
    """전 세계 스케줄이 정각에 몰려 그 시각이 가장 잘 밀린다."""
    assert cron.split()[0] != "0", f"정각 슬롯: {cron!r}"


@pytest.mark.parametrize("cron", crons())
def test_UTC_월요일이다(cron):
    """요일 숫자는 UTC 기준인데 주차는 KST로 계산한다 (pipeline/weeks.py).

    UTC 일요일에 돌면 스냅샷이 지난주 주차로 저장되어 **이미 발행한 주차를 건드린다.**
    KST 월요일 00:00(UTC 일 15:00)이 하한선이므로, UTC 월요일이면 안전한 쪽이다.
    """
    minute, hour, dom, month, dow = cron.split()
    assert dow == "1", f"UTC 월요일이 아니다: {cron!r}"
    assert (dom, month) == ("*", "*"), f"날짜를 고정했다: {cron!r}"


def test_소스_id가_워크플로에_없다():
    """7장의 누수 판별법을 워크플로에도 적용한다.

    소스 id가 여기 박히면 소스가 늘거나 차단 상태가 바뀔 때마다 워크플로를 고치게 된다.
    묶음에 무엇이 드는지는 pipeline/sources.py의 GROUPS가 정한다.
    """
    새는것 = [s for s in sources.known() if re.search(rf"\b{re.escape(s)}\b", TEXT)]
    assert not 새는것, f"워크플로에 소스 id가 있다: {새는것}"
