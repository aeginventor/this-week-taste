"""크라운제과 파서 골든 테스트.

픽스처는 2026-08-27 실측 응답이다. 네트워크 없이 돈다.

  crown_list_new.html         GET ?searchCateCd=1478063307       신제품 3
  crown_list_biscuit_p1.html  GET ?searchCateCd=1478063272&…=1   비스킷 15 중 첫 12
  crown_list_all.html         GET ?searchCateCd=all              총 45 (완전성 대조용)

**픽스처가 셋인 것 자체가 이 소스의 함정이다.** `신제품` 탭은 나머지 넷과 교집합이
0이라 빼면 그대로 사라지고, `전체` 탭의 총건수는 그것을 알아채는 유일한 근거다.
비스킷은 유일하게 두 쪽으로 나뉘는 탭이라 페이지네이션 경로를 지킨다.

상세 픽스처가 없는 이유는 **목록이 설명문을 전부 줘서 상세를 아예 긁지 않기 때문이다**
(`detail: False`).
"""

from pathlib import Path

import pytest

from scrapers import crown

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-27T09:00:00+09:00"

NEW = "1478063307"
BISCUIT = "1478063272"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def new_items():
    items, skipped = crown.parse_list(_text("crown_list_new.html"), NEW, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def biscuit_items():
    items, skipped = crown.parse_list(_text("crown_list_biscuit_p1.html"), BISCUIT,
                                      scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


# ── 완전성: 이 소스가 가장 조용히 틀릴 수 있는 자리다 ──────────────────


def test_신제품_탭은_다른_탭과_겹치지_않는다(new_items, biscuit_items):
    """겹쳤다면 `신제품`을 빼도 손실이 없다는 뜻이고, 이 테스트는 무의미해진다.

    실제로는 교집합이 0이라 빼는 순간 그 탭이 통째로 사라진다.
    """
    assert {i["external_id"] for i in new_items} & {i["external_id"] for i in biscuit_items} == set()


def test_전체_탭_총건수가_탭_다섯의_합이다():
    """`전체`가 45인데 우리 다섯 탭의 부트스트랩 합도 45여야 한다.

    이 등식이 깨지면 우리가 모르는 탭이 있다는 뜻이다.
    """
    assert crown.parse_total(_text("crown_list_all.html")) == sum(crown.BOOTSTRAP_COUNTS.values())


def test_총건수는_페이지에_담긴_건수가_아니다(biscuit_items):
    """비스킷 첫 쪽은 12건인데 소스는 15건이라고 한다. 그래서 2쪽을 더 받아야 한다."""
    assert crown.parse_total(_text("crown_list_biscuit_p1.html")) == 15
    assert len(biscuit_items) == crown.PAGE_SIZE == 12


def test_총건수가_없으면_예외다():
    """0으로 삼키면 페이지네이션이 첫 쪽에서 조용히 멈춘다."""
    with pytest.raises(crown.ParseError, match="총건수"):
        crown.parse_total("<html><body><ul class='pro_list'></ul></body></html>")


def test_모르는_탭_코드는_예외다():
    with pytest.raises(ValueError, match="모르는 탭 코드"):
        crown.parse_list(_text("crown_list_new.html"), "9999", scraped_at=SCRAPED_AT)


# ── 항목의 모양 ──────────────────────────────────────────────────


def test_필수_필드가_전부_있다(new_items, biscuit_items):
    for item in new_items + biscuit_items:
        assert item["source_id"] == "crown"
        assert item["name"]
        assert item["external_id"]
        assert item["scraped_at"] == SCRAPED_AT


def test_external_id는_idx다(new_items):
    assert sorted(i["external_id"] for i in new_items) == ["393", "394", "395"]
    assert all(i["alt_ids"] == {"idx": i["external_id"]} for i in new_items)


def test_상품_키가_겹치지_않는다(new_items, biscuit_items):
    keys = [i["external_id"] for i in new_items + biscuit_items]
    assert len(keys) == len(set(keys))


def test_목록이_설명문을_준다(new_items, biscuit_items):
    """`detail: False`의 근거다. 이것이 깨지면 blurb가 전량 null이 된다."""
    items = new_items + biscuit_items
    assert all(i["description"] for i in items)
    assert next(i for i in items if i["external_id"] == "395")["description"] == "버터 크로아상 풍미 가득"


def test_가격은_항상_없다(new_items, biscuit_items):
    """브랜드 사이트라 가격을 주지 않는다. diff의 (이름, 가격) 계층이 무력해진다."""
    assert all(i["price"] is None for i in new_items + biscuit_items)


def test_소스가_태그를_주지_않는다(new_items):
    assert all(i["tags"] == [] for i in new_items)


def test_category_raw는_탭_이름이다(new_items, biscuit_items):
    assert {i["category_raw"] for i in new_items} == {"신제품"}
    assert {i["category_raw"] for i in biscuit_items} == {"비스킷"}


def test_source_url은_개별_상품_주소다(new_items):
    assert next(i for i in new_items if i["external_id"] == "395")["source_url"] == \
        "https://www.crown.co.kr/product/view?idx=395"


# ── 이미지: 한글·공백이 든 경로 ────────────────────────────────────


def test_이미지_주소가_퍼센트_인코딩된다(new_items):
    """원본 경로에 한글과 공백과 괄호가 있다. 그대로 내보내면 깨진다."""
    url = next(i for i in new_items if i["external_id"] == "395")["image_url"]
    assert url.startswith("https://www.crown.co.kr/upload/system/product/")
    assert " " not in url
    assert "카라멜콘" not in url
    assert url.endswith(".jpg")


def test_모든_항목이_이미지를_갖는다(new_items, biscuit_items):
    assert all(i["image_url"] for i in new_items + biscuit_items)


# ── 소스의 신상 라벨: 판정에 쓰지 않고 대조군으로만 (2.1) ───────────────


def test_신제품_탭만_new_라벨을_받는다(new_items, biscuit_items):
    assert all(i["_labels"]["new"] for i in new_items)
    assert not any(i["_labels"]["new"] for i in biscuit_items)


def test_라벨은_언더바_키라_스냅샷에_저장되지_않는다(new_items):
    """`snapshot.py`가 `_` 접두 키를 control 파일로 떼어 놓는다."""
    assert all(k.startswith("_") for k in new_items[0] if k not in {
        "source_id", "external_id", "alt_ids", "name", "price", "category_raw",
        "description", "tags", "image_url", "source_url", "scraped_at"})


# ── 이름이 없는 항목 ─────────────────────────────────────────────


def test_이름이_없으면_건너뛰고_센다():
    markup = """
      <div class="search_area"><strong class="tit">총 <span>1</span>건 있습니다.</strong></div>
      <ul class="pro_list">
        <li class="item" onclick="view('1')">
          <div class="img"><img src="/upload/a.jpg"></div>
          <div class="info"><strong></strong><div>설명만 있다</div></div>
        </li>
      </ul>
    """
    items, skipped = crown.parse_list(markup, NEW, scraped_at=SCRAPED_AT)
    assert items == []
    assert skipped == 1
