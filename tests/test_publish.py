"""발행 단계의 두 가지 불변식.

1. `id`는 first_seen 주차에 확정되고 그 뒤로 절대 바뀌지 않는다
2. 단종 항목은 지난주 발행본에서 이월된다 (이번 주 스냅샷에 없으므로 다른 경로가 없다)

id가 바뀌면 아카이브 URL이 깨지고 diff가 같은 제품을 "단종 1건 + 신상 1건"으로 오탐한다.
"""

import json

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


# ── 발행이 무엇을 보고 발행했는가 (ADR-0011) ──────────────────────────────
#
# 수집은 봇이, 발행은 사람이 따로 돌린다. 같은 주차를 다시 수집하면 발행물이 근거로 삼은
# 카탈로그가 조용히 교체되는데, 이 값이 없으면 어긋났다는 것 자체를 알 수 없다.
# 2026-W35가 실제로 그랬다 — 14:24 발행, 15:30 재수집.

def _snap(week, source_id, scraped_at, **extra):
    from pipeline import snapshot
    path = snapshot.snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"week": week, "source_id": source_id, "scraped_at": scraped_at,
         "count": 1, "items": [], **extra}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    from pipeline import snapshot
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path


def _report(week="2026-W36", source_id="homeplus", previous_week="2026-W35"):
    result = {"added": [], "removed": [], "counts": {}, "previous_week": previous_week,
              "gap_weeks": 1}
    return publish._source_report(week, source_id, result, [])


def test_리포트가_근거로_쓴_스냅샷_시각을_남긴다(snap_dir):
    _snap("2026-W36", "homeplus", "2026-08-31T10:00:00+09:00")
    _snap("2026-W35", "homeplus", "2026-08-24T15:35:31+09:00")

    provenance = _report()["snapshot"]

    assert provenance["scraped_at"] == "2026-08-31T10:00:00+09:00"
    assert provenance["previous_week"] == "2026-W35"
    assert provenance["previous_scraped_at"] == "2026-08-24T15:35:31+09:00"


def test_이월본이_아니면_held_from을_싣지_않는다(snap_dir):
    # 해당 없는 자리에 빈 값을 실으면 나중에 의미 있는 값으로 오독된다 (7장).
    _snap("2026-W36", "homeplus", "2026-08-31T10:00:00+09:00")
    assert "held_from" not in _report()["snapshot"]


def test_이월본이면_출처_주차를_싣는다(snap_dir):
    _snap("2026-W36", "homeplus", "2026-08-24T15:35:31+09:00", held_from="2026-W35")
    assert _report()["snapshot"]["held_from"] == "2026-W35"


def test_범위_밖_항목은_이름까지_리포트에_남는다(snap_dir):
    # 건수만 남기면 무엇이 사라졌는지 알 수 없다. 오판정은 여기서만 눈에 띈다.
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    dropped = [{"external_id": "a", "name": "데일리)아오리사과2입(팩)"},
               {"external_id": "b", "name": "HB)카라카라오렌지6입"}]
    result = {"added": [], "removed": [], "counts": {}, "previous_week": None,
              "gap_weeks": 1}
    report = publish._source_report("2026-W36", "cu", result, [], out_of_scope=dropped)
    assert report["out_of_scope"]["count"] == 2
    assert "HB)카라카라오렌지6입" in report["out_of_scope"]["names"]


def test_범위_밖이_없으면_키를_싣지_않는다(snap_dir):
    # 해당 없는 자리에 0을 실으면 "판정이 돌았는데 0건"과 "판정이 안 돌았다"를 못 가른다.
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    result = {"added": [], "removed": [], "counts": {}, "previous_week": None,
              "gap_weeks": 1}
    assert "out_of_scope" not in publish._source_report("2026-W36", "cu", result, [])


# ── 지표 4: 지난주 발행한 신상이 사라졌는가 (ADR-0015) ──────────────
#
# `status: discontinued`로 발행하던 것을 지표로 옮겼다. 틀려도 예외가 안 나고
# 리포트에 숫자로만 나오는 자리라 테스트가 필요하다 (7장).


def _published(source_id, external_id, name):
    return {"source_id": source_id, "external_id": external_id, "name": name,
            "id": f"{source_id}--{external_id}"}


def test_지난주_발행본이_없으면_키를_싣지_않는다(snap_dir):
    """첫 발행 주에는 잴 수가 없다. 0을 실으면 "사라진 것이 없다"로 오독된다 (7장)."""
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    result = {"added": [], "removed": [{"external_id": "a"}], "counts": {},
              "previous_week": None, "gap_weeks": 1}

    report = publish._source_report("2026-W36", "cu", result, [], previous_published={})

    assert "published_then_gone" not in report


def test_지난주_발행한_신상이_사라지면_이름까지_남는다(snap_dir):
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    previous = {"17620": _published("cu", "17620", "백종원 매콤제육덮밥"),
                "17621": _published("cu", "17621", "삼각김밥 참치마요")}
    result = {"added": [], "removed": [{"external_id": "17620"}], "counts": {},
              "previous_week": "2026-W35", "gap_weeks": 1}

    gone = publish._source_report("2026-W36", "cu", result, [],
                                  previous_published=previous)["published_then_gone"]

    assert gone == {"previous_published": 2, "gone": 1,
                    "names": ["백종원 매콤제육덮밥"]}


def test_모수는_카탈로그가_아니라_발행본이다(snap_dir):
    """⚠️ 이 지표의 핵심이다. **우리가 신상이라고 실은 적 없는 항목은 세지 않는다.**

    W33→W35 diff에서 CU의 removed가 431건이었지만 W35가 첫 발행이라 그중 발행된
    것은 0건이었다. 카탈로그에서 오래된 상품이 내려간 것은 우리 판정의 옳고 그름과
    무관하다 — 그걸 세면 지표가 상품 수명 이야기가 되어버린다.
    """
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    previous = {"17620": _published("cu", "17620", "백종원 매콤제육덮밥")}
    # 사라진 것은 셋인데 그중 지난주 발행본에 있던 것은 하나뿐이다.
    result = {"added": [],
              "removed": [{"external_id": "17620"}, {"external_id": "99998"},
                          {"external_id": "99999"}],
              "counts": {}, "previous_week": "2026-W35", "gap_weeks": 1}

    gone = publish._source_report("2026-W36", "cu", result, [],
                                  previous_published=previous)["published_then_gone"]

    assert gone["previous_published"] == 1
    assert gone["gone"] == 1


def test_아무것도_안_사라져도_키를_싣는다(snap_dir):
    """`out_of_scope`와 반대다. 모수가 있으면 0은 **의미 있는 0**이다 —
    "지난주 신상이 하나도 안 사라졌다"는 좋은 소식이지 미계산이 아니다."""
    _snap("2026-W36", "cu", "2026-08-31T10:00:00+09:00")
    previous = {"17620": _published("cu", "17620", "백종원 매콤제육덮밥")}
    result = {"added": [], "removed": [], "counts": {},
              "previous_week": "2026-W35", "gap_weeks": 1}

    gone = publish._source_report("2026-W36", "cu", result, [],
                                  previous_published=previous)["published_then_gone"]

    assert gone == {"previous_published": 1, "gone": 0, "names": []}


def test_라벨도_단조키도_없는_소스에서_계산된다(snap_dir):
    """**이 지표를 만든 이유다.** 홈플러스는 NEW 라벨도 단조 증가 키도 없어서
    지표 2·3이 둘 다 안 실린다. 건수 2위인데 채점을 못 하고 있었다."""
    _snap("2026-W36", "homeplus", "2026-08-31T10:00:00+09:00")
    previous = {"070234705": _published("homeplus", "070234705", "냉동만두")}
    result = {"added": [], "removed": [{"external_id": "070234705"}], "counts": {},
              "previous_week": "2026-W35", "gap_weeks": 1}

    report = publish._source_report("2026-W36", "homeplus", result, [],
                                    previous_published=previous)

    assert "monotonic_id" not in report          # 단조 키가 없다
    assert report["published_then_gone"]["gone"] == 1
