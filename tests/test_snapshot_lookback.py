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


def _write(week, source_id, count=10, **extra):
    path = snapshot.snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"week": week, "source_id": source_id,
                                "count": count, "items": [], **extra}), encoding="utf-8")


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

# ── 이월은 빈 자리만 채운다 (2.4) ──────────────────────────────────────────
#
# `_hold_previous`가 이번 주 파일을 무조건 덮어쓰고 있었다. 이상 상황에서 이월이 도는데
# 이번 주에 이미 정상 스냅샷이 있으면, **검증을 통과했던 카탈로그가 지난주 것으로
# 되돌아간다.** 조용하고, 되돌린 흔적은 `held_from` 하나뿐이다.

def test_이번_주_정상_스냅샷이_있으면_이월하지_않는다(snap_dir):
    _write("2026-W33", "cu")
    _write("2026-W35", "cu")
    before = snapshot.snapshot_path("2026-W35", "cu").read_text(encoding="utf-8")

    assert snapshot._hold_previous("2026-W35", "cu") is True

    after = snapshot.snapshot_path("2026-W35", "cu").read_text(encoding="utf-8")
    assert after == before
    assert "held_from" not in json.loads(after)


def test_이번_주_스냅샷이_없으면_이월한다(snap_dir):
    _write("2026-W33", "cu")
    assert snapshot._hold_previous("2026-W35", "cu") is True
    saved = json.loads(snapshot.snapshot_path("2026-W35", "cu").read_text(encoding="utf-8"))
    assert saved["held_from"] == "2026-W33"
    assert saved["week"] == "2026-W35"


def test_이월본_자리에는_다시_이월한다(snap_dir):
    # 이월본은 "이번 주 데이터가 없다"는 뜻이므로 지킬 것이 없다.
    _write("2026-W33", "cu")
    _write("2026-W35", "cu", held_from="2026-W32")
    assert snapshot._hold_previous("2026-W35", "cu") is True
    saved = json.loads(snapshot.snapshot_path("2026-W35", "cu").read_text(encoding="utf-8"))
    assert saved["held_from"] == "2026-W33"
