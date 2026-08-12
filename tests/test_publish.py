"""발행 단계의 두 가지 불변식.

1. `id`는 first_seen 주차에 확정되고 그 뒤로 절대 바뀌지 않는다
2. 단종 항목은 지난주 발행본에서 이월된다 (이번 주 스냅샷에 없으므로 다른 경로가 없다)

id가 바뀌면 아카이브 URL이 깨지고 diff가 같은 제품을 "단종 1건 + 신상 1건"으로 오탐한다.
"""

import pytest

from pipeline import publish


def snapshot_item(external_id, name="샐)테스트샐러드", price=4800, barcode=None):
    return {
        "source_id": "cu",
        "external_id": external_id,
        "alt_ids": {k: v for k, v in (("barcode", barcode), ("gd_idx", external_id)) if v},
        "name": name,
        "price": price,
        "category_raw": "간편식사",
        "image_url": "https://cdn.example/x.jpg",
        "source_url": f"https://cu.bgfretail.com/product/view.do?gdIdx={external_id}",
        "scraped_at": "2026-08-11T09:00:00+09:00",
    }


def test_id_is_source_and_external_id():
    assert publish.make_id("cu", "17620") == "cu--17620"


def test_new_item_gets_id_and_first_seen_from_this_week():
    item = publish._publish_item(snapshot_item("17620"), week="2026-W33",
                                 source_id="cu", curated={}, previous=None)
    assert item["id"] == "cu--17620"
    assert item["first_seen"] == "2026-W33"
    assert item["last_seen"] == "2026-W33"
    assert item["status"] == "active"


def test_id_and_first_seen_are_carried_forward_never_recomputed():
    """지난주에 다른 규칙으로 만들어진 id도 그대로 이월한다."""
    previous = {"id": "cu--gd17620", "first_seen": "2026-W30"}
    item = publish._publish_item(snapshot_item("17620"), week="2026-W33",
                                 source_id="cu", curated={}, previous=previous)
    assert item["id"] == "cu--gd17620"      # 재계산하면 cu--17620이 됐을 것이다
    assert item["first_seen"] == "2026-W30"
    assert item["last_seen"] == "2026-W33"


def test_curated_fields_applied_but_name_is_never_touched():
    curated = {"17620": {"category": "샐러드", "tags": ["샐러드"], "blurb": "고소한 닭가슴살"}}
    item = publish._publish_item(snapshot_item("17620"), week="2026-W33",
                                 source_id="cu", curated=curated, previous=None)
    assert item["category"] == "샐러드"
    assert item["blurb"] == "고소한 닭가슴살"
    assert item["name"] == "샐)테스트샐러드"


def test_missing_curation_falls_back_to_source_category():
    item = publish._publish_item(snapshot_item("17620"), week="2026-W33",
                                 source_id="cu", curated={}, previous=None)
    assert item["category"] == "간편식사"
    assert item["blurb"] is None
    assert item["tags"] == []


def test_validate_rejects_duplicate_ids():
    items = [
        publish._publish_item(snapshot_item("17620"), week="2026-W33",
                              source_id="cu", curated={}, previous=None),
        publish._publish_item(snapshot_item("17620"), week="2026-W33",
                              source_id="cu", curated={}, previous=None),
    ]
    with pytest.raises(Exception, match="발행 스키마 검증 실패"):
        publish._validate(items, "2026-W33")


def test_validate_rejects_bad_week_format():
    items = [publish._publish_item(snapshot_item("17620"), week="2026-33",
                                   source_id="cu", curated={}, previous=None)]
    with pytest.raises(Exception, match="발행 스키마 검증 실패"):
        publish._validate(items, "2026-33")


def test_validate_rejects_missing_required_field():
    item = publish._publish_item(snapshot_item("17620"), week="2026-W33",
                                 source_id="cu", curated={}, previous=None)
    item["source_url"] = None
    with pytest.raises(Exception, match="발행 스키마 검증 실패"):
        publish._validate([item], "2026-W33")
