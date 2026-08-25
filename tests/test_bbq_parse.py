"""BBQ 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  bbq_menu_19.json  치킨 22건. `[NEW]` 접두사와 ™ 기호가 둘 다 들어 있다
  bbq_menu_23.json  음료 21건. 설명문이 없는 항목이 섞여 있다
"""

import json
from pathlib import Path

import pytest

from pipeline import normalize
from scrapers import bbq

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, category_code: str):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    items, skipped = bbq.parse_menu(payload, category_code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def chicken():
    return _parse("bbq_menu_19.json", "19")


@pytest.fixture(scope="module")
def drinks():
    return _parse("bbq_menu_23.json", "23")


def test_목록_건수(chicken, drinks):
    assert len(chicken) == 22
    assert len(drinks) == 21


def test_항목_모양(chicken):
    item = next(i for i in chicken if i["external_id"] == "3003")
    assert item["source_id"] == "bbq"
    assert item["name"] == "황금올리브치킨™"
    assert item["alt_ids"] == {"id": "3003"}
    assert item["category_raw"] == "치킨"
    assert item["price"] == 23000
    assert item["tags"] == []                 # 소스가 태그를 주지 않는다
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == "https://bbq.co.kr/products/3003"
    assert item["image_url"].startswith("https://static.bbqorder.co.kr/")


def test_가격이_전부_있다(chicken, drinks):
    """이 채널에서 유일하게 가격을 전부 준다(주의 7번)."""
    assert all(isinstance(i["price"], int) and i["price"] > 0
               for i in chicken + drinks)


def test_목록이_설명문을_준다(chicken):
    """이 소스가 `detail: False`인 근거. 음료 일부는 설명이 없어 null이다."""
    assert all(i["description"] for i in chicken)


def test_설명문이_없으면_None이다(drinks):
    assert any(i["description"] is None for i in drinks)


def test_이름을_손대지_않는다(chicken):
    """주의 4번·5번. `[NEW]`도 ™도 원문 그대로 간다 (4장의 name 계약)."""
    names = {i["name"] for i in chicken}
    assert any(n.startswith("[NEW]") for n in names)
    assert any("™" in n for n in names)


def test_NEW_접두사는_대조군으로_따로_보낸다(chicken):
    """2.1 — 소스의 신상 표기를 판정에 쓰지 않는다. `_`가 그 표시다."""
    labelled = [i for i in chicken if i["_labels"]["new"]]
    assert labelled
    assert all(i["name"].startswith("[NEW]") for i in labelled)
    assert all(not i["name"].startswith("[NEW]")
               for i in chicken if not i["_labels"]["new"])


def test_상표기호는_공유_정규화가_접는다(chicken):
    """주의 5번 — 스크래퍼가 아니라 normalize가 할 일이다.

    동일성 판정은 모든 소스가 쓰는 자리라 소스별 스크래퍼에 두면 7장의 누수가 된다.
    """
    item = next(i for i in chicken if i["name"] == "황금올리브치킨™")
    assert normalize.normalize_name(item["name"]) == "황금올리브치킨tm"


def test_프로모션_카테고리를_긁지_않는다():
    """주의 1번. 34(필릭스 PICK)·17(추천)이 들어오면 25건이 중복되어
    `snapshot.py`의 유일성 검사가 발행을 멈춘다."""
    assert "34" not in bbq.CATEGORIES
    assert "17" not in bbq.CATEGORIES
    assert set(bbq.CATEGORIES) == {"18", "19", "20", "21", "22", "23"}


def test_봉투가_생기면_시끄럽게_죽는다():
    """주의 2번 — 지금은 최상위 배열이다. 봉투가 생기면 조용히 0건이 되면 안 된다."""
    with pytest.raises(bbq.ParseError, match="배열이 아니다"):
        bbq.parse_menu({"data": []}, "19", scraped_at=SCRAPED_AT)


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        bbq.parse_menu([], "34", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(bbq.BOOTSTRAP_COUNTS) == set(bbq.CATEGORIES)
    assert sum(bbq.BOOTSTRAP_COUNTS.values()) == 105
