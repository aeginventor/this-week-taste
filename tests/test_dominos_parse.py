"""도미노 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다(**EUC-KR을 디코딩해 UTF-8로 저장했다**).
네트워크 없이 돈다.

  dominos_list_C0101.html  메뉴(피자) 27건. 라벨·가격·상세 링크가 다 있다
  dominos_list_C0202.html  음료&기타 14건. **상세 링크가 하나도 없다** — ADR-0013 2층

두 카테고리를 다 두는 이유는 이 소스가 **한 소스 안에서 1층과 2층이 섞이는 첫 사례**라서다.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapers import dominos

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, code: str):
    markup = (FIXTURES / name).read_text(encoding="utf-8")
    items, skipped = dominos.parse_list(markup, code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def pizza():
    return _parse("dominos_list_C0101.html", "C0101")


@pytest.fixture(scope="module")
def drinks():
    return _parse("dominos_list_C0202.html", "C0202")


def test_목록_건수(pizza, drinks):
    assert len(pizza) == 27
    assert len(drinks) == 14


def test_한글이_깨지지_않았다(pizza):
    """주의 1번 — EUC-KR. 디코딩이 틀리면 이름이 전부 깨진다."""
    names = [i["name"] for i in pizza]
    assert any("치즈" in n for n in names)
    assert all("�" not in n for n in names)


def test_항목_모양(pizza):
    item = next(i for i in pizza if i["external_id"] == "RPZ422SL")
    assert item["source_id"] == "dominos"
    assert item["name"] == "치즈폴레 무슈스"
    assert item["alt_ids"] == {"code_01": "RPZ422SL"}
    assert item["category_raw"] == "메뉴"
    assert item["scraped_at"] == SCRAPED_AT
    assert item["image_url"].startswith("https://cdn.dominos.co.kr/")


def test_이름에서_라벨을_떼어낸다(pizza):
    """주의 2번. `div.label-box`를 안 떼면 `치즈폴레 무슈스기간한정NEW`가 된다."""
    item = next(i for i in pizza if i["external_id"] == "RPZ422SL")
    assert item["name"] == "치즈폴레 무슈스"
    assert item["_labels"]["badges"] == ["기간한정", "NEW"]
    assert item["_labels"]["new"] is True
    # 어떤 이름에도 라벨 문자열이 붙어 있으면 안 된다.
    assert all(not i["name"].endswith("NEW") for i in pizza)


def test_가격은_M_사이즈를_쓴다(pizza):
    """주의 5번 — `L 36,900원~ / M 30,000원~` → 30000 (2026-08-25 결정)."""
    item = next(i for i in pizza if i["external_id"] == "RPZ422SL")
    assert item["price"] == 30000
    assert all(i["price"] is None or i["price"] > 0 for i in pizza)


def test_가격_파싱():
    def nodes(html):
        return BeautifulSoup(html, "html.parser").select("span.price")

    both = nodes('<span class="price"><span class="size_l">L</span>36,900원~</span>'
                 '<span class="price"><span class="size_m">M</span>30,000원~</span>')
    assert dominos.parse_price(both) == 30000

    only_l = nodes('<span class="price"><span class="size_l">L</span>36,900원~</span>')
    assert dominos.parse_price(only_l) == 36900

    plain = nodes('<span class="price">3,000원</span>')
    assert dominos.parse_price(plain) == 3000
    assert dominos.parse_price([]) is None


def test_lazyload_이미지를_읽는다(pizza):
    """주의 4번. `src`는 플레이스홀더 `bg.gif`다."""
    assert all(i["image_url"] for i in pizza)
    assert all("bg.gif" not in i["image_url"] for i in pizza)


def test_해시태그를_설명문으로_쓴다(pizza):
    """주의 6번. 분류어가 아니라 제품 설명이므로 `tags`가 아니라 `description`이다."""
    item = next(i for i in pizza if i["external_id"] == "RPZ422SL")
    assert item["tags"] == []
    assert item["description"] and "무신사" in item["description"]


# ── source_url이 1층과 2층으로 갈린다 (주의 7번) ──────────────────

def test_상세가_있으면_상세를_가리킨다(pizza):
    item = next(i for i in pizza if i["external_id"] == "RPZ422SL")
    assert "detail?" in item["source_url"] and "code_01=RPZ422SL" in item["source_url"]


def test_상세가_없으면_목록을_가리킨다(drinks):
    """ADR-0013 2층. 음료는 모달이라 개별 URL이 없다."""
    assert all(i["source_url"] == "https://web.dominos.co.kr/goods/list?dsp_ctgr=C0202"
               for i in drinks)


def test_상세가_없어도_상품_코드는_나온다(drinks):
    """주의 3번. 음료는 `addGoods('RDK001L6')`에만 코드가 있다."""
    assert all(not i["external_id"].startswith("nh") for i in drinks), \
        "이름 해시로 떨어진 항목이 있다 — 코드 패턴을 놓쳤다"


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        dominos.parse_list("<html></html>", "C9999", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(dominos.BOOTSTRAP_COUNTS) == set(dominos.CATEGORIES)
    assert sum(dominos.BOOTSTRAP_COUNTS.values()) == 50
