"""bhc 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  bhc_products_1.json   CHICKEN 33건. `isNew`가 `"Y"`인 항목과 `"N"`인 항목이 섞여 있다
  bhc_products_47.json  COLPOP 11건. **전부 앞 카테고리와 겹친다** — 중복 제거의 근거

`isNew` 테스트가 이 파일의 핵심이다. `"N"`도 파이썬에서는 참이라, 판정이 뒤집혀도
"라벨이 다 붙어 있네"로 보이고 아무 예외도 나지 않는다.
"""

import json
from pathlib import Path

import pytest

from scrapers import bhc

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, code: str):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    items, skipped = bhc.parse_products(payload, code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def chicken():
    return _parse("bhc_products_1.json", "1")


@pytest.fixture(scope="module")
def colpop():
    return _parse("bhc_products_47.json", "47")


def test_목록_건수(chicken, colpop):
    assert len(chicken) == 33
    assert len(colpop) == 11


def test_항목_모양(chicken):
    item = next(i for i in chicken if i["external_id"] == "104000")
    assert item["source_id"] == "bhc"
    assert item["alt_ids"] == {"product_cd": "104000"}
    assert item["category_raw"] == "CHICKEN"
    assert item["price"] is None          # options가 전부 비어 있다
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == "https://www.bhc.co.kr/menu/1"
    assert item["image_url"].startswith("https://home-img.bhc.co.kr/")


def test_제품명의_줄바꿈을_접는다(chicken):
    """주의 2번. `"뿌링클(반)+맛초킹라이스\\n+콜라500ml\\n"` 형태로 온다."""
    item = next(i for i in chicken if i["external_id"] == "104000")
    assert item["name"] == "뿌링클(반)+맛초킹라이스 +콜라500ml"
    assert all("\n" not in i["name"] and not i["name"].endswith(" ") for i in chicken)


def test_목록이_설명문을_준다(chicken):
    """이 소스가 `detail: False`인 근거."""
    assert sum(1 for i in chicken if i["description"]) >= 30


def test_시리즈_태그를_tags에_싣는다(chicken):
    """주의 4번. `cateNm`은 카테고리가 아니라 상품별 시리즈 태그의 배열이다."""
    item = next(i for i in chicken if i["external_id"] == "104000")
    assert item["tags"] == ["뿌링클"]
    assert all(isinstance(i["tags"], list) for i in chicken)


# ── isNew 함정 (주의 1번) ──────────────────────────────────────

def test_isNew는_문자열이라_Y만_참이다():
    """`"N"`도 파이썬에서는 참이다. 이 함수가 없으면 전건이 신상이 된다."""
    assert bhc.is_yes("Y") is True
    assert bhc.is_yes("y") is True
    assert bhc.is_yes("N") is False       # ← truthy 판정이면 여기서 터진다
    assert bhc.is_yes("") is False
    assert bhc.is_yes(None) is False


def test_신상_라벨이_전건_참이_아니다(chicken):
    """판정이 뒤집혀도 예외가 안 나므로 여기서 숫자로 못 박는다."""
    flagged = sum(1 for i in chicken if i["_labels"]["new"])
    assert 0 < flagged < len(chicken), f"전건 또는 0건이 신상으로 잡혔다: {flagged}/{len(chicken)}"


def test_best와_limited도_같은_방식이다(chicken):
    for item in chicken:
        assert isinstance(item["_labels"]["best"], bool)
        assert isinstance(item["_labels"]["limited"], bool)


# ── 중복 제거 (주의 3번) ───────────────────────────────────────

def test_COLPOP은_전부_앞_카테고리와_겹친다(chicken, colpop):
    """이 소스에서 중복이 가장 큰 자리다(158건 중 45건).

    `BOOTSTRAP_COUNTS`의 COLPOP이 0인 것이 오류가 아님을 여기서 못 박는다.
    """
    kept = bhc.dedupe(chicken + colpop)
    keys = [i["external_id"] for i in kept]
    assert len(keys) == len(set(keys))
    assert bhc.BOOTSTRAP_COUNTS["47"] == 0


def test_앞의_카테고리가_분류를_가져간다(chicken, colpop):
    overlap = {i["external_id"] for i in chicken} & {i["external_id"] for i in colpop}
    if not overlap:
        pytest.skip("픽스처에 겹치는 항목이 없다")
    kept = {i["external_id"]: i for i in bhc.dedupe(chicken + colpop)}
    assert all(kept[k]["category_raw"] == "CHICKEN" for k in overlap)


def test_같은_코드에_이름이_다르면_죽는다():
    with pytest.raises(bhc.ParseError, match="이름이 다르다"):
        bhc.dedupe([{"external_id": "1", "name": "가"},
                    {"external_id": "1", "name": "나"}])


def test_봉투가_바뀌면_시끄럽게_죽는다():
    with pytest.raises(bhc.ParseError, match="body가 없다"):
        bhc.parse_products({"status": "OK"}, "1", scraped_at=SCRAPED_AT)


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        bhc.parse_products({"body": []}, "99", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(bhc.BOOTSTRAP_COUNTS) == set(bhc.CATEGORIES)
    assert sum(bhc.BOOTSTRAP_COUNTS.values()) == 113
