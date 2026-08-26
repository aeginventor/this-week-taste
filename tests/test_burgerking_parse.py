"""버거킹 파서 골든 테스트.

픽스처는 2026-08-26 실측 응답이다. 네트워크 없이 돈다.

  burgerking_list_all.json        전체 메뉴 (BKR0632). 9분류 239행
  burgerking_detail_7714341.json  상세 1건 — 세트, NEW 플래그, 키워드 6개
  burgerking_detail_1100808.json  상세 1건 — 단품, 플래그 없음, 키워드 3개

목록 픽스처가 하나뿐인 이유는 **이 소스의 전체 카탈로그가 요청 1건이기 때문이다.**
대신 그 한 응답 안에 이 소스의 함정이 전부 들어 있다 — 판촉 탭, 분류 간 중복,
같은 이름 다른 코드, 이름 끝 공백.
"""

import json
from pathlib import Path

import pytest

from scrapers import burgerking

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-26T09:00:00+09:00"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def items():
    return burgerking.parse_list(_text("burgerking_list_all.json"), scraped_at=SCRAPED_AT)


# ── 봉투 ─────────────────────────────────────────────────────────
#
# 정찰이 여기서 1년치 막혔다. 봉투가 틀리면 HTTP 400이 오고 소스 전체가 0건이 된다.


def test_봉투가_bizMOB_형식이다():
    message = burgerking.envelope("BKR0632", {"menuKeywordList": []})

    assert message["header"]["trcode"] == "BKR0632"
    assert message["header"]["result"] is True
    assert message["header"]["cd_call_chnn"] == "01"
    assert message["body"] == {"menuKeywordList": []}


def test_서버가_실패라고_하면_예외다():
    """⚠️ HTTP 200에 실패가 실려 온다. 헤더를 안 보면 빈 목록을 정상으로 삼킨다."""
    failed = json.dumps({"header": {"result": False, "error_code": "BSVP0001",
                                    "error_text": "처리 중 오류"}, "body": {}})
    with pytest.raises(burgerking.ParseError, match="BSVP0001"):
        burgerking.parse_envelope(failed, "BKR0632")


def test_목록이_비면_예외다():
    empty = json.dumps({"header": {"result": True}, "body": {"allMenuList": []}})
    with pytest.raises(burgerking.ParseError, match="allMenuList"):
        burgerking.parse_list(empty, scraped_at=SCRAPED_AT)


def test_모르는_분류는_예외다():
    """분류가 늘면 사람이 CATEGORIES에 넣어야 한다. 조용히 건수에서 빠지면 안 된다."""
    payload = json.dumps({"header": {"result": True}, "body": {"allMenuList": [
        {"menuCategoryCd": "K299999", "menuCategorySeq": "1", "menuCategoryNm": "새분류",
         "menuInfo": [{"menuCd": "1", "menuNm": "새 메뉴"}]},
    ]}})
    with pytest.raises(burgerking.ParseError, match="K299999"):
        burgerking.parse_list(payload, scraped_at=SCRAPED_AT)


# ── 목록 ─────────────────────────────────────────────────────────


def test_전체_건수(items):
    """239행이 온다. 같은 코드를 접으면 192건이다."""
    assert len(items) == 192
    assert len({i["external_id"] for i in items}) == 192


def test_분류별_건수가_부트스트랩과_같다(items):
    counts = {}
    for item in items:
        counts[item["category_raw"]] = counts.get(item["category_raw"], 0) + 1
    expected = {burgerking.CATEGORIES[code]: n
                for code, n in burgerking.BOOTSTRAP_COUNTS.items() if n}
    assert counts == expected


def test_추천메뉴는_분류로_쓰이지_않는다(items):
    """판촉 탭이다. 26건 전부 다른 분류에도 있어서 그쪽이 이긴다(주의 2번).

    빼버리지 않고 뒤로 미루는 이유: 여기에만 있는 항목이 생기면 잃으면 안 된다.
    그날은 이 테스트가 깨지고, 그것이 알림이다.
    """
    assert not [i for i in items if i["category_raw"] == "추천메뉴"]


def test_같은_이름_다른_코드는_접지_않는다(items):
    """정규 메뉴와 올데이킹에 같은 제품이 다른 코드로 실린다(16쌍, 주의 4번).

    이름으로 접으면 그 한 쌍이 사라지고, 다음 주 diff가 없던 신상을 만들어낸다.
    """
    pairs = [i for i in items if i["name"] == "콰트로치즈와퍼주니어 세트"]
    assert len(pairs) == 2
    assert {i["external_id"] for i in pairs} == {"7714025", "7130282"}
    assert {i["category_raw"] for i in pairs} == {"와퍼&주니어", "올데이스낵&올데이킹"}


def test_이름_끝_공백을_뗀다(items):
    """9건이 공백을 달고 온다. 두면 소스가 고치는 순간 diff가 이름 변경으로 잡는다."""
    assert not [i for i in items if i["name"] != i["name"].strip()]
    assert [i for i in items if i["name"] == "와퍼주니어 라지세트"]


def test_스냅샷_항목의_모양(items):
    item = next(i for i in items if i["external_id"] == "7714341")

    assert item["source_id"] == "burgerking"
    assert item["name"] == "몬스터 맥시멈 라지세트"
    assert item["price"] is None                # 주의 5번
    assert item["description"] is None          # 주의 6번 — 상세가 준다
    assert item["tags"] == []
    assert item["category_raw"] == "오리지널스&맥시멈"
    assert item["image_url"].startswith("https://mob-prd.burgerking.co.kr/")
    assert item["source_url"] == "https://www.burgerking.co.kr/menu/detail/7714341"
    assert item["scraped_at"] == SCRAPED_AT


def test_모든_항목이_이미지와_상품_URL을_갖는다(items):
    assert not [i for i in items if not i["image_url"]]
    assert not [i for i in items if not i["source_url"].endswith(i["external_id"])]


def test_NEW는_대조군으로만_남는다(items):
    """판정에 쓰지 않는다(2.1). 192건 중 46건이라 비율이 높다 — 채점표로도 아직 못 쓴다."""
    labelled = [i for i in items if i["_labels"]["new"]]
    assert len(labelled) == 46
    assert all("new" not in i for i in items)


# ── 상세 ─────────────────────────────────────────────────────────


def test_상세가_설명문과_태그를_준다():
    detail = burgerking.parse_detail(_text("burgerking_detail_7714341.json"))

    assert detail["name"] == "몬스터 맥시멈 라지세트"
    assert detail["description"] == "몬스터, 맥시멈으로 등장"
    assert "맥시멈" in detail["tags"]
    assert len(detail["tags"]) == 6


def test_상세의_이름이_목록과_같다(items):
    """`enrich.py`가 목록과 상세의 이름을 대조한다. 어긋나면 보강이 통째로 버려진다."""
    detail = burgerking.parse_detail(_text("burgerking_detail_1100808.json"))
    listed = next(i for i in items if i["external_id"] == "1100808")

    assert detail["name"] == listed["name"] == "콰트로치즈와퍼주니어"
    assert detail["description"].startswith("진짜 불맛을 즐겨라")
    assert detail["tags"] == ["와퍼주니어", "치즈", "진한맛"]
