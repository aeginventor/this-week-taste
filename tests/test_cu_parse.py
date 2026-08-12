"""CU 파서 골든 테스트.

정찰 때 저장한 원본 응답을 고정 픽스처로 쓴다. 네트워크 없이 돌고,
사이트 구조가 바뀌면 여기서 먼저 깨진다. 기대값은 전부 실측치다.
"""

import re
from pathlib import Path

import pytest

from scrapers import cu

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "cu_productAjax_p1.html"
SCRAPED_AT = "2026-08-11T09:00:00+09:00"


@pytest.fixture(scope="module")
def parsed():
    items, skipped = cu.parse_list(SAMPLE.read_text(encoding="utf-8"), "10",
                                   scraped_at=SCRAPED_AT)
    return items, skipped


def test_item_count_and_no_skips(parsed):
    """실측: 간편식사 1페이지는 정확히 40건이고 이름 없는 항목이 없다."""
    items, skipped = parsed
    assert len(items) == 40
    assert skipped == 0


def test_required_fields_never_missing(parsed):
    items, _ = parsed
    for item in items:
        assert item["name"]
        assert item["price"] is not None
        assert item["image_url"]
        assert item["source_url"]
        assert item["external_id"]
        assert item["alt_ids"]["gd_idx"]


def test_all_barcodes_are_13_digits(parsed):
    """실측: 40/40이 13자리 바코드다."""
    items, _ = parsed
    barcodes = [i["alt_ids"]["barcode"] for i in items]
    assert len(barcodes) == 40
    assert all(re.fullmatch(r"\d{13}", b) for b in barcodes)


def test_underscore_suffix_stripped_from_image_filename():
    """실측: 40건 중 5건이 `8809655892303_1.jpg` 형태다. `_` 앞까지만 취해야 한다."""
    assert cu._barcode_from_image(
        "https://cdn.example/product/8809655892303_1.jpg") == "8809655892303"
    assert cu._barcode_from_image(
        "https://cdn.example/product/8809148599009.jpg") == "8809148599009"
    assert cu._barcode_from_image("https://cdn.example/product/noimage.png") is None
    assert cu._barcode_from_image(None) is None


def test_sample_contains_the_five_suffixed_filenames(parsed):
    """접미사 케이스가 픽스처에서 사라지면 이 테스트가 알려준다."""
    raw = SAMPLE.read_text(encoding="utf-8")
    assert len(re.findall(r"/product/\d+_\d+\.\w+", raw)) == 5
    items, _ = parsed
    # 그럼에도 바코드는 전부 13자리로 정리돼야 한다
    assert all(len(i["alt_ids"]["barcode"]) == 13 for i in items)


def test_protocol_relative_image_url_gets_scheme(parsed):
    items, _ = parsed
    assert all(i["image_url"].startswith("https://") for i in items)


def test_external_id_is_gd_idx_not_barcode(parsed):
    """전 카탈로그 5,082건 실측: gd_idx 중복 0건, 바코드 중복 16건.

    바코드는 물리적 제품을, gd_idx는 카탈로그 항목을 가리킨다. 우리가 발행하는 단위는
    카탈로그 항목이므로 주키는 gd_idx여야 한다. 바코드는 alt_ids에 남아 diff 1순위 키로 쓰인다.
    """
    items, _ = parsed
    assert items[0]["external_id"] == "17620"
    assert items[0]["alt_ids"]["barcode"] == "8809148599009"
    assert all(i["external_id"] == i["alt_ids"]["gd_idx"] for i in items)


def test_duplicate_barcodes_stay_distinct_items():
    """실측 사례: 같은 바코드가 가격이 다른 두 항목으로 등록돼 있다.

    바코드를 주키로 쓰면 둘 중 하나가 조용히 사라진다.
    """
    markup = """
    <li class="prod_list"><div class="prod_img" onclick="view(20181);">
      <img src="//x/product/8801114153819.jpg" class="prod_img"/></div>
      <div class="name"><p>풀무원)나주식수육곰탕</p></div>
      <div class="price"><strong>8,000</strong></div></li>
    <li class="prod_list"><div class="prod_img" onclick="view(24447);">
      <img src="//x/product/8801114153819.jpg" class="prod_img"/></div>
      <div class="name"><p>풀무원)나주식수육곰탕</p></div>
      <div class="price"><strong>9,900</strong></div></li>
    """
    items, skipped = cu.parse_list(markup, "50", scraped_at=SCRAPED_AT)
    assert skipped == 0
    assert len(items) == 2
    assert {i["external_id"] for i in items} == {"20181", "24447"}
    assert {i["alt_ids"]["barcode"] for i in items} == {"8801114153819"}
    assert {i["price"] for i in items} == {8000, 9900}


def test_source_url_points_at_detail_page(parsed):
    items, _ = parsed
    assert items[0]["source_url"] == (
        "https://cu.bgfretail.com/product/view.do?category=product&gdIdx=17620")


def test_known_first_item(parsed):
    """정찰 보고서에 인용된 첫 항목. 값이 바뀌면 사이트가 바뀐 것이다."""
    items, _ = parsed
    assert items[0]["name"] == "샐)오리지널닭가슴살샐러"
    assert items[0]["price"] == 4800
    assert items[0]["category_raw"] == "간편식사"
    assert items[0]["source_id"] == "cu"


def test_name_truncation_is_source_side(parsed):
    """실측: 최대 길이 12자, 9건이 정확히 12자. 소스가 자른 것이므로 복원하지 않는다."""
    items, _ = parsed
    lengths = [len(i["name"]) for i in items]
    assert max(lengths) == 12
    assert sum(1 for n in lengths if n == 12) == 9


def test_new_label_is_not_part_of_the_snapshot_item(parsed):
    """소스의 신상 라벨은 판정에 쓰지 않는다(2.1). `_` 접두 키로만 실어 보낸다."""
    items, _ = parsed
    assert all("_labels" in i for i in items)
    assert all(not k.startswith("_") or k == "_labels" for i in items for k in i)
    # 1페이지는 gdIdx 오름차순의 맨 앞(=가장 오래된 상품)이라 NEW 라벨이 없다
    assert sum(1 for i in items if i["_labels"]["new"]) == 0


def test_gd_idx_is_ascending(parsed):
    """목록이 gdIdx 오름차순이라는 전제. 신상은 마지막 페이지에 있다."""
    items, _ = parsed
    gd = [int(i["alt_ids"]["gd_idx"]) for i in items]
    assert gd == sorted(gd)
    assert gd[0] == 17620 and gd[-1] == 26420


def test_has_next_page_detects_more_button():
    raw = SAMPLE.read_text(encoding="utf-8")
    assert cu.has_next_page(raw) is True
    assert cu.has_next_page("<ul></ul>") is False


def test_price_parsing_variants():
    from bs4 import BeautifulSoup
    def price(markup):
        return cu._parse_price(BeautifulSoup(markup, "html.parser").select_one("strong"))
    assert price("<strong>4,800</strong>") == 4800
    assert price("<strong>980</strong>") == 980
    assert price("<strong></strong>") is None
    assert price("<strong>가격미정</strong>") is None


def test_nameless_block_is_skipped_not_crashed():
    """5장: 파서는 방어적으로. 대신 건너뛴 수를 돌려주어 호출자가 시끄럽게 실패한다."""
    markup = """
    <li class="prod_list"><div class="prod_img" onclick="view(1);">
      <img src="//x/product/8801234567890.jpg" class="prod_img"/></div>
      <div class="name"><p></p></div></li>
    """
    items, skipped = cu.parse_list(markup, "10", scraped_at=SCRAPED_AT)
    assert items == []
    assert skipped == 1


def test_unknown_category_code_rejected():
    with pytest.raises(ValueError):
        cu.parse_list("", "99", scraped_at=SCRAPED_AT)
