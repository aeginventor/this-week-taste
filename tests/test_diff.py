"""diff의 제품 동일성 판정 테스트.

CLAUDE.md 7장이 명시적으로 허용한 테스트 대상이다. 여기가 깨지면 신상 판정이 틀리고,
신상 판정이 틀리면 이 프로젝트가 하는 일이 없다.
"""

import copy

import pytest

from pipeline.diff import SIMILARITY_THRESHOLD, diff_items


def item(name, price, *, barcode=None, gd_idx=None, category="간편식사", image=None):
    alt = {}
    if barcode:
        alt["barcode"] = barcode
    if gd_idx:
        alt["gd_idx"] = gd_idx
    return {
        "source_id": "cu",
        "external_id": barcode or f"gd{gd_idx}",
        "alt_ids": alt,
        "name": name,
        "price": price,
        "category_raw": category,
        "image_url": image or f"https://cdn.example/{barcode or gd_idx}.jpg",
        "source_url": f"https://cu.bgfretail.com/product/view.do?gdIdx={gd_idx}",
        "scraped_at": "2026-08-11T09:00:00+09:00",
    }


@pytest.fixture
def base_week():
    return [
        item("샐)오리지널닭가슴살샐러", 4800, barcode="8809148599009", gd_idx="17620"),
        item("삼)치킨마요삼각", 1400, barcode="8801771035527", gd_idx="20001"),
        item("빅삼)치킨마요삼각", 1700, barcode="8800336392051", gd_idx="20002"),
    ]


# ── 항등성 ───────────────────────────────────────────────────────

def test_identical_snapshots_produce_no_changes(base_week):
    result = diff_items(base_week, copy.deepcopy(base_week))
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0
    assert result["counts"]["changed"] == 0
    assert result["counts"]["review"] == 0
    assert result["counts"]["matched"] == 3


def test_empty_previous_week_makes_everything_added(base_week):
    result = diff_items([], base_week)
    assert result["counts"]["added"] == 3
    assert result["counts"]["removed"] == 0


# ── 이름이 미묘하게 바뀌는 경우 ───────────────────────────────────

def test_renamed_product_is_changed_not_added_and_removed(base_week):
    """계획의 핵심 질문. 이름이 한 글자 바뀌어도 키가 살아 있으면 같은 제품이다."""
    current = copy.deepcopy(base_week)
    current[0]["name"] = "샐)오리지날닭가슴살샐러"  # 널 → 날

    result = diff_items(base_week, current)
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0
    assert result["counts"]["changed"] == 1
    assert result["changed"][0]["matched_by"] == "barcode"
    assert result["changed"][0]["fields"]["name"] == {
        "from": "샐)오리지널닭가슴살샐러", "to": "샐)오리지날닭가슴살샐러"}


def test_price_change_only_is_changed(base_week):
    current = copy.deepcopy(base_week)
    current[0]["price"] = 5200
    result = diff_items(base_week, current)
    assert result["counts"] == {**result["counts"], "added": 0, "removed": 0, "changed": 1}
    assert result["changed"][0]["fields"]["price"] == {"from": 4800, "to": 5200}


def test_barcode_reissued_still_matches_by_gd_idx(base_week):
    """바코드가 바뀌어도 gdIdx가 같으면 같은 제품이다 (L2)."""
    current = copy.deepcopy(base_week)
    current[0]["alt_ids"]["barcode"] = "8809148599999"
    current[0]["external_id"] = "8809148599999"

    result = diff_items(base_week, current)
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0
    assert result["changed"] == [] or result["changed"][0]["matched_by"] == "gd_idx"
    assert result["counts"]["conflicts"] == 1
    assert result["conflicts"][0]["conflicting_key"] == "barcode"


def test_both_keys_changed_falls_back_to_name_and_price(base_week):
    """두 키가 모두 바뀌어도 이름+가격이 같으면 같은 제품이다 (L3)."""
    current = copy.deepcopy(base_week)
    current[0]["alt_ids"] = {}
    current[0]["external_id"] = "nhdeadbeef0000"

    result = diff_items(base_week, current)
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0
    assert result["counts"]["matched"] == 3


# ── POS 접두사 회귀 (실측 근거) ──────────────────────────────────

def test_pos_prefix_variants_are_never_merged(base_week):
    """`삼)`과 `빅삼)`은 다른 상품이다. 접두사를 정규화로 지우면 여기서 깨진다."""
    current = copy.deepcopy(base_week)
    result = diff_items(base_week, current)
    assert result["counts"]["matched"] == 3
    assert result["counts"]["review"] == 0

    # 한쪽만 단종된 경우에도 다른 쪽으로 흡수되면 안 된다
    current_without_big = [i for i in copy.deepcopy(base_week)
                           if not i["name"].startswith("빅삼)")]
    result = diff_items(base_week, current_without_big)
    assert result["counts"]["removed"] == 1
    assert result["removed"][0]["name"] == "빅삼)치킨마요삼각"
    assert result["counts"]["added"] == 0


def test_same_truncated_name_different_price_stays_separate():
    """CU는 이름을 12자에서 자른다. 이름만으로 같다고 판정하면 안 된다."""
    previous = [item("샐)오리지널닭가슴살샐러", 4800, barcode="1111111111111", gd_idx="1")]
    current = [
        item("샐)오리지널닭가슴살샐러", 4800, barcode="1111111111111", gd_idx="1"),
        item("샐)오리지널닭가슴살샐러", 6500, barcode="2222222222222", gd_idx="2"),
    ]
    result = diff_items(previous, current)
    assert result["counts"]["added"] == 1
    assert result["added"][0]["price"] == 6500
    assert result["counts"]["removed"] == 0


# ── added / removed ──────────────────────────────────────────────

def test_new_product_is_added(base_week):
    current = base_week + [item("도)신상돈까스", 4900, barcode="8809999999999", gd_idx="30000")]
    result = diff_items(base_week, current)
    assert result["counts"]["added"] == 1
    assert result["added"][0]["name"] == "도)신상돈까스"
    assert result["counts"]["removed"] == 0


def test_disappeared_product_is_removed(base_week):
    result = diff_items(base_week, base_week[:-1])
    assert result["counts"]["removed"] == 1
    assert result["removed"][0]["name"] == "빅삼)치킨마요삼각"


# ── L4 보류 ──────────────────────────────────────────────────────

def test_uncertain_pair_goes_to_review_not_added_or_removed():
    """키가 전부 바뀌고 가격도 바뀌면 확신할 수 없다. 자동 판정하지 않는다."""
    previous = [item("샐)오리지널닭가슴살샐러", 4800, barcode="1111111111111", gd_idx="1")]
    current = [item("샐)오리지날닭가슴살샐러", 5200, barcode="9999999999999", gd_idx="9")]

    result = diff_items(previous, current)
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0
    assert result["counts"]["review"] == 1
    assert result["review"][0]["similarity"] >= SIMILARITY_THRESHOLD


def test_review_does_not_cross_categories():
    previous = [item("샐)오리지널닭가슴살샐러", 4800, barcode="1", gd_idx="1",
                     category="간편식사")]
    current = [item("샐)오리지날닭가슴살샐러", 5200, barcode="9", gd_idx="9",
                    category="음료")]
    result = diff_items(previous, current)
    assert result["counts"]["review"] == 0
    assert result["counts"]["added"] == 1
    assert result["counts"]["removed"] == 1


def test_unrelated_products_are_not_reviewed():
    previous = [item("샐)오리지널닭가슴살샐러", 4800, barcode="1", gd_idx="1")]
    current = [item("음)제로콜라500", 2000, barcode="9", gd_idx="9")]
    result = diff_items(previous, current)
    assert result["counts"]["review"] == 0
    assert result["counts"]["added"] == 1
    assert result["counts"]["removed"] == 1


# ── 1:1 매칭 ─────────────────────────────────────────────────────

def test_matching_is_strictly_one_to_one():
    """지난주 항목 하나가 이번 주 두 항목에 동시에 매칭되면 안 된다."""
    previous = [item("삼)치킨마요삼각", 1400, barcode="1111111111111", gd_idx="1")]
    current = [
        item("삼)치킨마요삼각", 1400, barcode="1111111111111", gd_idx="1"),
        item("삼)치킨마요삼각", 1400, barcode="2222222222222", gd_idx="2"),
    ]
    result = diff_items(previous, current)
    assert result["counts"]["matched"] == 1
    assert result["counts"]["added"] == 1
    assert result["counts"]["removed"] == 0
