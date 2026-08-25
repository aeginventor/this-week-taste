"""상세 보강의 실패 경로 (CLAUDE.md 3장·6장).

11장이 "`enrich.py`의 실패 처리 — 271/271 성공이라 실패 경로 미검증"으로
적어둔 자리다.

**보강은 있으면 좋은 것이지 발행을 막을 이유가 아니다.** 한 건이 실패했다고 그 주가
통째로 죽으면 안 되고, 반대로 실패가 조용히 묻혀도 안 된다 — 매주 조금씩 늘어나는
실패를 아무도 못 보게 된다.

여기서 지키는 것은 셋이다: 실패해도 나머지가 보강되는가, 실패한 항목이 **원본으로
남는가**(빈 설명문으로 덮이지 않는가), 실패가 기록에 남는가.
"""

import json

import pytest

from pipeline import diff, enrich
from scrapers import base

WEEK = "2026-W35"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(diff, "DIFF_DIR", tmp_path / "diffs")
    monkeypatch.setattr(enrich, "ENRICHED_DIR", tmp_path / "enriched")
    monkeypatch.setattr(base, "Session", lambda *a, **k: object())
    return tmp_path


def _write_diff(dirs, source_id, added):
    path = diff.DIFF_DIR / WEEK / f"{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"added": added}, ensure_ascii=False), encoding="utf-8")


def _items(n, **extra):
    return [{"external_id": str(i), "name": f"제품{i}", "description": None,
             "tags": [], **extra} for i in range(n)]


def _saved(source_id="cu"):
    return json.loads(enrich.enriched_path(WEEK, source_id).read_text(encoding="utf-8"))


def test_한_건이_실패해도_나머지는_보강된다(dirs, monkeypatch, caplog):
    def flaky(session, key, *, week):
        if key == "2":
            raise base.FetchError("타임아웃")
        return {"name": f"제품{key}", "description": f"설명{key}", "tags": []}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: flaky)
    _write_diff(dirs, "cu", _items(5))

    with caplog.at_level("ERROR"):
        enrich.run("cu", WEEK)

    saved = _saved()
    assert set(saved) == {"0", "1", "3", "4"}
    assert saved["0"]["description"] == "설명0"
    # 실패한 항목은 **아예 빠진다.** 빈 설명문으로 들어가면 curate가 그것을
    # "설명문 없음"이 아니라 "빈 설명문"으로 읽어 blurb를 지어낼 여지가 생긴다.
    assert "2" not in saved


def test_실패는_조용히_넘어가지_않는다(dirs, monkeypatch, caplog):
    def always_fail(session, key, *, week):
        raise base.FetchError("타임아웃")

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: always_fail)
    _write_diff(dirs, "cu", _items(3))

    with caplog.at_level("ERROR"):
        enrich.run("cu", WEEK)

    assert caplog.text.count("상세 조회 실패") == 3
    assert _saved() == {}


def test_전부_실패해도_예외를_던지지_않는다(dirs, monkeypatch):
    """여기서 예외가 나가면 그 소스의 발행이 통째로 멈춘다. 보강은 그럴 값이 아니다."""
    monkeypatch.setattr(enrich, "_detail_fetcher",
                        lambda sid: _raise_fetch_error)
    _write_diff(dirs, "cu", _items(3))
    enrich.run("cu", WEEK)                       # 예외 없이 끝나야 한다
    assert enrich.enriched_path(WEEK, "cu").exists()


def _raise_fetch_error(session, key, *, week):
    raise base.FetchError("타임아웃")


def test_이름이_다르면_보강하지_않는다(dirs, monkeypatch, caplog):
    """목록과 상세의 이름이 다르면 **키 매핑이 틀린 것**이다.

    그대로 보강하면 다른 제품의 설명문이 붙는다 — 예외 없이 조용히 틀린다.
    """
    def wrong_product(session, key, *, week):
        return {"name": "전혀 다른 제품", "description": "남의 설명", "tags": []}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: wrong_product)
    _write_diff(dirs, "cu", _items(2))

    with caplog.at_level("ERROR"):
        enrich.run("cu", WEEK)

    assert _saved() == {}
    assert "이름 불일치" in caplog.text


def test_external_id가_없으면_건너뛴다(dirs, monkeypatch, caplog):
    fetched = []

    def spy(session, key, *, week):
        fetched.append(key)
        return {"name": "제품0", "description": "설명", "tags": []}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: spy)
    _write_diff(dirs, "cu", [
        {"external_id": None, "name": "키 없는 제품", "description": None, "tags": []},
        {"external_id": "0", "name": "제품0", "description": None, "tags": []},
    ])

    with caplog.at_level("WARNING"):
        enrich.run("cu", WEEK)

    assert fetched == ["0"]
    assert "external_id가 없어" in caplog.text


# ── 목록이 준 것을 보존하는가 (4장의 tags 계약) ────────────────────

def test_상세가_태그를_안_주면_목록의_태그를_지킨다(dirs, monkeypatch):
    """배스킨라빈스가 이 경우다 — 태그는 목록이, 설명문은 상세가 준다.

    상세 결과로 통째로 덮으면 스냅샷이 이미 가진 태그가 사라진다.
    """
    def detail_without_tags(session, key, *, week):
        return {"name": f"제품{key}", "description": "상세 설명", "tags": []}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: detail_without_tags)
    _write_diff(dirs, "baskinrobbins",
                [{"external_id": "p1", "name": "제품p1", "description": None,
                  "tags": ["크림치즈", "조청카라멜"]}])

    enrich.run("baskinrobbins", WEEK)

    saved = _saved("baskinrobbins")
    assert saved["p1"]["description"] == "상세 설명"
    assert saved["p1"]["tags"] == ["크림치즈", "조청카라멜"]


def test_상세가_태그를_주면_그것을_쓴다(dirs, monkeypatch):
    """던킨이 이 경우다 — 설명문과 태그가 둘 다 상세에 있다."""
    def detail_with_tags(session, key, *, week):
        return {"name": f"제품{key}", "description": "설명", "tags": ["글레이즈드"]}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: detail_with_tags)
    _write_diff(dirs, "dunkin",
                [{"external_id": "p536", "name": "제품p536",
                  "description": None, "tags": []}])

    enrich.run("dunkin", WEEK)
    assert _saved("dunkin")["p536"]["tags"] == ["글레이즈드"]


def test_목록이_설명문을_주면_태그도_함께_넘어간다(dirs, monkeypatch):
    """상세를 아예 안 긁는 경로. 여기서 태그를 떨어뜨리면 조용히 사라진다."""
    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: None)
    _write_diff(dirs, "kyochon",
                [{"external_id": "1", "name": "제품", "description": "목록 설명",
                  "tags": ["태그"]}])

    enrich.run("kyochon", WEEK)

    saved = _saved("kyochon")
    assert saved["1"] == {"description": "목록 설명", "tags": ["태그"]}
