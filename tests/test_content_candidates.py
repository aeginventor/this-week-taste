"""콘텐츠 후보를 잘못 출시·복제하거나 비공개 검토 메모를 발행하는 경계를 검사한다."""
from copy import deepcopy
import json

import pytest

from pipeline import content, paths, publish

WEEK = "2026-W37"


def candidate():
    return {"id": "sample-drink", "review": {
        "decision": "include", "reason": "구체적인 구매·신제품 설명을 읽었다",
        "history": "이전 관측의 동일 제품을 찾지 못했다", "reviewed_by": "AI",
    }, "evidence": [{"url": "https://example.test/review", "access": "body",
                       "origin_group": "independent-purchase", "note": "상품명과 판매처를 확인"}],
        "product": {"source_id": "sample", "external_id": "content-drink", "name": "테스트 음료",
                    "brand": "테스트", "channel": "convenience", "price": None,
                    "source_url": "https://example.test/review", "source_name": "개인 후기",
                    "release_status": "released", "tags": []}}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CANDIDATES_DIR", tmp_path / "candidates")
    monkeypatch.setattr(publish, "WEEKS_DIR", tmp_path / "weeks")
    monkeypatch.setattr(publish, "PUBLISHED_DIR", tmp_path / "published")
    return tmp_path


def write(*entries):
    p = content.candidate_path(WEEK)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"version": 1, "week": WEEK, "reviewed_at": "2026-09-10T15:00:00+09:00",
                            "entries": list(entries)}, ensure_ascii=False))


def test_nonofficial_candidate_can_publish_without_invented_date_or_private_notes(isolated):
    row = candidate()
    row["raw_text"] = "작성자 원문을 복제하지 않는다"
    write(row)
    publish.merge(WEEK)
    payload = json.loads(publish.week_path(WEEK).read_text())
    item = payload["items"][0]
    assert item["name"] == "테스트 음료"
    assert "release_date" not in item
    assert "review" not in item and "evidence" not in item and "raw_text" not in item
    assert "removed" not in payload
    assert payload["sources"] == ["sample"]


def test_only_included_entries_are_published(isolated):
    row = candidate()
    hold = {"id": "ambiguous", "review": {"decision": "hold", "reason": "규격 미상"}}
    write(row, hold)
    items, report = content.load(WEEK, [])
    assert len(items) == 1 and report["held"] == 1


@pytest.mark.parametrize("field,value", [("price", True), ("price", "2000"), ("tags", "간식"),
                                          ("release_date", "2026-02-30"), ("channel", "unknown")])
def test_invalid_external_fields_are_rejected(isolated, field, value):
    row = candidate()
    row["product"][field] = value
    write(row)
    with pytest.raises(ValueError):
        content.load(WEEK, [])


def test_search_summary_alone_does_not_become_read_source(isolated):
    row = candidate()
    row["evidence"][0]["access"] = "search_only"
    write(row)
    with pytest.raises(ValueError, match="읽지 않았다"):
        content.load(WEEK, [])


def test_date_requires_explicit_basis_and_released_date_belongs_to_issue_week(isolated):
    row = candidate()
    row["product"]["release_date"] = "2026-09-08"
    write(row)
    with pytest.raises(ValueError, match="출시일 근거"):
        content.load(WEEK, [])
    row["review"]["date_basis"] = "본문이 9월 8일 출시라고 명시"
    write(row)
    assert content.load(WEEK, [])[0][0]["release_date"] == "2026-09-08"
    row["product"]["release_date"] = "2026-09-01"
    write(row)
    with pytest.raises(ValueError, match="이번 주 출시"):
        content.load(WEEK, [])


def test_upcoming_can_be_undated_but_cannot_use_past_date(isolated):
    row = candidate()
    row["product"]["release_status"] = "upcoming"
    write(row)
    assert "release_date" not in content.load(WEEK, [])[0][0]
    row["product"]["release_date"] = "2026-09-09"
    row["review"]["date_basis"] = "검토할 날짜 주장"
    write(row)
    with pytest.raises(ValueError, match="지난 예정일"):
        content.load(WEEK, [])


def test_duplicate_ids_fail_before_existing_public_file_is_replaced(isolated):
    row = candidate()
    write(row)
    publish.merge(WEEK)
    original = publish.week_path(WEEK).read_bytes()
    write(row, deepcopy(row))
    with pytest.raises(ValueError, match="ID 중복"):
        publish.merge(WEEK)
    assert publish.week_path(WEEK).read_bytes() == original


def test_repeated_content_keeps_first_seen_from_previous_publication(isolated):
    write(candidate())
    publish.WEEKS_DIR.mkdir()
    (publish.WEEKS_DIR / "2026-W36.json").write_text(json.dumps({"items": [
        {"id": "sample--content-drink", "first_seen": "2026-W36"}]}))
    publish.merge(WEEK)
    assert json.loads(publish.week_path(WEEK).read_text())["items"][0]["first_seen"] == "2026-W36"


def test_catalog_connection_is_explicit_and_preserves_original_identity(isolated):
    row = candidate()
    catalog_item = {"id": "old-public-id", "source_id": "sample", "external_id": "007",
                    "first_seen": "2026-W35", "name": "목록 원문 이름"}
    row["catalog_id"] = "old-public-id"
    row["review"]["match_basis"] = "브랜드·규격·사진으로 해당 원본 항목을 대조"
    write(row)
    items, report = content.load(WEEK, [catalog_item])
    assert items[0]["id"] == "old-public-id" and items[0]["external_id"] == "007"
    assert items[0]["name"] == "목록 원문 이름" and report["catalog_matches"] == 1
    row["product"]["source_id"] = "another"
    write(row)
    with pytest.raises(ValueError, match="연결할 카탈로그"):
        content.load(WEEK, [catalog_item])


def test_catalog_exclusion_requires_exact_current_item(tmp_path, monkeypatch):
    from pipeline import content
    import json
    import pytest
    path = tmp_path / '2026-W37.json'
    monkeypatch.setattr(content, 'candidate_path', lambda week: path)
    item = {'id': 'cu--1', 'name': '포도', 'source_id': 'cu', 'source_url': 'https://example.com/1'}
    row = {**item, 'reason': '신선 원물', 'reviewed_by': 'AI', 'evidence': '저장된 공식 상세의 과일 태그와 설명 확인'}
    path.write_text(json.dumps({'catalog_exclusions': [row]}))
    assert content.exclusions('2026-W37', [item]) == {'cu--1'}
    with pytest.raises(ValueError, match='현재 상품과 다르다'):
        content.exclusions('2026-W37', [{**item, 'name': '포도주스'}])
    path.write_text(json.dumps({'catalog_exclusions': [row, row]}))
    with pytest.raises(ValueError):
        content.exclusions('2026-W37', [item])
