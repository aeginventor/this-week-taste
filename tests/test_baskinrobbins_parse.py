"""배스킨라빈스 파서 골든 테스트.

CLAUDE.md 7장이 테스트를 요구하는 첫 번째 종류다 — **외부에서 들어온 값의 모양에
의존하는 코드.** 소스가 마크업을 바꾸면 예외가 아니라 빈 결과가 나오므로,
저장된 원본 샘플로 눈에 보이게 만든다.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  baskinrobbins_list_A.html    아이스크림 29건. `view.php` 네임스페이스
  baskinrobbins_list_C.html    음료 17건. `view_subcategory.php` 네임스페이스
  baskinrobbins_view_1124.html 상세 1건 (솔티 조청 뉴욕치즈케이크)

두 목록을 다 두는 이유는 **이 소스의 유일한 함정이 둘 사이에 있기 때문이다** —
seq가 각각 1부터 시작해 8건이 충돌한다(스크래퍼 docstring 주의 1번).
한쪽만 테스트하면 그 함정을 영원히 못 본다.
"""

from pathlib import Path

import pytest

from scrapers import baskinrobbins as br

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def icecream():
    items, skipped = br.parse_list(_load("baskinrobbins_list_A.html"), "A",
                                   scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def drinks():
    items, skipped = br.parse_list(_load("baskinrobbins_list_C.html"), "C",
                                   scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


def test_목록_건수(icecream, drinks):
    assert len(icecream) == 29
    assert len(drinks) == 17


def test_항목_모양(icecream):
    item = next(i for i in icecream if i["name"] == "솔티 조청 뉴욕치즈케이크")
    assert item["source_id"] == "baskinrobbins"
    assert item["external_id"] == "p1124"
    assert item["alt_ids"] == {"seq": "1124"}
    assert item["category_raw"] == "아이스크림"
    assert item["price"] is None          # 이 소스는 가격을 주지 않는다
    assert item["description"] is None    # 설명문은 상세에만 있다
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"] == (
        "https://www.baskinrobbins.co.kr/menu/view.php?seq=1124")
    assert item["image_url"].startswith("https://www.baskinrobbins.co.kr/upload/")


def test_소스가_준_태그를_그대로_싣는다(icecream):
    """이 소스의 존재 이유 중 하나. LLM이 이름만 보고 지어내는 것보다 낫다(6장)."""
    item = next(i for i in icecream if i["external_id"] == "p1124")
    assert item["tags"] == ["크림치즈", "조청카라멜", "현미그라함쿠키"]
    # 전건에 태그가 있다 — 하나라도 비면 마크업이 바뀐 것이다.
    assert all(i["tags"] for i in icecream)


def test_태그_파싱():
    assert br.parse_tags("#크림치즈 #조청카라멜") == ["크림치즈", "조청카라멜"]
    assert br.parse_tags("  ") == []
    assert br.parse_tags(None) == []
    # `#`이 없으면 태그가 아니다. 통짜 문자열을 태그 한 개로 만들지 않는다.
    assert br.parse_tags("크림치즈") == ["크림치즈"]


def test_두_네임스페이스가_충돌하지_않는다(icecream, drinks):
    """이 소스의 유일한 진짜 함정 (스크래퍼 docstring 주의 1번).

    2026-08-25 실측: 전체 128건 중 raw seq는 120개뿐이라 8건이 겹친다.
    접두사가 빠지면 diff가 서로 다른 제품을 같은 것으로 본다.
    """
    assert all(i["external_id"].startswith("p") for i in icecream)
    assert all(i["external_id"].startswith("s") for i in drinks)

    raw_overlap = ({i["alt_ids"]["seq"] for i in icecream}
                   & {i["alt_ids"]["seq"] for i in drinks})
    assert raw_overlap, "픽스처가 바뀌었다 — 이 테스트가 지키려는 충돌 자체가 사라졌다"

    keys = [i["external_id"] for i in icecream + drinks]
    assert len(keys) == len(set(keys))


def test_상세_링크가_네임스페이스를_따라간다(drinks):
    item = drinks[0]
    assert "view_subcategory.php" in item["source_url"]


def test_신상_라벨은_대조군으로만(icecream):
    """2.1 — 소스의 신상 표기를 판정에 쓰지 않는다. `_`가 그 표시다."""
    assert all("_labels" in i for i in icecream)
    assert sum(1 for i in icecream if i["_labels"]["new"]) == 2


def test_상세_파싱():
    detail = br.parse_detail(_load("baskinrobbins_view_1124.html"))
    # 목록의 이름과 **정확히 같아야** enrich의 이름 대조를 통과한다.
    assert detail["name"] == "솔티 조청 뉴욕치즈케이크"
    assert detail["description"] == (
        "크림치즈 아이스크림에 달콤하고 짭조름한 솔티 조청 카라멜과 "
        "바삭한 현미 그라함 쿠키의 만남")
    # 태그는 상세에 없다. []를 주면 enrich가 스냅샷의 태그를 보존한다(4장).
    assert detail["tags"] == []


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        br.parse_list("<html></html>", "Z", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    """빠진 카테고리가 있으면 첫 수집 검증이 그 카테고리를 그냥 지나친다."""
    assert set(br.BOOTSTRAP_COUNTS) == set(br.CATEGORIES)
    assert sum(br.BOOTSTRAP_COUNTS.values()) == 128
