"""소스별 부분 산출물 → 병합. 틀려도 예외가 안 난다 (CLAUDE.md 7장).

실제로 고치기 전에는 `make week-all`이 소스 4개를 차례로 덮어써서
**마지막 소스 하나만** 발행됐다. 아무 경고도 없었다.
"""

import json

import pytest

from pipeline import alert, publish


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "PUBLISHED_DIR", tmp_path / "published")
    monkeypatch.setattr(publish, "WEEKS_DIR", tmp_path / "weeks")
    return tmp_path


def _item(source_id, external_id, name):
    return {
        "id": publish.make_id(source_id, external_id), "week": "2026-W35",
        "source_id": source_id, "brand": source_id.upper(), "channel": "convenience",
        "name": name, "price": 1000, "category": "도시락", "tags": [], "blurb": None,
        "image_url": None, "source_url": f"https://x/{external_id}",
        "external_id": external_id, "alt_ids": {},
        "first_seen": "2026-W35", "last_seen": "2026-W35", "status": "active",
    }


def _write_part(dirs, source_id, items, discontinued=0):
    path = publish.PUBLISHED_DIR / "2026-W35" / f"{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "week": "2026-W35", "source_id": source_id,
        "generated_at": "2026-08-24T09:00:00+09:00",
        "counts": publish._counts(items, discontinued),
        "report": {"week": "2026-W35", "source_id": source_id, "added": len(items)},
        "items": items,
    }, ensure_ascii=False), encoding="utf-8")


def test_소스_넷이_모두_한_파일에_들어간다(dirs):
    """덮어쓰기 회귀 검사. 고치기 전에는 마지막 하나만 남았다."""
    _write_part(dirs, "cu", [_item("cu", "1", "김밥"), _item("cu", "2", "우유")])
    _write_part(dirs, "homeplus", [_item("homeplus", "070234705", "사과")])
    _write_part(dirs, "starbucks", [_item("starbucks", "SB1", "라떼")])
    _write_part(dirs, "orion", [_item("orion", "9", "초코파이")])

    publish.merge("2026-W35")
    merged = json.loads(publish.week_path("2026-W35").read_text())

    assert merged["counts"]["total"] == 5
    assert merged["sources"] == ["cu", "homeplus", "orion", "starbucks"]
    assert {i["source_id"] for i in merged["items"]} == {
        "cu", "homeplus", "orion", "starbucks"}


def test_소스가_달라도_external_id가_같으면_id는_갈린다(dirs):
    """CU의 gd_idx와 오리온의 goodsno가 둘 다 숫자라 실제로 겹칠 수 있다."""
    _write_part(dirs, "cu", [_item("cu", "1234", "김밥")])
    _write_part(dirs, "orion", [_item("orion", "1234", "초코파이")])

    publish.merge("2026-W35")
    merged = json.loads(publish.week_path("2026-W35").read_text())

    ids = sorted(i["id"] for i in merged["items"])
    assert ids == ["cu--1234", "orion--1234"], "소스가 다르면 id도 달라야 한다"
    assert len(set(ids)) == 2


def test_id가_진짜로_겹치면_발행을_멈춘다(dirs):
    """합치고 나서야 드러나는 충돌이다. 조용히 내보내면 아카이브 URL이 깨진다."""
    _write_part(dirs, "cu", [_item("cu", "1", "김밥")])
    _write_part(dirs, "cu2", [_item("cu", "1", "김밥(중복)")])

    with pytest.raises(alert.PipelineAnomaly):
        publish.merge("2026-W35")


def test_리포트는_소스별로_남는다(dirs):
    """소스마다 파일에 쓰면 서로 덮어써서 마지막 소스 지표만 남았다."""
    _write_part(dirs, "cu", [_item("cu", "1", "김밥")])
    _write_part(dirs, "orion", [_item("orion", "9", "초코파이")])

    publish.merge("2026-W35")
    report = json.loads((publish.WEEKS_DIR / "2026-W35.report.json").read_text())

    assert sorted(report["by_source"]) == ["cu", "orion"]
    assert report["totals"]["total"] == 2


def test_부분_산출물이_없으면_합치지_않는다(dirs):
    assert publish.merge("2026-W35") is None
