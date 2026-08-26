"""버거킹 전체 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 burgerking 항목, 골든 픽스처 `tests/fixtures/burgerking_*.json`.
아래 수치는 전부 2026-08-26 실측이다.

  POST /burgerking/BKR0632.json   message=<봉투 JSON>   → 전체 메뉴 (요청 1건, 192건)
  POST /burgerking/BKR0634.json   message=<봉투 JSON>   → 상품 1건 상세

정찰이 **"요청 봉투 미확정"으로 멈춰 있던 소스다**(빈 body로 POST하면 HTTP 400).
봉투는 브라우저 캡처 없이 알아냈다 — 사이트가 스스로 싣고 다니는
`bizMOB/bizMOB-webExtend.js`의 `bizMOBWeb.Network.requestTr`가 `{header, body}`를
JSON 문자열로 만들어 **`message` 폼 필드 하나**에 넣어 POST한다. 그대로 따르면 200이 온다.

이 소스에서 조심할 것:

  1. **전체 카탈로그가 요청 1건이다.** 카테고리 순회도 페이지네이션도 없다.
     `BKR0632`의 body는 `{"menuKeywordList": []}` — 키워드 필터를 비우면 전부 온다.
  2. ⚠️ **`추천메뉴`(K200001)는 분류가 아니라 판촉 탭이다.** 26건 전부가 다른 분류에도
     있었다(2026-08-26 실측). 그래서 분류를 고를 때 **맨 뒤로 미루되 빼지는 않는다** —
     여기에만 있는 항목이 생기면 그건 잃으면 안 되는 항목이다. 그런 항목이 나오면
     `snapshot.py`의 건수 검증이 "기준에 없던 카테고리"로 알린다.
  3. ⚠️ **한 항목이 여러 분류에 실린다.** 239행 → 192건. 같은 분류 안에서 같은 코드가
     두 번 나오기도 한다(킹플로트 3종). 그래서 `menuCd`로 접는다.
  4. ⚠️ **같은 이름에 코드가 둘인 쌍이 16개 있다.** 정규 메뉴와 `올데이스낵&올데이킹`에
     같은 제품이 다른 코드로 실린다. 서로 다른 카탈로그 항목이므로 접지 않는다 —
     `menuCd`가 갈라준다(4장: 주키는 물리적 제품이 아니라 카탈로그 항목을 가리킨다).
  5. **목록에 가격이 없다.** 상세의 `dineInprc`에는 있지만 **사이트가 그 값을 화면에
     보여주지 않아** 우리도 싣지 않는다(2026-08-26, 사람이 결정). `price`는 항상 null이다.
  6. **설명문과 태그가 둘 다 상세에 있다** → `detail: True`. 던킨과 같은 배치다.
     목록의 `menuComponents`는 세트 구성이고 단품에서는 이름과 같아서 설명문이 아니다.
  7. **`menuFlagList`의 NEW는 판정에 쓰지 않는다**(2.1). 192건 중 46건이라 비율이 높다.
     대조군(`_labels`)으로만 둔다.
  8. **이름 끝에 공백이 붙어 오는 항목이 9건 있다.** 떼지 않으면 소스가 고치는 순간
     diff가 이름 변경으로 잡는다.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/burgerking.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "burgerking"
BASE_URL = "https://www.burgerking.co.kr"
TR_URL = BASE_URL + "/burgerking/{trcode}.json"
MENU_URL = BASE_URL + "/menu/detail/{menu_cd}"

LIST_TR = "BKR0632"
DETAIL_TR = "BKR0634"

# `cd_call_chnn`: 01=PC웹 02=앱 03=모바일웹. 앱 전용 메뉴가 갈릴 수 있으므로
# 우리가 보는 화면(PC웹)과 같은 값을 쓴다.
CALL_CHANNEL = "01"

# `menuCategoryCd` → `category_raw`에 넣을 표기. 소스가 이름을 함께 주지만
# 표를 둬야 `snapshot.py`의 건수 검증이 이름을 코드로 되돌릴 수 있다.
CATEGORIES = {
    "K200001": "추천메뉴",           # 주의 2번 — 판촉 탭이다
    "K200002": "오리지널스&맥시멈",
    "K200003": "프리미엄",
    "K200004": "와퍼&주니어",
    "K200005": "치킨&슈림프",
    "K200016": "올데이스낵&올데이킹",
    "K200006": "모닝",
    "K200010": "사이드",
    "K200020": "음료&디저트",
}

PROMO_CATEGORY = "K200001"

# 2026-08-26 실측. 239행 → 192건(주의 3번). **첫 수집 때만 쓰는 부트스트랩 기준이다.**
# 추천메뉴가 0인 것은 정상이다 — 그 26건이 전부 다른 분류에서 먼저 잡힌다(주의 2번).
BOOTSTRAP_COUNTS = {
    "K200001": 0,
    "K200002": 17,
    "K200003": 21,
    "K200004": 36,
    "K200005": 25,
    "K200016": 34,
    "K200006": 11,
    "K200010": 28,
    "K200020": 20,
}


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


# ── 요청 봉투 ────────────────────────────────────────────────────


def envelope(trcode: str, body: dict) -> dict:
    """bizMOB 전문 봉투. `bizMOB-webExtend.js`의 `requestTr`가 만드는 것과 같다.

    `cd_call_chnn`만 사이트(app.js)가 얹는 값이고 나머지는 프레임워크 기본값이다.
    """
    return {
        "header": {
            "result": True,
            "error_code": "",
            "error_text": "",
            "info_text": "",
            "message_version": "",
            "login_session_id": "",
            "trcode": trcode,
            "cd_call_chnn": CALL_CHANNEL,
        },
        "body": body,
    }


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_envelope(text: str, trcode: str) -> dict:
    """응답 본문 → 전문 body. 헤더가 실패라고 하면 예외를 던진다.

    ⚠️ **HTTP 200에 실패가 실려 온다.** `header.result`를 안 보면 빈 목록을
    정상으로 착각한다.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"{trcode}: JSON이 아니다: {text[:200]!r}") from exc

    header = payload.get("header") or {}
    if not header.get("result"):
        raise ParseError(f"{trcode}: 서버가 실패라고 답했다: "
                         f"{header.get('error_code')} {header.get('error_text')}")
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ParseError(f"{trcode}: body가 없다: {str(payload)[:200]}")
    return body


def _sorted_categories(categories: list[dict]) -> list[dict]:
    """분류 순서. 판촉 탭을 맨 뒤로 미룬다 (주의 2번).

    앞선 분류에서 먼저 잡힌 항목이 그 분류를 갖게 되므로, 순서가 곧
    `category_raw`를 정한다.
    """
    return sorted(categories, key=lambda c: (c.get("menuCategoryCd") == PROMO_CATEGORY,
                                             int(c.get("menuCategorySeq") or 0)))


def parse_list(text: str, *, scraped_at: str) -> list[dict]:
    """전체 메뉴 응답 → 스냅샷 항목들. 같은 `menuCd`는 처음 것만 남긴다 (주의 3번)."""
    body = parse_envelope(text, LIST_TR)
    categories = body.get("allMenuList")
    if not categories:
        raise ParseError("allMenuList가 비었다. 응답 구조가 바뀌었거나 미리보기 응답이다.")

    items: dict[str, dict] = {}
    for category in _sorted_categories(categories):
        code = category.get("menuCategoryCd")
        if code not in CATEGORIES:
            raise ParseError(
                f"모르는 분류다: {code!r} ({category.get('menuCategoryNm')!r}). "
                "CATEGORIES에 넣을지 사람이 정해야 한다."
            )
        for row in category.get("menuInfo") or []:
            name = (row.get("menuNm") or "").strip()   # 주의 8번
            if not name:
                raise ParseError(f"이름이 없는 항목이 있다: {str(row)[:200]}")
            menu_cd = str(row.get("menuCd") or "").strip()
            if not menu_cd:
                raise ParseError(f"menuCd가 없는 항목이 있다: {name}")
            if menu_cd in items:
                continue

            items[menu_cd] = {
                "source_id": SOURCE_ID,
                "external_id": menu_cd,
                # 목록이 주는 안정적인 키가 menuCd 하나뿐이다. 상세의 coverMenuCd는
                # 여러 항목이 공유하는 값이라 매칭 키로 쓸 수 없다.
                "alt_ids": {},
                "name": name,
                "price": None,                  # 주의 5번
                "category_raw": CATEGORIES[code],
                "description": None,            # 주의 6번 — 상세가 준다
                "tags": [],                     # 〃
                "image_url": row.get("menuImgPath") or None,
                "source_url": MENU_URL.format(menu_cd=menu_cd),
                "scraped_at": scraped_at,
                # 주의 7번: 대조군으로만 쓴다 (2.1).
                "_labels": {"new": any(f.get("menuFlagNm") == "NEW"
                                       for f in (row.get("menuFlagList") or []))},
            }

    return list(items.values())


def parse_detail(text: str) -> dict:
    """상세 응답 → {name, description, tags} (주의 6번).

    태그는 사이트가 상세 화면에 `#맥시멈 #몬스터맥시멈` 형태로 그리는 것과 같은 값이다.
    `menuFlagList`(NEW·BEST)는 판촉 배지라 태그가 아니다.
    """
    body = parse_envelope(text, DETAIL_TR)
    tags = [(k.get("menuKeywordNm") or "").strip()
            for k in (body.get("menuKeywordList") or [])]
    return {
        "name": (body.get("menuNm") or "").strip(),
        "description": (body.get("menuDesc") or "").strip() or None,
        "tags": [t for t in tags if t],
    }


# ── 수집 ─────────────────────────────────────────────────────────


def request_tr(session: base.Session, trcode: str, body: dict, *, week: str,
               request_id: str) -> str:
    """전문 1건. 원본을 남기고 본문을 그대로 돌려준다 (2.5)."""
    resp = session.post(
        TR_URL.format(trcode=trcode),
        data={"message": json.dumps(envelope(trcode, body), ensure_ascii=False)},
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Accept-Language": "ko-KR"},
    )
    resp.encoding = "utf-8"
    base.save_raw(week, SOURCE_ID, request_id, resp.text, "json")
    return resp.text


def fetch_detail(session: base.Session, external_id: str, *, week: str) -> dict:
    """상품 1건의 상세. diff가 걸러낸 신상에만 쓴다."""
    text = request_tr(session, DETAIL_TR, {"menuCd": external_id},
                      week=week, request_id=f"detail_{external_id}")
    return parse_detail(text)


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """버거킹 전체 메뉴. 2026-08-26 실측 192건 / 1요청.

    `categories`는 단독 실행에서 결과를 좁혀 보기 위한 것이다. 요청 수는 그대로 1건이다 —
    소스가 분류별 조회를 주지 않는다.
    """
    week = week or weeks.current_week()
    scraped_at = weeks.scraped_at()
    session = base.Session()

    text = request_tr(session, LIST_TR, {"menuKeywordList": []},
                      week=week, request_id=LIST_TR)
    items = parse_list(text, scraped_at=scraped_at)

    if categories:
        unknown = [c for c in categories if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"모르는 분류 코드: {unknown}")
        wanted = {CATEGORIES[c] for c in categories}
        items = [i for i in items if i["category_raw"] in wanted]

    log.info("버거킹 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="버거킹 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="분류 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
