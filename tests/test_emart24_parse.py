"""이마트24 파서 골든 테스트.

픽스처는 2026-08-25 실측 응답이다. 네트워크 없이 돈다.

  emart24_list_ff_p1.html   Fresh Food 1페이지 20건. NEW 라벨이 하나도 없다
  emart24_list_pl_p19.html  차별화 상품 19페이지 20건. **NEW 라벨 4건**

19페이지를 고른 이유: 이 소스의 `NEW`는 텍스트가 항상 있고 `opacity: 0`으로 숨긴다.
숨긴 것만 있는 페이지로 테스트하면 **판정이 뒤집혀도 통과한다** — 전부 false가
나오나 전부 true가 나오나 "라벨이 없다"로 보이기 때문이다. 둘 다 있어야 잡힌다.
"""

from pathlib import Path

import pytest

from scrapers import emart24

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-25T12:00:00+09:00"


def _parse(name: str, code: str):
    markup = (FIXTURES / name).read_text(encoding="utf-8")
    items, skipped = emart24.parse_list(markup, code, scraped_at=SCRAPED_AT)
    assert skipped == 0
    return items


@pytest.fixture(scope="module")
def fresh():
    return _parse("emart24_list_ff_p1.html", "ff")


@pytest.fixture(scope="module")
def private_label():
    return _parse("emart24_list_pl_p19.html", "pl")


def test_한_페이지는_20건이다(fresh, private_label):
    assert len(fresh) == emart24.PAGE_SIZE == 20
    assert len(private_label) == 20


def test_항목_모양(fresh):
    item = next(i for i in fresh if i["name"] == "구황작물 치즈감자김밥")
    assert item["source_id"] == "emart24"
    assert item["external_id"] == "8800323762973"
    assert item["alt_ids"] == {"barcode": "8800323762973"}
    assert item["price"] == 3200
    assert item["category_raw"] == "Fresh Food"
    assert item["description"] is None      # 설명문이 없는 소스다
    assert item["tags"] == []
    assert item["scraped_at"] == SCRAPED_AT
    assert item["image_url"].startswith("https://msave.emart24.co.kr/")


def test_상품_URL이_없어_목록을_가리킨다(fresh, private_label):
    """ADR-0013. 개별 상품 링크가 전부 `href="#none"`이다."""
    assert all(i["source_url"] == "https://emart24.co.kr/goods/ff" for i in fresh)
    assert all(i["source_url"] == "https://emart24.co.kr/goods/pl"
               for i in private_label)


def test_바코드는_이미지_파일명에서만_나온다(fresh, private_label):
    """주의 1번 — 이 소스에서 상품 키를 얻는 유일한 방법이다."""
    for item in fresh + private_label:
        assert item["external_id"].isdigit(), f"이름 해시로 떨어졌다: {item['name']}"
        assert item["external_id"] in item["image_url"]


def test_바코드_파싱():
    url = "https://msave.emart24.co.kr/cmsbo/upload/nHq/plu_image/500x500/8800323762973.JPG"
    assert emart24.parse_barcode(url) == "8800323762973"
    assert emart24.parse_barcode("/assets/imgs/productPlaceHolder.png") is None
    assert emart24.parse_barcode(None) is None


def test_가격_파싱():
    assert emart24.parse_price("3,200 원") == 3200
    assert emart24.parse_price("980 원") == 980
    assert emart24.parse_price("") is None
    assert emart24.parse_price(None) is None


# ── NEW 라벨 (주의 6번) ────────────────────────────────────────

def test_숨긴_NEW는_신상이_아니다(fresh):
    """`NEW` 텍스트는 전건에 있다. `opacity: 0`이면 안 보이는 것이다."""
    assert sum(i["_labels"]["new"] for i in fresh) == 0


def test_보이는_NEW만_센다(private_label):
    assert sum(i["_labels"]["new"] for i in private_label) == 4
    labelled = {i["name"] for i in private_label if i["_labels"]["new"]}
    assert "응급실)치즈쏘옥떡볶이300g" in labelled


def test_NEW_판정():
    from bs4 import BeautifulSoup

    def node(html):
        return BeautifulSoup(html, "html.parser").select_one("span")

    assert emart24.is_new(node('<span style="opacity: 0;">NEW</span>')) is False
    assert emart24.is_new(node('<span style="opacity:0">NEW</span>')) is False
    assert emart24.is_new(node("<span>NEW</span>")) is True
    assert emart24.is_new(None) is False


# ── 중복 제거 (주의 2번·3번) ──────────────────────────────────

def _item(key, name, price):
    return {"external_id": key, "name": name, "price": price}


def test_같은_바코드는_앞의_것을_남긴다():
    kept = emart24.dedupe([
        _item("880", "Fresh Food 쪽 이름", 3200),
        _item("880", "Fresh Food 쪽 이름", 3200),
    ])
    assert len(kept) == 1
    assert kept[0]["name"] == "Fresh Food 쪽 이름"


def test_이름_표기만_다르면_허용한다():
    """실측 1건 — 목록마다 자르는 길이가 다르다."""
    kept = emart24.dedupe([
        _item("880", "손종원_new뉴욕스타일베이컨샌드위치", 4200),
        _item("880", "손종원_new뉴욕스타일베이컨샌드", 4200),
    ])
    assert len(kept) == 1
    assert kept[0]["name"] == "손종원_new뉴욕스타일베이컨샌드위치"


def test_가격이_다르면_시끄럽게_죽는다():
    """CU는 *다른* 상품이 같은 바코드를 썼다(ADR-0001). 조용히 접으면 한 건이 사라진다."""
    with pytest.raises(emart24.ParseError, match="가격이 다르다"):
        emart24.dedupe([_item("880", "가", 3200), _item("880", "나", 4900)])


def test_순서를_지킨다():
    kept = emart24.dedupe([_item("1", "가", 100), _item("2", "나", 200),
                           _item("1", "가", 100), _item("3", "다", 300)])
    assert [i["external_id"] for i in kept] == ["1", "2", "3"]


def test_모르는_코드는_거부한다():
    with pytest.raises(ValueError, match="모르는 경로 코드"):
        emart24.parse_list("<html></html>", "event", scraped_at=SCRAPED_AT)


def test_행사와_시즌_기획은_긁지_않는다():
    """주의 4번 — 카탈로그가 아니라 프로모션이다."""
    assert set(emart24.CATEGORIES) == {"ff", "pl"}


def test_Fresh_Food를_먼저_긁는다():
    """주의 2번 — 순서가 중복 항목의 분류를 정한다."""
    assert list(emart24.CATEGORIES) == ["ff", "pl"]


def test_부트스트랩_실측치가_코드를_전부_덮는다():
    assert set(emart24.BOOTSTRAP_COUNTS) == set(emart24.CATEGORIES)
    assert sum(emart24.BOOTSTRAP_COUNTS.values()) == 566
