"""GS25 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  gs25_freshfood_p1.json    유어스 Fresh Food 1페이지 20건. `isNew`가 **전건 "T"**
  gs25_different_p14.json   차별화 상품 14페이지 20건. `isNew`가 **전건 "F"**,
                            범위 밖 분류(생활용품) 4건이 섞여 있다

두 쪽을 다 쓰는 이유: `isNew`는 `"T"`/`"F"` **문자열**이라 truthy로 읽으면 전건이
신상이 된다. 한쪽만으로 테스트하면 **판정이 뒤집혀도 통과한다.**
"""

import json
from pathlib import Path

import pytest

from scrapers import gs25

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T15:00:00+09:00"


def _parse(name: str, list_key: str):
    body = (FIXTURES / name).read_text(encoding="utf-8")
    return gs25.parse_list(body, list_key, scraped_at=SCRAPED_AT)


@pytest.fixture(scope="module")
def fresh():
    return _parse("gs25_freshfood_p1.json", "FreshFoodKey")


@pytest.fixture(scope="module")
def different():
    return _parse("gs25_different_p14.json", "DifferentServiceKey")


def test_문자열_안의_JSON을_두_번_푼다(fresh):
    """응답 본문은 JSON 문자열이고 그 안에 JSON이 들어 있다 (주의 1번)."""
    items, total, _ = fresh
    assert total == 204
    assert len(items) == 20


def test_항목_모양(fresh):
    items, _, _ = fresh
    item = next(i for i in items if i["external_id"] == "8809494072195")
    assert item["source_id"] == "gs25"
    assert item["name"] == "오든든)대만식햄치즈샌드"
    assert item["alt_ids"] == {"att_file_id": "MD0000001280494"}
    assert item["price"] == 2800
    assert item["category_raw"] == "프레시푸드"
    assert item["description"] is None      # 설명문이 없는 소스다
    assert item["tags"] == []
    assert item["scraped_at"] == SCRAPED_AT
    assert item["image_url"].startswith("https://image.woodongs.com/")


def test_이름_끝의_편성_코드를_뗀다(fresh):
    """사이트 자신이 `1편`/`2편`을 지우고 그린다 (주의 6번)."""
    items, _, _ = fresh
    assert not any(i["name"].endswith(("1편", "2편")) for i in items)
    assert "오든든)더블햄샌드" in {i["name"] for i in items}


def test_잘린_이름은_건드리지_않는다(fresh):
    """`…피타브레드1`은 `1편`이 잘린 흔적이지만 복원하지 않는다. 사이트도 그대로 둔다."""
    items, _, _ = fresh
    assert "오든든)치즈포테이토피타브레드1" in {i["name"] for i in items}


def test_신상_라벨은_문자열_비교다(fresh, different):
    """`"T"`/`"F"`를 truthy로 읽으면 전건이 신상이 된다 (주의 2번)."""
    fresh_items, _, _ = fresh
    diff_items, _, _ = different
    assert all(i["_labels"]["new"] for i in fresh_items)
    assert not any(i["_labels"]["new"] for i in diff_items)


def test_범위_밖_분류를_뺀다(different):
    """볼펜·우산 같은 생활용품이 차별화 상품 목록에 섞여 온다 (주의 4번)."""
    items, _, dropped = different
    assert dict(dropped) == {"DAILY_SUPPLIES": 4}
    assert len(items) == 16
    assert all(i["category_raw"] in gs25.CATEGORIES.values() for i in items)


def test_상품_URL이_없어_목록을_가리킨다(fresh, different):
    """ADR-0013. 목록 항목에 링크 자체가 없다."""
    fresh_items, _, _ = fresh
    diff_items, _, _ = different
    assert all(i["source_url"].endswith("/youus-freshfood") for i in fresh_items)
    assert all(i["source_url"].endswith("/youus-different-service") for i in diff_items)


def test_모르는_분류는_예외다():
    """조용히 빠지면 `snapshot.py`의 건수 검증에서 그만큼 사라진다 (주의 5번)."""
    body = json.dumps(json.dumps({
        "SubPageListPagination": {"totalNumberOfResults": 1},
        "SubPageListData": [{"goodsNm": "유어스)새분류상품", "code": "1",
                             "departCd": {"code": "PET_SUPPLIES"}}],
    }))
    with pytest.raises(gs25.ParseError, match="모르는 분류"):
        gs25.parse_list(body, "FreshFoodKey", scraped_at=SCRAPED_AT)


def test_총건수가_없으면_예외다():
    body = json.dumps(json.dumps({"SubPageListData": []}))
    with pytest.raises(gs25.ParseError, match="총건수"):
        gs25.parse_payload(body)


def test_응답이_JSON이_아니면_예외다():
    with pytest.raises(gs25.ParseError, match="JSON이 아니다"):
        gs25.parse_payload("<html>error</html>")


def test_가격이_없으면_null이다():
    assert gs25.parse_price(0) is None
    assert gs25.parse_price(None) is None
    assert gs25.parse_price(5500.0) == 5500


def test_이미지가_없으면_null이다():
    """이미지가 없는 항목은 파일명에 문자열 `null`이 들어온다."""
    assert gs25.parse_image("https://image.woodongs.com/imgsvr/item/GD_null_001.jpg") is None
    assert gs25.parse_image(None) is None


def test_같은_코드는_접고_가격이_다르면_예외다():
    """이마트24와 같은 계약. 다른 상품이 같은 코드를 쓰는 것을 삼키지 않는다(ADR-0001)."""
    def item(name, price):
        return {"external_id": "8801", "name": name, "price": price}

    assert len(gs25.dedupe([item("가", 1000), item("가", 1000)])) == 1
    with pytest.raises(gs25.ParseError, match="가격이 다르다"):
        gs25.dedupe([item("가", 1000), item("나", 2000)])


def test_모르는_목록키는_예외다():
    with pytest.raises(ValueError, match="모르는 목록키"):
        gs25.parse_list("{}", "EventKey", scraped_at=SCRAPED_AT)
