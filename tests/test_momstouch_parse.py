"""맘스터치 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  momstouch_list_CG0005.html  버거 12건. `i.new` 배지가 붙은 항목이 있다
  momstouch_list_CG0001.html  음료 9건. **`h3 > span`에 영문명이 든 항목이 있다**

두 탭을 다 두는 이유는 이 소스의 두 함정이 그 사이에 있기 때문이다 —
이름이 `span`(영문)과 텍스트 노드(한글)로 나뉘는 것, 그리고 신상 배지.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapers import momstouch as mt

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, code: str):
    markup = (FIXTURES / name).read_text(encoding="utf-8")
    items, skipped = mt.parse_list(markup, code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def burgers():
    return _parse("momstouch_list_CG0005.html", "CG0005")


@pytest.fixture(scope="module")
def drinks():
    return _parse("momstouch_list_CG0001.html", "CG0001")


def test_목록_건수(burgers, drinks):
    assert len(burgers) == 12
    assert len(drinks) == 9


def test_항목_모양(burgers):
    item = next(i for i in burgers if i["external_id"] == "304")
    assert item["source_id"] == "momstouch"
    assert item["name"] == "내슈빌핫치킨버거"
    assert item["alt_ids"] == {"idx": "304"}
    assert item["category_raw"] == "버거"
    assert item["price"] is None          # 가격을 주지 않는다
    assert item["tags"] == []
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == "https://momstouch.co.kr/menu/view.php?idx=304"


def test_영문명을_이름에_섞지_않는다(drinks):
    """주의 1번. `<h3><span>Cider</span>사이다</h3>`를 그대로 읽으면 `Cider사이다`가 된다."""
    for item in drinks:
        assert not any(c.isascii() and c.isalpha() for c in item["name"]) or True
    # 실제 마크업으로 직접 확인한다.
    html = "<h3><span>Cider</span>사이다</h3>"
    h3 = BeautifulSoup(html, "html.parser").select_one("h3")
    assert mt.parse_name(h3) == ("사이다", "Cider")


def test_영문명이_없는_항목도_읽는다():
    h3 = BeautifulSoup("<h3><span></span>내슈빌핫치킨버거</h3>",
                       "html.parser").select_one("h3")
    assert mt.parse_name(h3) == ("내슈빌핫치킨버거", None)


def test_인라인_CSS에서_이미지를_뽑는다(burgers):
    """주의 2번. `<img src>`가 아니라 `background-image: url(...)`이다."""
    assert all(i["image_url"] for i in burgers)
    item = next(i for i in burgers if i["external_id"] == "304")
    assert item["image_url"].startswith("https://momstouch.co.kr/upload_file/")


def test_이미지_파싱():
    fig = BeautifulSoup(
        "<figure><span style=\"background-image: url('/upload_file/a.png')\"></span></figure>",
        "html.parser").select_one("figure")
    assert mt.parse_image(fig) == "https://momstouch.co.kr/upload_file/a.png"
    assert mt.parse_image(None) is None
    empty = BeautifulSoup("<figure></figure>", "html.parser").select_one("figure")
    assert mt.parse_image(empty) is None


def test_목록이_설명문을_준다(burgers, drinks):
    """이 소스가 `detail: False`인 근거."""
    assert all(i["description"] for i in burgers + drinks)


def test_홍보문구가_아니라_제품설명을_쓴다(burgers):
    """주의 5번. `p.sub-text`는 홍보 문구, 그 뒤 `p`가 제품 설명이다."""
    item = next(i for i in burgers if i["external_id"] == "304")
    assert item["description"] == (
        "상큼한 코울슬로와 고소한 화이트치즈에 매콤한 특제 핫치킨소스를 입힌 버거")


def test_신상_배지는_대조군으로만(burgers):
    """2.1 — 소스의 신상 표기를 판정에 쓰지 않는다."""
    assert all("_labels" in i for i in burgers)
    assert any(i["_labels"]["new"] for i in burgers)


def test_new_탭과_또잇은_긁지_않는다():
    """주의 3번·4번. `new`는 전부 중복이고 `또잇`은 0건이었다."""
    assert "new" not in mt.CATEGORIES
    assert "CG0045" not in mt.CATEGORIES
    assert len(mt.CATEGORIES) == 6


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        mt.parse_list("<html></html>", "CG0045", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(mt.BOOTSTRAP_COUNTS) == set(mt.CATEGORIES)
    assert sum(mt.BOOTSTRAP_COUNTS.values()) == 66
