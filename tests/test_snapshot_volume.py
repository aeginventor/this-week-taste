"""건수 급감·급증·0건 판정 (CLAUDE.md 2.4).

**틀린 답이 예외 없이 그냥 숫자로 나오는 자리**라 7장이 테스트를 요구하는 두 번째
종류다. 문턱을 잘못 잡으면 조용히 둘 중 하나가 된다 — 사고를 놓치거나,
정상 변동마다 발행이 멈추거나.

11장이 "급증(+200%) 탐지는 한 번도 걸린 적 없음"으로 적어둔 자리다. 실제 수집에서
걸리기를 기다리면 그때가 첫 실행이 되므로, 여기서 미리 걸어본다.
"""

import json

import pytest

from pipeline import alert, snapshot

WEEK = "2026-W35"
PREV = "2026-W34"


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path


@pytest.fixture
def quiet_notify(monkeypatch):
    """알림을 가로채 호출 내역만 모은다. 테스트가 GitHub을 치면 안 된다."""
    sent = []
    monkeypatch.setattr(alert, "notify", lambda title, body: sent.append((title, body)))
    return sent


def _write(week, source_id, count):
    path = snapshot.snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source_id": source_id, "week": week, "count": count,
        "items": [{"external_id": f"x{i}"} for i in range(count)],
    }), encoding="utf-8")


def test_0건이면_이상이다(snap_dir, quiet_notify):
    with pytest.raises(alert.PipelineAnomaly, match="0건"):
        snapshot._check_volume("cu", WEEK, 0)


def test_첫_수집은_증감을_보지_않는다(snap_dir, quiet_notify):
    """비교 대상이 없다. 여기서 예외가 나면 새 소스를 영영 못 붙인다."""
    snapshot._check_volume("cu", WEEK, 4000)
    assert quiet_notify == []


def test_급감은_이상이다(snap_dir, quiet_notify):
    _write(PREV, "cu", 1000)
    with pytest.raises(alert.PipelineAnomaly, match="급감"):
        snapshot._check_volume("cu", WEEK, 299)      # 29.9% < 30%


def test_급증은_이상이다(snap_dir, quiet_notify):
    """11장의 미검증 항목. 감소만 보면 목록의 성격이 통째로 바뀐 사고를 놓친다."""
    _write(PREV, "cu", 100)
    with pytest.raises(alert.PipelineAnomaly, match="급증"):
        snapshot._check_volume("cu", WEEK, 301)      # 301% > 300%

    title, body = quiet_notify[-1]
    assert "급증" in title
    assert "직전 주 100건 → 이번 주 301건" in body and "+201%" in body


@pytest.mark.parametrize("count", [300, 1000, 3000])
def test_문턱_안이면_통과한다(snap_dir, quiet_notify, count):
    """30%~300%는 정상 변동이다. 여기가 좁으면 매주 발행이 멈춘다."""
    _write(PREV, "cu", 1000)
    snapshot._check_volume("cu", WEEK, count)
    assert quiet_notify == []


def test_경계값은_이상이_아니다(snap_dir, quiet_notify):
    """`<`와 `>`이므로 정확히 문턱이면 통과한다. 부등호가 뒤집히면 여기서 잡힌다."""
    _write(PREV, "cu", 100)
    snapshot._check_volume("cu", WEEK, 30)       # 정확히 30%
    snapshot._check_volume("cu", WEEK, 300)      # 정확히 300%
    assert quiet_notify == []


def test_지난주가_0건이면_비율을_보지_않는다(snap_dir, quiet_notify):
    """0으로 나누면 ZeroDivisionError로 그 주 수집이 통째로 죽는다."""
    _write(PREV, "cu", 0)
    snapshot._check_volume("cu", WEEK, 500)
    assert quiet_notify == []


def test_건너뛴_주차를_되짚어_비교한다(snap_dir, quiet_notify):
    """W34가 없으면 W33과 비교한다 (ADR-0007). 안 그러면 첫 수집으로 오인한다."""
    _write("2026-W33", "cu", 100)
    with pytest.raises(alert.PipelineAnomaly, match="급증"):
        snapshot._check_volume("cu", WEEK, 400)


# ── 이월이 대조군 파일까지 옮기는가 ───────────────────────────────
#
# `_hold_previous`의 이월 자체는 test_snapshot_lookback.py가 덮는다. 여기서는
# **control 파일**을 본다 — 빠뜨리면 그 주의 채점표(소스 NEW 라벨)가 사라지고,
# 8장의 오탐 지표가 조용히 0건으로 집계된다.

def test_이월은_대조군_파일도_함께_옮긴다(snap_dir):
    _write("2026-W33", "cu", 10)
    snapshot.control_path("2026-W33", "cu").write_text(
        json.dumps({"x1": {"labels": {"new": True}}}), encoding="utf-8")

    assert snapshot._hold_previous(WEEK, "cu") is True

    moved = snapshot.control_path(WEEK, "cu")
    assert moved.exists()
    assert json.loads(moved.read_text(encoding="utf-8")) == {"x1": {"labels": {"new": True}}}


def test_이월할_지난주가_없으면_실패로_끝난다(snap_dir):
    """새 소스의 첫 주가 이 경우다. 조용히 성공으로 넘기면 안 된다."""
    assert snapshot._hold_previous(WEEK, "cu") is False
    assert not snapshot.snapshot_path(WEEK, "cu").exists()
