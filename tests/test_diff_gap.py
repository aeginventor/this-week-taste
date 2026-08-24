"""건너뛴 주차 처리. 틀려도 예외가 안 나고 그냥 숫자가 어긋난다 (CLAUDE.md 7장).

실제로 이것 때문에 2026-W34를 놓친 뒤 W35가 발행되지 않았다.
"""

import json

import pytest

from pipeline import diff, weeks


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """스냅샷·diff 경로를 tmp로 돌린다. 진짜 data/ 를 건드리지 않기 위해."""
    from pipeline import snapshot
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(diff, "DIFF_DIR", tmp_path / "diffs")
    return tmp_path


def _write_snapshot(data_dir, week, source_id, names):
    path = data_dir / "snapshots" / week / f"{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [{"source_id": source_id, "external_id": f"id{i}", "name": n,
              "price": 1000 + i, "category_raw": "간편식사", "description": None,
              "image_url": None, "source_url": f"https://x/{i}",
              "alt_ids": {}, "scraped_at": "2026-08-24T09:00:00+09:00"}
             for i, n in enumerate(names)]
    path.write_text(json.dumps({"week": week, "source_id": source_id,
                                "count": len(items), "items": items},
                               ensure_ascii=False), encoding="utf-8")


def test_직전_주가_있으면_그것과_비교하고_gap은_1(data_dir):
    _write_snapshot(data_dir, "2026-W34", "cu", ["김밥", "우유"])
    _write_snapshot(data_dir, "2026-W35", "cu", ["김밥", "우유", "샌드위치"])

    diff.run("cu", "2026-W35")
    result = json.loads((data_dir / "diffs" / "2026-W35" / "cu.json").read_text())

    assert result["previous_week"] == "2026-W34"
    assert result["gap_weeks"] == 1
    assert result["baseline"] is False
    assert result["counts"]["added"] == 1


def test_한_주_건너뛰면_그_전_주와_비교하고_gap은_2(data_dir):
    """이게 W35에서 실제로 터진 경우다. 고치기 전에는 baseline으로 빠졌다."""
    _write_snapshot(data_dir, "2026-W33", "cu", ["김밥", "우유"])
    # W34 없음
    _write_snapshot(data_dir, "2026-W35", "cu", ["김밥", "우유", "샌드위치"])

    diff.run("cu", "2026-W35")
    result = json.loads((data_dir / "diffs" / "2026-W35" / "cu.json").read_text())

    assert result["baseline"] is False, "직전 주가 없다고 기준선으로 빠지면 안 된다"
    assert result["previous_week"] == "2026-W33"
    assert result["gap_weeks"] == 2
    assert result["counts"]["added"] == 1


def test_되짚기_상한을_넘으면_기준선으로_둔다(data_dir):
    """너무 오래된 것과 비교해놓고 '이번 주 신상'이라 부를 수 없다."""
    old = weeks.shift("2026-W35", -(diff.MAX_LOOKBACK_WEEKS + 1))
    _write_snapshot(data_dir, old, "cu", ["김밥"])
    _write_snapshot(data_dir, "2026-W35", "cu", ["김밥", "우유"])

    diff.run("cu", "2026-W35")
    result = json.loads((data_dir / "diffs" / "2026-W35" / "cu.json").read_text())

    assert result["baseline"] is True
    assert result["previous_week"] is None
    assert result["counts"]["added"] == 0, "기준선이면 전량을 신상으로 내보내지 않는다"


def test_gap은_연도_경계를_넘어도_맞는다():
    """2026-W01의 2주 전은 2025-W52다. 주차 숫자를 빼면 -1이 나온다."""
    assert diff._gap("2025-W52", "2026-W01") == 1
    assert diff._gap("2025-W51", "2026-W01") == 2
