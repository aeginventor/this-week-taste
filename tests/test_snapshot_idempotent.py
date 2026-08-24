"""한 주차의 스냅샷은 한 번만 뜬다 (ADR-0011).

틀려도 예외가 나지 않고 **다른 카탈로그가 근거로 쓰인다.** 7장 2번 그대로다.
실제로 2026-W35가 그랬다 — 14:24에 발행하고 15:30에 봇이 다시 수집해, 발행물이 참조한
스냅샷이 디스크에서 조용히 교체됐다. 그때는 차이가 0이라 무해했다.
"""

import json
import types

import pytest

from pipeline import snapshot

WEEK = "2026-W35"


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path


@pytest.fixture
def fake_source(monkeypatch):
    """fetch 호출 횟수를 세는 가짜 스크래퍼. 몇 번 긁었는지가 이 테스트의 관심사다."""
    calls = []

    def fetch(*, week):
        calls.append(week)
        return [{"external_id": "x1", "name": "가", "category_raw": None,
                 "scraped_at": f"2026-08-24T15:30:0{len(calls)}+09:00"}]

    module = types.SimpleNamespace(fetch=fetch, CATEGORIES={}, calls=calls)
    monkeypatch.setattr(snapshot, "_scraper_for", lambda source_id: module)
    return module


def _write(week, source_id, **extra):
    path = snapshot.snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"week": week, "source_id": source_id, "scraped_at": "2026-08-24T10:00:00+09:00",
         "count": 1, "items": [{"external_id": "x1", "name": "가"}], **extra},
        ensure_ascii=False), encoding="utf-8")
    return path


def test_스냅샷이_이미_있으면_긁지_않는다(snap_dir, fake_source):
    _write(WEEK, "cu")
    snapshot.take("cu", WEEK)
    assert fake_source.calls == []


def test_재사용할_때_파일이_바뀌지_않는다(snap_dir, fake_source):
    path = _write(WEEK, "cu")
    before = path.read_text(encoding="utf-8")
    snapshot.take("cu", WEEK)
    assert path.read_text(encoding="utf-8") == before


def test_refresh를_주면_다시_긁는다(snap_dir, fake_source):
    _write(WEEK, "cu")
    snapshot.take("cu", WEEK, refresh=True)
    assert fake_source.calls == [WEEK]
    saved = json.loads(snapshot.snapshot_path(WEEK, "cu").read_text(encoding="utf-8"))
    assert saved["scraped_at"] == "2026-08-24T15:30:01+09:00"


def test_이월본은_재사용하지_않고_다시_긁는다(snap_dir, fake_source):
    # 이월본(2.4)은 "이번 주 데이터가 없다"는 뜻이다. 그걸 굳히면 지난주 카탈로그가
    # 이번 주의 최종 스냅샷이 된다.
    _write(WEEK, "cu", held_from="2026-W33")
    snapshot.take("cu", WEEK)
    assert fake_source.calls == [WEEK]
    saved = json.loads(snapshot.snapshot_path(WEEK, "cu").read_text(encoding="utf-8"))
    assert "held_from" not in saved


def test_스냅샷이_없으면_당연히_긁는다(snap_dir, fake_source):
    snapshot.take("cu", WEEK)
    assert fake_source.calls == [WEEK]


def test_다른_소스의_스냅샷은_영향을_주지_않는다(snap_dir, fake_source):
    # 격리 단위는 소스다 (2.3).
    _write(WEEK, "homeplus")
    snapshot.take("cu", WEEK)
    assert fake_source.calls == [WEEK]


def test_cli의_refresh_플래그가_take까지_전달된다(snap_dir, fake_source):
    _write(WEEK, "cu")
    assert snapshot.main(["--source", "cu", "--week", WEEK]) == 0
    assert fake_source.calls == []
    assert snapshot.main(["--source", "cu", "--week", WEEK, "--refresh"]) == 0
    assert fake_source.calls == [WEEK]
