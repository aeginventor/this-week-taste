"""던킨 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  dunkin_list_cat1_p1.html  DONUT 1페이지. `props.products` 키
  dunkin_list_cat6_p1.html  COFFEE 1페이지. `props.productCats` 키
  dunkin_view_536.html      상세 1건 (페이머스 글레이즈드)

두 목록을 다 두는 이유는 **이 소스의 두 함정이 그 사이에 있기 때문이다** —
응답 키가 갈리고(주의 1번), 두 키의 `id`가 충돌한다(주의 2번).
`products`만 테스트하면 COFFEE가 통째로 0건이 되는 사고를 영영 못 잡는다.
"""

from pathlib import Path

import pytest

from scrapers import dunkin

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, category_code: str):
    markup = (FIXTURES / name).read_text(encoding="utf-8")
    return dunkin.parse_page(dunkin.extract_data_page(markup), category_code,
                             scraped_at=SCRAPED_AT)


@pytest.fixture(scope="module")
def donuts():
    return _parse("dunkin_list_cat1_p1.html", "1")


@pytest.fixture(scope="module")
def coffee():
    return _parse("dunkin_list_cat6_p1.html", "6")


def test_products_키를_읽는다(donuts):
    items, last_page = donuts
    assert len(items) == 12          # per_page 고정
    assert last_page == 8            # DONUT 91건 / 12 = 8페이지


def test_productCats_키도_읽는다(coffee):
    """주의 1번. 이 테스트가 없으면 COFFEE 20건이 조용히 사라진다."""
    items, last_page = coffee
    assert len(items) == 12
    assert last_page == 2
    assert all(i["category_raw"] == "COFFEE" for i in items)


def test_항목_모양(donuts):
    items, _ = donuts
    item = next(i for i in items if i["name"] == "페이머스 글레이즈드")
    assert item["source_id"] == "dunkin"
    assert item["external_id"] == "p536"
    assert item["alt_ids"] == {"id": "536"}
    assert item["category_raw"] == "DONUT"     # 주의 8번: cat1만 싣는다
    assert item["price"] is None               # 가격을 주지 않는다
    assert item["description"] is None         # 설명문은 상세에 있다
    assert item["tags"] == []                  # 태그도 상세에 있다
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == (
        "https://www.dunkindonuts.co.kr/menu/view?cat=1&sub=37&id=536")
    assert item["image_url"].startswith("https://www.dunkindonuts.co.kr/storage/")


def test_두_네임스페이스가_충돌하지_않는다(donuts, coffee):
    """주의 2번. 전체 216건 중 raw id가 2건 겹친다(id 4, 132).

    픽스처 두 장만으로는 그 두 건이 안 잡힐 수 있으므로, 여기서는 **접두사가
    실제로 붙는지**를 지킨다. 충돌 자체는 첫 수집의 유일성 검사가 잡는다.
    """
    ditems, _ = donuts
    citems, _ = coffee
    assert all(i["external_id"].startswith("p") for i in ditems)
    assert all(i["external_id"].startswith("c") for i in citems)

    keys = [i["external_id"] for i in ditems + citems]
    assert len(keys) == len(set(keys))


def test_신상_라벨은_대조군으로만(donuts):
    """2.1 — 소스의 신상 표기를 판정에 쓰지 않는다."""
    items, _ = donuts
    assert all("_labels" in i for i in items)
    assert all(isinstance(i["_labels"]["new"], bool) for i in items)


def test_상세_파싱():
    markup = (FIXTURES / "dunkin_view_536.html").read_text(encoding="utf-8")
    detail = dunkin.parse_detail(dunkin.extract_data_page(markup))
    # 목록의 이름과 **정확히 같아야** enrich의 이름 대조를 통과한다.
    assert detail["name"] == "페이머스 글레이즈드"
    assert detail["description"] == "더욱 촉촉하고 부드러워진 달콤한 정통 도넛"
    # `#`을 떼고 싣는다. 발행물의 tags는 이미 UI에서 `#`을 붙인다.
    assert detail["tags"] == ["글레이즈드", "오리지널", "던킨글레이즈드"]


def test_상세는_단수_product를_읽는다():
    """주의: `props.products`(복수)는 같은 서브카테고리의 다른 제품 목록이다.

    복수를 읽으면 목록 첫 항목의 설명이 전 제품에 붙는다 — 조용히 틀린다.
    """
    markup = (FIXTURES / "dunkin_view_536.html").read_text(encoding="utf-8")
    page = dunkin.extract_data_page(markup)
    assert "products" in page["props"] and "product" in page["props"]
    assert page["props"]["product"]["data"]["id"] == 536


def test_마크업이_바뀌면_시끄럽게_죽는다():
    with pytest.raises(dunkin.ParseError, match="data-page"):
        dunkin.extract_data_page("<html><body>없음</body></html>")


def test_모르는_응답_키는_거부한다():
    """조용히 0건을 내보내지 않는다 (2.4)."""
    with pytest.raises(dunkin.ParseError, match="목록 키를 찾지 못했다"):
        dunkin.parse_page({"props": {"somethingElse": {}}}, "1", scraped_at=SCRAPED_AT)


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        dunkin.parse_page({"props": {"products": {}}}, "9", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(dunkin.BOOTSTRAP_COUNTS) == set(dunkin.CATEGORIES)
    assert sum(dunkin.BOOTSTRAP_COUNTS.values()) == 216
