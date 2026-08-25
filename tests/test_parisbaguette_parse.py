"""파리바게뜨 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  parisbaguette_list_bread_p1.html    브레드 1페이지 100건. `data-total-count="170"`
  parisbaguette_list_kitchen_p1.html  간편식 27건 (한 페이지에 다 온다)
  parisbaguette_view_potato.html      상세 1건 (감자쫀떡)

브레드를 고른 이유: **이 소스에서 유일하게 두 페이지인 카테고리**다.
`data-total-count`(170)와 한 페이지 건수(100)가 다른 것이 여기서만 확인된다.
"""

from pathlib import Path

import pytest

from scrapers import parisbaguette as pb

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(name: str, slug: str):
    items, skipped = pb.parse_list(_load(name), slug, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def bread():
    return _parse("parisbaguette_list_bread_p1.html", "브레드")


@pytest.fixture(scope="module")
def kitchen():
    return _parse("parisbaguette_list_kitchen_p1.html", "퍼스트클래스키친")


def test_한_페이지는_최대_100건이다(bread, kitchen):
    assert len(bread) == pb.PAGE_SIZE == 100
    assert len(kitchen) == 27          # 한 페이지에 다 온다


def test_전체_건수를_소스가_알려준다(bread, kitchen):
    """`fetch_category`가 이 값으로 '페이지를 놓쳤는지'를 검사한다."""
    assert pb.parse_total(_load("parisbaguette_list_bread_p1.html")) == 170
    assert pb.parse_total(_load("parisbaguette_list_kitchen_p1.html")) == 27
    assert pb.parse_total("<div>없음</div>") is None


def test_항목_모양(bread):
    item = next(i for i in bread if i["name"] == "감자쫀떡(1개입)")
    assert item["source_id"] == "parisbaguette"
    assert item["external_id"] == "potato-chewy-rice-cake-1pcs"
    assert item["alt_ids"] == {"slug": "potato-chewy-rice-cake-1pcs"}
    assert item["category_raw"] == "브레드"
    assert item["price"] is None          # 가격을 주지 않는다
    assert item["description"] is None    # 설명문은 상세에 있다
    assert item["tags"] == []
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == (
        "https://www.paris.co.kr/product/potato-chewy-rice-cake-1pcs/")


def test_플레이스홀더가_아닌_이미지를_읽는다(bread):
    """주의 3번. 첫 `<img>`는 base64 플레이스홀더(`img.guide`)다."""
    assert all(i["image_url"] for i in bread)
    assert all(not i["image_url"].startswith("data:") for i in bread)
    assert all("cloudfront.net" in i["image_url"] for i in bread)


def test_슬러그를_디코딩한다():
    """주의 4번. 인코딩된 채로 키를 만들면 대소문자만 달라져도 다른 키가 된다."""
    assert pb.parse_slug("/product/potato-chewy-rice-cake-1pcs/") == \
        "potato-chewy-rice-cake-1pcs"
    assert pb.parse_slug(
        "https://www.paris.co.kr/product/%ed%95%ab%eb%8f%84%ea%b7%b8%eb%8f%84%eb%84%9b/"
    ) == "핫도그도넛"
    assert pb.parse_slug(None) is None
    assert pb.parse_slug("https://www.paris.co.kr/") is None


def test_슬러그가_키로_충분하다(bread, kitchen):
    """2026-08-25 실측 519건에서 중복 0건."""
    keys = [i["external_id"] for i in bread + kitchen]
    assert len(keys) == len(set(keys))
    assert all(not k.startswith("nh") for k in keys), "이름 해시로 떨어진 항목이 있다"


def test_카테고리_슬러그와_표시이름이_다르다():
    """주의 2번. `간편식`의 슬러그는 `퍼스트클래스키친`이다."""
    assert pb.CATEGORIES["퍼스트클래스키친"] == "간편식"
    assert pb.CATEGORIES["샌드위치-샐러드"] == "샌드위치/샐러드"


def test_상세_파싱():
    detail = pb.parse_detail(_load("parisbaguette_view_potato.html"))
    # 목록의 이름과 **정확히 같아야** enrich의 이름 대조를 통과한다.
    assert detail["name"] == "감자쫀떡(1개입)"
    assert detail["description"] == (
        "담백한 감자에 달콤 짭짜름한 버터를 더해 겉은 바삭하고 속은 쫀득한 감자쫀떡")
    # 태그는 상세에 없다. []를 주면 enrich가 스냅샷의 태그를 보존한다(4장).
    assert detail["tags"] == []


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리 슬러그"):
        pb.parse_list("<html></html>", "간편식", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(pb.BOOTSTRAP_COUNTS) == set(pb.CATEGORIES)
    assert sum(pb.BOOTSTRAP_COUNTS.values()) == 519
