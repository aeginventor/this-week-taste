"""스타벅스 목록 파서 골든 테스트 (CLAUDE.md 7장).

`tests/fixtures/starbucks_cold_brew.json`은 2026-08-12에 `CATE_CD=W0000171`로
실제로 받은 응답이다.
"""

import json
from pathlib import Path

import pytest

from scrapers import starbucks

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "starbucks_cold_brew.json"
SCRAPED_AT = "2026-08-12T09:00:00+09:00"


@pytest.fixture(scope="module")
def parsed():
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    items, skipped = starbucks.parse_list(payload, "W0000171", scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


def test_콜드브루_24건(parsed):
    assert len(parsed) == 24


def test_product_cd가_주키다(parsed):
    first = parsed[0]
    assert first["external_id"] == first["alt_ids"]["product_cd"]
    assert first["external_id"].isdigit()


def test_카테고리_안에서_중복이_없다(parsed):
    """`CATE_CD=0`으로 한 번에 받으면 202건이 중복된다. 카테고리별로 받으면 0이다."""
    ids = [i["external_id"] for i in parsed]
    assert len(ids) == len(set(ids))


def test_가격은_항상_없다(parsed):
    """price 필드는 존재하지만 실측 326건 전부 빈 문자열이다."""
    assert all(i["price"] is None for i in parsed)


def test_설명문이_목록에_이미_있다(parsed):
    """이것 때문에 enrich가 이 소스의 상세를 긁지 않는다 (4장 description)."""
    assert all(i["description"] for i in parsed)


def test_빈_문자열은_None으로_접힌다(parsed):
    """스타벅스는 미상을 `""`로 준다. 그대로 두면 '값이 있다'로 오인된다."""
    assert not any(v == "" for i in parsed for v in i.values() if isinstance(v, str))


def test_카테고리_이름은_요청값에서_역산한다(parsed):
    """응답의 cate_CD가 전부 빈 값이라 응답에서 읽을 수 없다."""
    assert all(i["category_raw"] == "콜드 브루" for i in parsed)


def test_이미지가_절대_URL이다(parsed):
    urls = [i["image_url"] for i in parsed if i["image_url"]]
    assert urls
    assert all(u.startswith("http") for u in urls)


def test_신상_라벨은_판정이_아니라_대조군이다(parsed):
    """new_SDATE는 불리언 라벨이 아니라 날짜다 (CLAUDE.md 2.1)."""
    labels = [i["_labels"] for i in parsed]
    assert all(set(l) == {"new", "new_start_date"} for l in labels)
    dates = [l["new_start_date"] for l in labels if l["new_start_date"]]
    assert dates and all(d.isdigit() and len(d) == 8 for d in dates)


def test_MD_카테고리는_아예_요청하지_않는다():
    """텀블러·머그는 걸러내는 것이 아니라 처음부터 안 받는다."""
    assert set(starbucks.CATEGORIES) == set(starbucks.DRINK_CATEGORIES) | set(starbucks.FOOD_CATEGORIES)
    assert "W0000030" not in starbucks.CATEGORIES      # 머그
    assert "W0000035" not in starbucks.CATEGORIES      # 스테인리스


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError):
        starbucks.parse_list([], "W9999999", scraped_at=SCRAPED_AT)


def test_리스트가_아니면_시끄럽게_실패한다():
    with pytest.raises(starbucks.ParseError):
        starbucks.parse_list({"list": "리스트가 아님"}, "W0000171", scraped_at=SCRAPED_AT)
