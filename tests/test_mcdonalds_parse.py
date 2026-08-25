"""맥도날드 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  mcdonalds_list_1.json  버거 22건. **이름에 HTML 태그가 든 항목이 있다**
  mcdonalds_list_7.json  맥런치 9건. 그중 7건이 버거와 겹친다 — 중복 제거의 근거
"""

import json
from pathlib import Path

import pytest

from scrapers import mcdonalds as mcd

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, code: str):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    items, skipped = mcd.parse_list(payload, code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def burgers():
    return _parse("mcdonalds_list_1.json", "1")


@pytest.fixture(scope="module")
def lunch():
    return _parse("mcdonalds_list_7.json", "7")


def test_목록_건수(burgers, lunch):
    assert len(burgers) == 22
    assert len(lunch) == 9


def test_항목_모양(burgers):
    item = next(i for i in burgers if i["external_id"] == "833")
    assert item["source_id"] == "mcdonalds"
    assert item["name"] == "진주 고추 크림치즈 비프 버거 세트"
    assert item["alt_ids"] == {"seq": "833"}
    assert item["category_raw"] == "버거"
    assert item["price"] is None          # 가격 필드 자체가 없다
    assert item["tags"] == []
    assert item["scraped_at"] == SCRAPED_AT
    assert item["source_url"].startswith("https://www.mcdonalds.co.kr/kor/menu/detail/833/")
    assert item["image_url"].startswith("https://www.mcdonalds.co.kr/")


def test_이름의_HTML_태그를_벗긴다(burgers):
    """주의 4번. 태그가 남으면 발행물 카드에 `<sub class=reg>`가 그대로 보인다."""
    assert all("<" not in i["name"] for i in burgers)
    # ®는 마크업이 아니라 이름의 일부다 — 남는다.
    assert any("®" in i["name"] for i in burgers)


def test_설명문의_br을_공백으로_접는다(burgers):
    item = next(i for i in burgers if i["external_id"] == "833")
    assert "<br>" not in item["description"]
    assert "\r" not in item["description"] and "\n" not in item["description"]
    assert item["description"].startswith("매콤 새콤한 진주 고추 피클이 부드럽고")


def test_목록이_설명문을_준다(burgers):
    """이 소스가 `detail: False`인 근거."""
    assert all(i["description"] for i in burgers)


def test_마크업_제거():
    assert mcd.strip_markup("빅맥<sub class=reg>®</sub> 세트") == "빅맥 ® 세트"
    assert mcd.strip_markup("가<br>\r\n나") == "가 나"
    assert mcd.strip_markup("") is None
    assert mcd.strip_markup(None) is None


def test_신상_라벨은_대조군으로만(burgers):
    """2.1. `newIcon`은 2026-08-25 실측에서 전건 빈 문자열이었다."""
    assert all("_labels" in i for i in burgers)
    assert all(i["_labels"]["new"] is False for i in burgers)


# ── 중복 제거 (주의 5번) ───────────────────────────────────────

def test_카테고리_간_중복을_접는다(burgers, lunch):
    """세트가 버거와 맥런치에 함께 실린다. 접지 않으면 유일성 검사가 발행을 멈춘다."""
    overlap = {i["external_id"] for i in burgers} & {i["external_id"] for i in lunch}
    assert overlap, "픽스처가 바뀌었다 — 이 테스트가 지키려는 중복 자체가 사라졌다"

    kept = mcd.dedupe(burgers + lunch)
    keys = [i["external_id"] for i in kept]
    assert len(keys) == len(set(keys))
    assert len(kept) == len(burgers) + len(lunch) - len(overlap)


def test_앞의_카테고리가_분류를_가져간다(burgers, lunch):
    kept = {i["external_id"]: i for i in mcd.dedupe(burgers + lunch)}
    overlap = {i["external_id"] for i in burgers} & {i["external_id"] for i in lunch}
    assert all(kept[k]["category_raw"] == "버거" for k in overlap)


def test_같은_seq에_이름이_다르면_죽는다():
    """seq가 상품을 가리키지 않는다는 뜻이다. 조용히 접으면 한 건이 사라진다."""
    a = {"external_id": "1", "name": "가"}
    b = {"external_id": "1", "name": "나"}
    with pytest.raises(mcd.ParseError, match="이름이 다르다"):
        mcd.dedupe([a, b])


def test_봉투가_바뀌면_시끄럽게_죽는다():
    with pytest.raises(mcd.ParseError, match="resultObject가 없다"):
        mcd.parse_list({"list": []}, "1", scraped_at=SCRAPED_AT)


def test_모르는_카테고리는_거부한다():
    with pytest.raises(ValueError, match="모르는 카테고리"):
        mcd.parse_list({"resultObject": {}}, "6", scraped_at=SCRAPED_AT)


def test_부트스트랩_실측치가_카테고리를_전부_덮는다():
    assert set(mcd.BOOTSTRAP_COUNTS) == set(mcd.CATEGORIES)
    assert sum(mcd.BOOTSTRAP_COUNTS.values()) == 100
