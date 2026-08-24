"""LLM 응답 파싱 (CLAUDE.md 7장: 외부에서 들어온 값의 모양에 의존하는 코드).

여기 있는 케이스는 전부 **실제로 겪은 것**이다. 2026-08-12에 `curate.py`를
실제 데이터 20건으로 처음 돌리면서 나왔다.

api 경로는 `OUTPUT_SCHEMA`가 모양을 강제하지만 cli 경로(`claude -p`)는 스키마를
쓸 수 없다. 그래서 응답이 매번 같은 모양으로 오지 않는다. 어긋났을 때 예외가
올라가면 그 주 발행 전체가 죽고, 조용히 넘어가면 전량이 원본으로 나가는데
아무도 모른다. 둘 다 안 된다.
"""

import json

import pytest

from pipeline import curate


# ── _entries: 모양 판별 ──────────────────────────────────────────────

def test_스키마대로_온_응답():
    parsed = {"items": [{"ref": "r0", "name": "온세)떠먹는패션피치케익"}]}
    assert curate._entries(parsed) == {
        "r0": {"ref": "r0", "name": "온세)떠먹는패션피치케익"}}


def test_맨_배열로_온_응답도_받는다():
    """2026-08-12 실측: cli 경로가 {"items":[...]} 대신 [...] 를 돌려줬다.

    이때 `parsed.get("items")`가 AttributeError를 내면서 발행 전체가 죽었다.
    """
    parsed = [{"ref": "r0", "name": "온세)떠먹는패션피치케익"}]
    assert curate._entries(parsed) == {
        "r0": {"ref": "r0", "name": "온세)떠먹는패션피치케익"}}


@pytest.mark.parametrize("parsed", [
    "그냥 문자열",
    {"result": "items가 아닌 키"},
    {"items": "리스트가 아님"},
    42,
    None,
])
def test_모르는_모양은_None(parsed):
    """None은 '재시도해라'는 신호다. 예외를 던지면 발행이 죽는다."""
    assert curate._entries(parsed) is None


def test_ref_없는_항목은_버린다():
    parsed = [
        {"ref": "r0", "name": "제품A"},
        {"name": "ref가 없다"},
        {"ref": 123, "name": "숫자라 키로 못 쓴다"},
        None,
    ]
    assert list(curate._entries(parsed)) == ["r0"]


def test_상품_키를_LLM에_보내지_않는다():
    """홈플러스 itemNo(`070234705`)가 숫자로 해석되어 배치 전량이 버려졌다.

    앞자리 0이 있는 키를 주고받는 한 이 문제는 프롬프트로 못 막는다.
    그래서 통신에는 `r0` 같은 배치 지역 참조만 쓴다.
    """
    items = [{"external_id": "070234705", "name": "청도 감 말랭이 300G(팩)"}]
    payload = curate._payload(items, {})

    assert payload[0]["ref"] == "r0"
    assert "070234705" not in json.dumps(payload, ensure_ascii=False)


def test_앞자리_0이_있는_키도_되돌아온다():
    """모델이 ref만 제대로 돌려주면 원래 키는 우리가 갖고 있으므로 온전하다."""
    batch = [{"external_id": "070234705", "name": "청도 감 말랭이 300G(팩)"}]
    answer = json.dumps([{"ref": "r0", "name": "청도 감 말랭이 300G(팩)",
                          "category": "과일", "blurb": None}])

    result = curate._curate_batch(_responder(answer), batch, {})
    assert list(result) == ["070234705"]


# ── _curate_batch: 실패했을 때 조용하지 않은가 ────────────────────────

BATCH = [{"external_id": "a", "name": "제품A"}, {"external_id": "b", "name": "제품B"}]


def _responder(*responses):
    """호출될 때마다 미리 정한 응답을 차례로 돌려준다."""
    queue = list(responses)
    return lambda _: queue.pop(0) if queue else None


def test_빈_결과는_성공이_아니다(caplog):
    """2026-08-12 실측: 20건을 보냈는데 0건이 와도 성공으로 취급했다.

    경고 한 줄 없이 전량이 원본으로 발행됐다. 이게 가장 나쁘다 — 조용하다.
    """
    result = curate._curate_batch(_responder("[]", "[]"), BATCH, {})

    assert result == {}
    assert "0건" in caplog.text
    assert "실패" in caplog.text


def test_일부만_온_응답은_기록에_남는다(caplog):
    partial = json.dumps([{"ref": "r0", "name": "제품A", "category": "과자"}])
    result = curate._curate_batch(_responder(partial), BATCH, {})

    assert list(result) == ["a"]
    assert "빠졌다" in caplog.text          # b가 빠졌다는 사실이 남아야 한다
    assert "제품B" in caplog.text           # 무엇이 빠졌는지도 남아야 한다


def test_모양이_틀리면_재시도한다():
    good = json.dumps([{"ref": "r0", "name": "제품A"}])
    result = curate._curate_batch(_responder("이건 JSON이 아니다", good), BATCH, {})

    assert list(result) == ["a"]           # 1회차 실패, 2회차 성공


def test_계속_실패하면_빈_결과로_넘어간다(caplog):
    """호출자는 이 결과를 받아 원본 그대로 발행한다. 예외를 던지지 않는다."""
    result = curate._curate_batch(_responder("망가짐", "또 망가짐"), BATCH, {})

    assert result == {}
    assert "원본 그대로" in caplog.text


def test_가망_없는_실패는_재시도하지_않는다(caplog):
    calls = []

    def refuse(_):
        calls.append(1)
        raise curate._GiveUp("모델이 요청을 거부했다")

    assert curate._curate_batch(refuse, BATCH, {}) == {}
    assert len(calls) == 1                 # 재시도 없이 바로 포기
    assert "거부" in caplog.text


# ── _strip_fence: cli 응답의 마크다운 껍질 ────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ('```json\n{"items": []}\n```', '{"items": []}'),
    ('```\n{"items": []}\n```', '{"items": []}'),
    ('{"items": []}', '{"items": []}'),          # api 경로: 펜스가 없다
    ('  \n {"items": []} \n ', '{"items": []}'),
])
def test_코드펜스를_벗긴다(raw, expected):
    assert curate._strip_fence(raw) == expected


# ── 범위 밖 판정 (6장) ─────────────────────────────────────────────────────
#
# 앞의 셋(분류·요약·병합)과 달리 이것은 항목을 **없앤다.** 틀리면 사이트에서 제품 하나가
# 조용히 사라지고, 아무 예외도 나지 않는다. 그래서 기본값이 어느 쪽으로 넘어지는지가
# 이 기능의 전부다 — **모르면 포함한다.**

def _item(name="테스트과자", category_raw="과자류"):
    return {"external_id": "x1", "name": name, "category_raw": category_raw}


def test_판정이_없으면_범위_안이다():
    assert curate._apply(_item(), None, None)["out_of_scope"] is False


def test_LLM이_필드를_안_주면_범위_안이다():
    # 구형 응답이나 스키마를 안 지킨 응답. 빠뜨리는 쪽으로 넘어지면 안 된다.
    edit = {"name": "테스트과자", "category": "과자", "blurb": None}
    assert curate._apply(_item(), edit, None)["out_of_scope"] is False


def test_범위_밖으로_판정하면_표시가_실린다():
    edit = {"name": "테스트과자", "category": "기타", "blurb": None, "out_of_scope": True}
    assert curate._apply(_item(), edit, None)["out_of_scope"] is True


def test_이름이_바뀐_항목은_판정도_버린다():
    # name 검증에 걸리면 그 항목의 LLM 결과를 통째로 버린다(6장). 범위 밖 판정도
    # 같이 버려야 한다 — 이름을 못 믿는 응답의 판정만 믿을 이유가 없다.
    edit = {"name": "다른이름", "category": "기타", "blurb": None, "out_of_scope": True}
    assert curate._apply(_item(), edit, None)["out_of_scope"] is False


def test_판정한_이름이_로그에_남는다(caplog):
    edit = {"name": "테스트과자", "category": "기타", "blurb": None, "out_of_scope": True}
    with caplog.at_level("INFO"):
        curate._apply(_item(), edit, None)
    assert "테스트과자" in caplog.text
