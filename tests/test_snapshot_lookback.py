"""건수 검증·이월이 보는 '지난주'. 틀리면 예외 없이 판정 기준만 바뀐다 (CLAUDE.md 7장).

실제로 2026-W35에서 이것 때문에 오리온이 발행되지 않을 뻔했다. 직전 주(W34)가 없어
정찰 실측치 ±10% 기준으로 떨어졌고, 껌 3→2건 같은 정상 변동이 -33%로 잡혀 이상이 됐다.
W33과 비교했다면 30~300% 기준이라 통과했을 값이다.
"""

import json

import pytest

from pipeline import snapshot


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path


def _write(week, source_id, count=10):
    path = snapshot.snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"week": week, "source_id": source_id,
                                "count": count, "items": []}), encoding="utf-8")


def test_직전_주가_있으면_그것을_쓴다(snap_dir):
    _write("2026-W33", "cu"); _write("2026-W34", "cu")
    assert snapshot.previous_available("cu", "2026-W35")[0] == "2026-W34"


def test_직전_주가_없으면_그_전으로_되짚는다(snap_dir):
    _write("2026-W33", "cu")  # W34 없음
    assert snapshot.previous_available("cu", "2026-W35")[0] == "2026-W33"


def test_상한을_넘으면_없는_것으로_본다(snap_dir):
    from pipeline import weeks
    _write(weeks.shift("2026-W35", -(snapshot.MAX_LOOKBACK_WEEKS + 1)), "cu")
    assert snapshot.previous_available("cu", "2026-W35") == (None, None)


def test_소스별로_따로_본다(snap_dir):
    """한 소스가 실패해 이월된 주가 있어도 다른 소스에 영향이 없어야 한다 (2.3)."""
    _write("2026-W34", "cu")
    _write("2026-W33", "orion")
    assert snapshot.previous_available("cu", "2026-W35")[0] == "2026-W34"
    assert snapshot.previous_available("orion", "2026-W35")[0] == "2026-W33"


def test_diff와_snapshot이_같은_주차를_본다(snap_dir):
    """셋이 서로 다른 주차를 보면 '무엇과 비교했는가'가 어긋난다."""
    from pipeline import diff
    _write("2026-W33", "cu")
    assert diff.MAX_LOOKBACK_WEEKS == snapshot.MAX_LOOKBACK_WEEKS
    assert snapshot.previous_available("cu", "2026-W35")[0] == "2026-W33"
