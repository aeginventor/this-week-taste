"""컴포즈 목록 파서 골든 테스트 (CLAUDE.md 7장).

`tests/fixtures/compose_list_303364.html`은 2026-08-25에 실제로 받은
커피ㆍ콜드브루 카테고리 1페이지 응답이다. 네트워크 없이 돌고, 컴포즈가 사이트
구조를 바꿨을 때 무엇이 어떻게 달라졌는지 보여준다.
"""

from pathlib import Path

import pytest

from scrapers import compose

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "compose_list_303364.html"
SCRAPED_AT = "2026-08-25T10:00:00+09:00"


@pytest.fixture(scope="module")
def parsed():
    items, skipped = compose.parse_list(SAMPLE.read_text(encoding="utf-8"), "303364",
                                        scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


def test_커피_카테고리_1페이지_20건(parsed):
    # 서버가 페이지당 20개로 고정한다.
    assert len(parsed) == compose.PAGE_SIZE == 20


def test_item_srl이_주키다(parsed):
    assert parsed[0]["external_id"] == "303749"
    assert parsed[0]["alt_ids"] == {"item_srl": "303749"}


def test_주키가_페이지_안에서_유일하다(parsed):
    ids = [i["external_id"] for i in parsed]
    assert len(set(ids)) == len(ids)


def test_이름이_잘리지_않는다(parsed):
    # CU와 달리 컴포즈는 이름을 온전히 준다.
    assert parsed[0]["name"] == "에스프레소"
    assert all(i["name"] and i["name"].strip() == i["name"] for i in parsed)


def test_가격은_항상_없다(parsed):
    # 목록에도 상세에도 가격이 없다. diff의 (이름, 가격) 계층이 무력해진다.
    assert all(i["price"] is None for i in parsed)


def test_설명문은_목록에_없다(parsed):
    # 상세에도 없다(영양·알레르기 정보뿐). blurb는 항상 null로 발행된다 (6장).
    assert all(i["description"] is None for i in parsed)


def test_카테고리_이름이_코드에서_역산된다(parsed):
    assert all(i["category_raw"] == "커피ㆍ콜드브루" for i in parsed)


def test_이미지와_상세_주소가_절대경로다(parsed):
    # 마크업은 상대 경로로 준다. 발행물이 그대로 실으면 링크가 깨진다.
    assert all(i["image_url"].startswith("https://composecoffee.com/files/") for i in parsed)
    assert all(i["source_url"].startswith("https://composecoffee.com/index.php") for i in parsed)
    assert all(i["external_id"] in i["source_url"] for i in parsed)


def test_소스의_신상_라벨을_담지_않는다(parsed):
    # 항목 마크업에 배지가 없다. 없는 것을 있는 척하지 않는다 — 채점표가 없는 소스다.
    assert all("_labels" not in i for i in parsed)


def test_모르는_카테고리_코드는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리 코드"):
        compose.parse_list("<html></html>", "999999", scraped_at=SCRAPED_AT)


def test_이름이_없으면_건너뛰고_센다():
    # 이름 선택자가 바뀌면 조용히 빈 결과가 나온다. 그것이 세어져야 한다 (2.4).
    markup = '<a class="cafemenu-menu-item" href="?item_srl=1"></a>'
    items, skipped = compose.parse_list(markup, "303364", scraped_at=SCRAPED_AT)
    assert (items, skipped) == ([], 1)


def test_부트스트랩_실측치가_카테고리와_짝이_맞는다():
    assert set(compose.BOOTSTRAP_COUNTS) == set(compose.CATEGORIES)
    assert sum(compose.BOOTSTRAP_COUNTS.values()) == 197
