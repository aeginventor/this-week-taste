"""교촌 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  kyochon_list_chicken.html  치킨 69건. 가격이 전부 있다
  kyochon_list_liquor.html   문베어 수제맥주 6건. 가격이 없는 항목이 섞여 있다

두 탭을 다 두는 이유는 **가격 유무가 그 사이에서 갈리기 때문이다**(101건 중 92건).
가격이 있는 탭만 테스트하면 `parse_price`의 None 경로가 검증되지 않는다.
"""

from pathlib import Path

import pytest

from scrapers import kyochon

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, tab: str):
    markup = (FIXTURES / name).read_text(encoding="utf-8")
    items, skipped = kyochon.parse_list(markup, tab, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def chicken():
    return _parse("kyochon_list_chicken.html", "chicken")


@pytest.fixture(scope="module")
def liquor():
    return _parse("kyochon_list_liquor.html", "liquor")


def test_목록_건수(chicken, liquor):
    assert len(chicken) == 69
    assert len(liquor) == 6


def test_항목_모양(chicken):
    item = next(i for i in chicken if i["name"] == "간장윙박스20PCS")
    assert item["source_id"] == "kyochon"
    assert item["external_id"] == "41363"
    assert item["alt_ids"] == {"id": "41363"}
    assert item["category_raw"] == "치킨"
    assert item["price"] == 23000
    assert item["tags"] == []                 # 소스가 태그를 주지 않는다
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == "https://www.kyochon.com/menu/view.asp?id=41363"
    assert item["image_url"].startswith("https://www.kyochon.com/uploadFiles/")


def test_목록이_설명문을_준다(chicken):
    """이 소스가 `detail: False`인 근거. 하나라도 비면 그 전제가 깨진 것이다."""
    assert all(i["description"] for i in chicken)


def test_설명문의_줄바꿈을_공백으로_접는다(chicken):
    """`<br>`이 그대로 남으면 blurb 요약이 깨진 문자열을 받는다."""
    item = next(i for i in chicken if i["external_id"] == "41363")
    assert item["description"] == (
        "간장소스의 풍부한 맛을 즐길 수 있는 겉바속촉 윙 메뉴[윙+봉 20조각] "
        "※ 원육 수급 상황에 따라 일부 매장에서는 [윙+봉] 20조각 메뉴가 "
        "[윙] 20조각 으로 제공될 수 있습니다.")
    assert "\n" not in item["description"]


def test_가격이_없으면_None이다(liquor):
    """4장이 price를 nullable로 둔 자리. 0으로 채우면 무료 상품이 된다."""
    assert any(i["price"] is None for i in liquor)
    assert all(i["price"] is None or i["price"] > 0 for i in liquor)


def test_가격_파싱():
    assert kyochon.parse_price("23,000") == 23000
    assert kyochon.parse_price("권장소비자가격 23,000 원") == 23000
    assert kyochon.parse_price("") is None
    assert kyochon.parse_price(None) is None
    assert kyochon.parse_price("가격문의") is None


def test_신상_라벨이_없는_소스다(chicken):
    """주의 6번 — 마크업에 배지가 없다. 없는 것을 만들지 않는다(6장)."""
    assert all("_labels" not in i for i in chicken)


def test_네비게이션_li를_상품으로_세지_않는다(chicken):
    """상품 블록의 표시는 `dl.txt > dt`다. 페이지에는 메뉴 탭 li도 있다."""
    assert all(i["name"] for i in chicken)
    assert "치킨" not in {i["name"] for i in chicken}   # 탭 이름이 섞이면 실패한다


def test_모르는_탭은_거부한다():
    with pytest.raises(ValueError, match="모르는 탭"):
        kyochon.parse_list("<html></html>", "burger", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_탭을_전부_덮는다():
    assert set(kyochon.BOOTSTRAP_COUNTS) == set(kyochon.CATEGORIES)
    assert sum(kyochon.BOOTSTRAP_COUNTS.values()) == 101
