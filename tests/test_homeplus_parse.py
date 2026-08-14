"""홈플러스 목록 파서 골든 테스트 (CLAUDE.md 7장).

`tests/fixtures/homeplus_list_200095.json`은 2026-08-13에 실제로 받은
`과자/시리얼 > 과자/쿠키/파이` 1페이지 응답이다. 네트워크 없이 돈다.
"""

import copy
import json
from pathlib import Path

import pytest

from scrapers import homeplus

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "homeplus_list_200095.json"
CATEGORY = "200095"
SCRAPED_AT = "2026-08-13T09:00:00+09:00"


@pytest.fixture(scope="module")
def payload():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed(payload):
    items, total_page = homeplus.parse_list(payload, CATEGORY, scraped_at=SCRAPED_AT)
    assert total_page == 2
    return items


def test_한_페이지_100건(parsed):
    """perPage 상한이 100이다. 이 값이 바뀌면 요청 수 계산이 통째로 달라진다."""
    assert len(parsed) == 100


def test_이름이_잘리지_않는다(parsed):
    """CU는 12자에서 잘려 오지만 홈플러스는 온전히 온다.

    이 차이가 curate에 직결된다 — 이름이 온전하면 blurb의 근거가 될 수 있다.
    """
    names = [i["name"] for i in parsed]
    assert "해태 오예스 360G" in names
    assert max(len(n) for n in names) > 12


def test_카테고리는_응답_원문을_쓴다(parsed):
    assert {i["category_raw"] for i in parsed} == {"과자/시리얼 > 과자/쿠키/파이"}


def test_카테고리가_기대와_어긋나면_예외(payload):
    """소스가 트리를 개편하면 조용히 지나가지 않고 멈춰야 한다.

    `snapshot.py`의 건수 검증은 이름 → 코드 역매핑에 기대므로, 이름이 바뀌면
    그 카테고리는 통째로 집계에서 빠지고 '기준에 없던 카테고리' 경고 한 줄로만 남는다.
    """
    broken = copy.deepcopy(payload)
    broken["data"]["dataList"][0]["mcateNm"] = "과자/쿠키/파이/신설"
    with pytest.raises(homeplus.ParseError, match="카테고리 트리를 바꿨"):
        homeplus.parse_list(broken, CATEGORY, scraped_at=SCRAPED_AT)


def test_가격은_정가이지_행사가가_아니다(payload, parsed):
    """dcPrice는 매주 바뀌는 행사가다. 그걸 넣으면 diff의 changed가 할인으로 뒤덮인다."""
    rows = {r["itemNo"]: r for r in payload["data"]["dataList"]}
    for item in parsed:
        assert item["price"] == rows[item["external_id"]]["salePrice"]


def test_이미지는_itemNo에서_만든다(parsed):
    item = next(i for i in parsed if i["external_id"] == "128513638")
    assert item["image_url"] == "https://image.homeplus.kr/it/128513638s0640"


def test_이미지가_없는_상품은_null(payload):
    """없는 itemNo도 HTTP 200 + 플레이스홀더를 주므로 imgDispYn이 유일한 근거다.

    URL을 만들 수 있다는 것과 이미지가 있다는 것은 다른 얘기다. 이 구분이 없으면
    이미지 없는 상품 전부가 회색 플레이스홀더로 발행된다.
    """
    one = copy.deepcopy(payload)
    one["data"]["dataList"] = one["data"]["dataList"][:1]
    one["data"]["dataList"][0]["imgDispYn"] = "N"
    items, _ = homeplus.parse_list(one, CATEGORY, scraped_at=SCRAPED_AT)
    assert items[0]["image_url"] is None


def test_상세_URL은_storeType을_쓴다(parsed):
    """storeId를 넣으면 '현재 판매중인 상품이 아닙니다' 껍데기가 온다. 실측으로 확인했다."""
    url = parsed[0]["source_url"]
    assert "storeType=" in url and "storeId=" not in url


def test_설명문은_항상_없다(parsed):
    """상세에도 텍스트 설명이 없어(표본 51건 중 1건) enrich를 붙이지 않는다.

    blurb를 이름만 보고 짓지 않기 위해 이 값이 None으로 유지되어야 한다 (6장).
    """
    assert all(i["description"] is None for i in parsed)


def test_external_id가_페이지_안에서_유일하다(parsed):
    assert len({i["external_id"] for i in parsed}) == len(parsed)


def test_returnCode가_SUCCESS가_아니면_예외(payload):
    broken = copy.deepcopy(payload)
    broken["returnCode"] = "FAIL"
    with pytest.raises(homeplus.ParseError):
        homeplus.parse_list(broken, CATEGORY, scraped_at=SCRAPED_AT)
