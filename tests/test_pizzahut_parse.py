"""피자헛 파서 골든 테스트.

픽스처는 2026-08-26 실측 응답이다. 네트워크 없이 돈다.

  pizzahut_pizza_all.json     GET /api/menu/pizza/all/VISIT           대표 17종
  pizzahut_cheesefesta.json   GET /api/menu/0767/list/cheesefesta/VISIT  피자 8 + 파스타 1

**픽스처가 둘인 것 자체가 이 소스의 함정이다.** `pizza/all`은 이름과 달리 전체가
아니어서 판촉 탭 8건이 빠진다. 하나만 두면 그 사실이 테스트에서 사라진다.

상세 픽스처가 없는 이유는 **상세가 목록보다 주는 것이 없어서 아예 긁지 않기 때문이다**
(`detail: False`).
"""

import json
from pathlib import Path

import pytest

from scrapers import pizzahut

FIXTURES = Path(__file__).parent / "fixtures"
SCRAPED_AT = "2026-08-26T09:00:00+09:00"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def items():
    """`fetch()`가 두 탭을 합치는 것과 같은 순서로 합친다."""
    merged: dict[str, dict] = {}
    for name, mixed in (("pizzahut_pizza_all.json", False),
                        ("pizzahut_cheesefesta.json", True)):
        for item in pizzahut.parse_list(_text(name), scraped_at=SCRAPED_AT, mixed=mixed):
            merged.setdefault(item["external_id"], item)
    return list(merged.values())


# ── 응답 모양 ────────────────────────────────────────────────────
#
# 이 소스는 **HTTP 200에 오류 본문을 실어 보내는 경로가 있다** —
# `/menu/pastaandside/all`이 `{"type":"MessageException", ...}`를 준다.
# 배열인지 보지 않으면 그것을 빈 목록으로 삼킨다.


def test_배열이_아니면_예외다():
    error = json.dumps({"type": "MessageException", "message": "메뉴를 찾을 수 없습니다.",
                        "status": 400})
    with pytest.raises(pizzahut.ParseError, match="배열이 아니다"):
        pizzahut.parse_list(error, scraped_at=SCRAPED_AT)


def test_목록이_비면_예외다():
    with pytest.raises(pizzahut.ParseError, match="비었다"):
        pizzahut.parse_list("[]", scraped_at=SCRAPED_AT)


def test_JSON이_아니면_예외다():
    with pytest.raises(pizzahut.ParseError, match="JSON이 아니다"):
        pizzahut.parse_list("<!doctype html><html>SPA 껍데기</html>",
                            scraped_at=SCRAPED_AT)


def test_모르는_분류는_예외다():
    """분류가 늘면 사람이 CATEGORIES에 넣어야 한다. 조용히 건수에서 빠지면 안 된다.

    `main.js`가 아는 sclass만 해도 MG(메가)·PN(팬)·OH·FZ가 더 있다. 그중 하나가
    목록에 등장하는 날 이 예외가 알린다.
    """
    payload = json.dumps([{"lclass": "P", "mclass": "PZ", "sclass": "MG",
                           "rpstMenuCd": "RPPZ9999", "digitalKey": "RPPZ9999",
                           "rpstName": "메가 피자", "items": []}])
    with pytest.raises(pizzahut.ParseError, match="MG"):
        pizzahut.parse_list(payload, scraped_at=SCRAPED_AT)


# ── 두 탭 ────────────────────────────────────────────────────────
#
# ⚠️ 여기가 이 소스에서 제일 중요한 자리다. `/menu/pizza/all`은 **전체가 아니다.**


def test_pizza_all이_전체가_아니다():
    """이름이 `all`인데 프리미엄+US오리진뿐이다. 치즈페스타 8건이 통째로 빠진다.

    이 테스트가 깨지는 날은 소스가 `all`을 진짜 전체로 고친 날이다. 그때는
    두 번째 요청을 지워야 한다 — 그 판단을 사람이 하라고 여기 남긴다.
    """
    only_all = pizzahut.parse_list(_text("pizzahut_pizza_all.json"),
                                   scraped_at=SCRAPED_AT)
    assert len(only_all) == 17
    assert {i["category_raw"] for i in only_all} == {"프리미엄", "US오리진"}


def test_판촉_탭이_피자가_아닌_것을_섞어_준다():
    """치즈페스타 응답 9행 중 1행이 파스타(mclass SD)다. 피자만 남긴다."""
    rows = json.loads(_text("pizzahut_cheesefesta.json"))
    assert len(rows) == 9
    assert len([r for r in rows if r["mclass"] != "PZ"]) == 1

    parsed = pizzahut.parse_list(_text("pizzahut_cheesefesta.json"),
                                 scraped_at=SCRAPED_AT, mixed=True)
    assert len(parsed) == 8
    assert {i["category_raw"] for i in parsed} == {"3x 치즈페스타"}


def test_섞임을_허용하지_않는_탭에서는_예외다():
    """`pizza/all`에 사이드가 섞이면 목록의 성격이 바뀐 것이다 — 조용히 넘기지 않는다."""
    with pytest.raises(pizzahut.ParseError, match="mclass"):
        pizzahut.parse_list(_text("pizzahut_cheesefesta.json"), scraped_at=SCRAPED_AT)


def test_전체_건수(items):
    """두 탭을 합쳐 25건. `items`의 사이즈는 별개 항목이 아니다(주의 4번)."""
    assert len(items) == 25
    assert len({i["external_id"] for i in items}) == 25


def test_분류별_건수가_부트스트랩과_같다(items):
    counts = {}
    for item in items:
        counts[item["category_raw"]] = counts.get(item["category_raw"], 0) + 1
    expected = {pizzahut.CATEGORIES[code]: n
                for code, n in pizzahut.BOOTSTRAP_COUNTS.items() if n}
    assert counts == expected


def test_부트스트랩이_판촉_탭을_포함한다():
    """치즈페스타 요청이 실패하면 건수 검증이 시끄럽게 실패해야 한다 (2.4).

    CF를 기준에서 빼면 그 탭이 통째로 사라져도 스냅샷이 조용히 통과한다.
    """
    assert pizzahut.BOOTSTRAP_COUNTS["CF"] == 8


def test_대표_코드가_중복이면_예외다():
    """같은 대표 코드가 한 응답에 두 번 오면 접지 않고 시끄럽게 실패한다.

    버거킹은 한 항목이 여러 분류에 실려서 접어야 했지만, 이 목록은 대표 단위라
    한 응답 안의 중복은 그것 자체가 이상 신호다. (탭 사이의 중복은 `fetch()`가 접는다.)
    """
    row = {"lclass": "P", "mclass": "PZ", "sclass": "PM", "rpstMenuCd": "RPPZ0007",
           "digitalKey": "RPPZ0007", "rpstName": "베이컨포테이토", "items": []}
    with pytest.raises(pizzahut.ParseError, match="중복"):
        pizzahut.parse_list(json.dumps([row, row]), scraped_at=SCRAPED_AT)


# ── 스냅샷 항목 ──────────────────────────────────────────────────


def test_설명문을_전부_준다(items):
    """25/25. 이래서 `detail: False`다 — 이미 가진 것을 버리고 다시 긁지 않는다."""
    assert not [i for i in items if not i["description"]]


def test_스냅샷_항목의_모양(items):
    item = next(i for i in items if i["external_id"] == "RPPZ2275")

    assert item["source_id"] == "pizzahut"
    assert item["name"] == "쓰리스타 시그니처"
    assert item["price"] == 37900                  # L만 있는 5종 중 하나
    assert item["category_raw"] == "프리미엄"
    assert item["description"].startswith("쓰리스타 킬러 셰프가")
    assert item["tags"] == []
    assert item["alt_ids"] == {"rpst_seq": 2275}
    assert item["image_url"] == (
        "https://akamai.pizzahut.co.kr/2020pizzahut-prod/public"
        "/img/menu/RPPZ2275_s.png")
    assert item["source_url"] == "https://www.pizzahut.co.kr/menu/pizza/premium/RPPZ2275"
    assert item["scraped_at"] == SCRAPED_AT


def test_가격은_사이즈_최저가다(items):
    """L·M 둘 다 있으면 M이 싸다(주의 5번). 도미노와 같은 처리다."""
    supreme = next(i for i in items if i["external_id"] == "RPPZ0008")
    assert supreme["name"] == "수퍼슈프림"
    assert supreme["price"] == 28500               # M 28,500 / L 33,900


def test_가격이_없으면_null이다():
    """사이즈가 하나도 없거나 값이 0이면 지어내지 않는다 (4장)."""
    payload = json.dumps([{"lclass": "P", "mclass": "PZ", "sclass": "US",
                           "rpstMenuCd": "RPPZ1888", "digitalKey": "RPPZ1888",
                           "rpstName": "치즈 러버", "rpstDesc": "설명",
                           "items": [{"price": 0}]}])
    assert pizzahut.parse_list(payload, scraped_at=SCRAPED_AT)[0]["price"] is None


def test_모든_항목이_가격과_이미지와_상품_URL을_갖는다(items):
    assert not [i for i in items if i["price"] is None]
    assert not [i for i in items if not i["image_url"]]
    assert not [i for i in items if not i["source_url"]]


def test_상품_URL이_분류에_따라_갈린다(items):
    """`main.js`의 `cpath`에서 역산했다. PM은 /premium/, US는 /usoriginal/."""
    by_category = {}
    for item in items:
        by_category.setdefault(item["category_raw"], []).append(item)

    assert all("/menu/pizza/premium/" in i["source_url"]
               for i in by_category["프리미엄"])
    assert all("/menu/pizza/usoriginal/" in i["source_url"]
               for i in by_category["US오리진"])
    assert all(i["source_url"].endswith(i["external_id"])
               for i in by_category["프리미엄"] + by_category["US오리진"])


def test_치즈페스타는_목록_페이지를_쓴다(items):
    """⚠️ CF는 개별 상품 URL이 없다 — `cpath`가 분기하지 않고 브라우저에서도
    카드를 눌러 URL이 바뀌지 않는다. ADR-0013의 2층이다(이마트24와 같은 자리)."""
    cf = [i for i in items if i["category_raw"] == "3x 치즈페스타"]
    assert len(cf) == 8
    assert {i["source_url"] for i in cf} == {
        "https://www.pizzahut.co.kr/menu/pizza/cheesefesta"}


# ── 단조 증가 키 ─────────────────────────────────────────────────
#
# `publish.py`의 오탐 지표가 이 값을 `int()`로 읽는다. 없거나 틀리면
# 신상 전량이 "등록 순서를 거스름"으로 집계된다(7장의 `gd_idx_monotonic` 사고).


def test_단조_증가_키가_실린다(items):
    assert all(isinstance(i["alt_ids"]["rpst_seq"], int) for i in items)


def test_출시일_순서와_대표_코드_순서가_같다(items):
    """6년치 25건이 어긋나지 않는다. 이 소스에 `monotonic_key`를 넣은 근거다.

    ⚠️ `saleStartDate`는 **판정에 쓰지 않는다**(2.1). 여기서만, 그 키를 지표로
    쓸 자격이 있는지 확인하는 데 쓴다.
    """
    by_code = {i["external_id"]: i["alt_ids"]["rpst_seq"] for i in items}

    dated = []
    for name in ("pizzahut_pizza_all.json", "pizzahut_cheesefesta.json"):
        for row in json.loads(_text(name)):
            if row["rpstMenuCd"] not in by_code:
                continue
            starts = sorted(s for s in (i.get("saleStartDate")
                                        for i in (row.get("items") or [])) if s)
            if starts:
                dated.append((starts[0], by_code[row["rpstMenuCd"]]))

    assert len(dated) == 25
    sequences = [seq for _, seq in sorted(dated)]
    assert sequences == sorted(sequences)


def test_접두사가_다르면_지표를_지어내지_않는다():
    """틀린 지표는 없는 지표보다 나쁘다 (7장)."""
    payload = json.dumps([{"lclass": "P", "mclass": "PZ", "sclass": "PM",
                           "rpstMenuCd": "XX0001", "digitalKey": "XX0001",
                           "rpstName": "형식이 바뀐 코드", "items": [{"price": 1000}]}])
    assert pizzahut.parse_list(payload, scraped_at=SCRAPED_AT)[0]["alt_ids"] == {}


# ── 대조군 ───────────────────────────────────────────────────────


def test_NEW는_대조군으로만_남는다(items):
    """판정에 쓰지 않는다(2.1). 25건 중 2건 — W37에 "지난주에도 붙어 있었나"를
    확인하기 전에는 채점표로도 쓰지 않는다."""
    labelled = [i for i in items if i["_labels"]["new"]]
    assert len(labelled) == 2
    assert all("new" not in i for i in items)
