"""GS25 유어스(PB)·차별화 상품 카탈로그.

정찰 근거: `sources/targets.yml`의 gs25 항목, 골든 픽스처 `tests/fixtures/gs25_*.json`.
아래 수치는 전부 2026-08-25 실측이다.

  GET  /gscvs/ko/products/youus-freshfood            → JSESSIONID + CSRFToken
  POST /gscvs/ko/products/youus-freshfoodDetail-search?CSRFToken=<토큰>
       pageNum=<N>&pageSize=500&searchSrvFoodCK=<목록키>&searchSort=searchALLSort

첫 요청의 HTTP 403은 봇 차단이 아니라 **CSRF 보호**다. 페이지가 자기 토큰을 HTML에
실어 보내는 정상 흐름을 그대로 따르면 200이 된다.

★ **robots.txt가 시각을 제한하는 첫 소스다** — `Crawl-delay: 10`,
`Visit-time: 0400-0845`(UTC, KST 13:00~17:45). 둘 다 `base.Session`이 강제하므로
여기서는 아무것도 하지 않는다([ADR-0014](../docs/adr/0014-collection-time-window.md)).
창 밖에서 돌리면 `base.VisitTimeClosed`로 시끄럽게 멈춘다.

이 소스에서 조심할 것:

  1. ⚠️ **응답 본문이 JSON 문자열 안의 JSON이다.** `json.loads()`를 두 번 해야 한다.
     한 번만 하면 `str`이 나오고 `["SubPageListData"]`에서 TypeError가 난다.
  2. ⚠️ **`isNew`가 `"T"`/`"F"` 문자열이다.** truthy로 읽으면 전건이 신상이 된다.
     bhc의 `isNew: "Y"`와 같은 함정이다. 사이트 자신도 `data.isNew == "T"`로 비교한다.
     판정에는 쓰지 않고 대조군(`_labels`)으로만 둔다 (2.1).
  3. **전체 카탈로그가 아니다.** PB(유어스) + 차별화 상품만 목록이 있고 일반 매입
     상품은 사이트에 없다. 행사상품(1,723건)은 **긁지 않는다** — 카탈로그가 아니라
     프로모션이라 월 경계에서 통째로 바뀐다([ADR-0012](../docs/adr/0012-collection-scope.md)).
  4. **범위 밖 분류를 여기서 뺀다.** 차별화 상품에는 볼펜·우산·멀티탭(`DAILY_SUPPLIES`),
     손톱깎이(`BEAUTY`), 치실·밴드(`HEALTH`)가 섞여 있다. 795건 중 228건이다.
     CU에서 생활용품 카테고리를, 홈플러스에서 신선 원물을 뺀 것과 같은 판단이다.
  5. ⚠️ **`departCd`는 응답이 주는 영문 enum이고 화면에 이름이 노출되지 않는다.**
     `category_raw`에 넣을 한국어 표기는 우리가 붙였다(4장: 원문이 없으면 역산).
     **모르는 enum이 오면 예외를 던진다** — `snapshot.py`의 건수 검증이 `CATEGORIES`를
     이름→코드로 뒤집어 쓰므로, 모르는 분류는 조용히 건수에서 빠진다.
  6. **이름 끝의 `1편`/`2편`을 뗀다.** GS25 내부 편성 코드이고 **사이트 자신이 그렇게
     그린다**(목록 페이지 JS 실측). 붙여두면 편성이 바뀔 때마다 diff가 이름 변경으로 잡는다.
     떼고 나서도 567건에 이름 중복이 없다.
  7. **개별 상품 URL이 없다.** 목록 항목이 `<li>` 안의 `div.prod_box`뿐이고 링크가
     없다. `source_url`은 목록 페이지를 가리킨다([ADR-0013](../docs/adr/0013-source-url-optional.md)).
  8. **설명문이 목록에도 상세에도 없다** → `detail: False`. `blurb`는 항상 `null`이다(6장).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/gs25.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "gs25"
BASE_URL = "http://gs25.gsretail.com"
SEARCH_URL = f"{BASE_URL}/gscvs/ko/products/youus-freshfoodDetail-search"

# 목록키 → (사람이 읽는 이름, 그 목록의 페이지). 페이지는 CSRF 토큰의 출처이자
# 상품 URL이 없을 때 가리킬 곳이다(주의 7번).
LISTS = {
    "FreshFoodKey": ("유어스 Fresh Food", f"{BASE_URL}/gscvs/ko/products/youus-freshfood"),
    "DifferentServiceKey": ("차별화 상품", f"{BASE_URL}/gscvs/ko/products/youus-different-service"),
}

# `departCd.code` → `category_raw`에 넣을 표기 (주의 5번).
CATEGORIES = {
    "FRESH_FOOD": "프레시푸드",
    "CONVENIENCE_FOOD": "간편식품",
    "DRINK": "음료",
    "CRACKER": "과자",
    "DAIRY": "유제품",
    "GENERAL_FOOD": "일반식품",
    "CHILLED_FOOD": "냉장식품",
    "FROZEN": "냉동식품",
}

# 범위 밖 분류 (주의 4번). **모르는 값과 구별하려고 이름을 붙여 남긴다** —
# 여기 없는 enum이 오면 그건 소스가 바뀐 것이므로 예외다.
EXCLUDED_CATEGORIES = {
    "DAILY_SUPPLIES": "생활용품",
    "BEAUTY": "미용",
    "HEALTH": "위생·의약외품",
}

# 2026-08-25 실측. 범위를 좁힌 뒤 567건 / 4요청(목록 페이지 1 + 검색 3).
# 좁히기 전은 795건이었다. **첫 수집 때만 쓰는 부트스트랩 기준이다.**
BOOTSTRAP_COUNTS = {
    "FRESH_FOOD": 204,
    "CONVENIENCE_FOOD": 188,
    "DRINK": 65,
    "CRACKER": 49,
    "DAIRY": 24,
    "GENERAL_FOOD": 22,
    "CHILLED_FOOD": 8,
    "FROZEN": 7,
}

PAGE_SIZE = 500     # 서버가 존중한다(실측). 591건이 2요청이면 끝난다.
MAX_PAGES = 10      # 폭주 방지. 최대가 2페이지였으므로 넉넉하다.

_CSRF_RE = re.compile(r'name="CSRFToken"\s+value="([^"]+)"')
_EPISODE_RE = re.compile(r"[12]편$")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def clean_name(raw: str) -> str:
    """`'혜자)반반제육도시락1편'` → `'혜자)반반제육도시락'` (주의 6번)."""
    return _EPISODE_RE.sub("", raw.strip()).strip()


def parse_price(value) -> int | None:
    """`5500.0` → `5500`. 0이나 없는 값은 `null`로 둔다(4장)."""
    if not value:
        return None
    return int(float(value))


def parse_image(value) -> str | None:
    """이미지가 없으면 파일명에 문자열 `null`이 들어온다. 사이트 JS도 그걸 검사한다."""
    if not value or "null" in str(value):
        return None
    return str(value)


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_payload(body: str) -> tuple[list[dict], int]:
    """응답 본문 → (원본 항목들, 소스가 밝힌 총건수). 주의 1번.

    총건수를 함께 돌려주는 이유: 받은 건수와 대조해야 페이지를 놓친 것을 알 수 있다.
    """
    try:
        payload = json.loads(body)
        if isinstance(payload, str):       # 문자열 안의 JSON (주의 1번)
            payload = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON이 아니다: {body[:200]!r}") from exc

    if not isinstance(payload, dict) or "SubPageListData" not in payload:
        raise ParseError(f"SubPageListData가 없다: {str(payload)[:200]}")

    total = (payload.get("SubPageListPagination") or {}).get("totalNumberOfResults")
    if total is None:
        raise ParseError("총건수(totalNumberOfResults)가 없다. 응답 구조가 바뀌었다.")
    return payload["SubPageListData"], int(total)


def parse_list(body: str, list_key: str, *, scraped_at: str) -> tuple[list[dict], int, Counter]:
    """목록 응답 → (범위 안 항목들, 소스가 밝힌 총건수, 범위 밖 분류별 건수)."""
    if list_key not in LISTS:
        raise ValueError(f"모르는 목록키: {list_key!r}")

    rows, total = parse_payload(body)
    _, list_url = LISTS[list_key]
    items: list[dict] = []
    dropped: Counter = Counter()

    for row in rows:
        name = (row.get("goodsNm") or "").strip()
        if not name:
            raise ParseError(f"이름이 없는 항목이 있다: {str(row)[:200]}")

        depart = (row.get("departCd") or {}).get("code")
        if depart in EXCLUDED_CATEGORIES:   # 주의 4번
            dropped[depart] += 1
            continue
        if depart not in CATEGORIES:        # 주의 5번
            raise ParseError(
                f"모르는 분류다: {depart!r} ({name}). CATEGORIES에 넣을지 "
                "EXCLUDED_CATEGORIES에 넣을지 사람이 정해야 한다."
            )

        code = str(row.get("code") or "").strip()
        att_file_id = (row.get("attFileId") or "").strip()
        clean = clean_name(name)

        items.append({
            "source_id": SOURCE_ID,
            "external_id": code or _name_hash(clean),
            # 상품 코드가 바뀌어도 같은 제품을 알아보게 하는 보조 키(4장).
            # 증가하는 값으로 보이지만 등록 순서인지는 확인하지 않았다 → monotonic_key는 None.
            "alt_ids": {"att_file_id": att_file_id} if att_file_id else {},
            "name": clean,
            "price": parse_price(row.get("price")),
            "category_raw": CATEGORIES[depart],
            "description": None,            # 주의 8번
            "tags": [],
            "image_url": parse_image(row.get("attFileNm")),
            "source_url": list_url,         # 주의 7번 (ADR-0013)
            "scraped_at": scraped_at,
            # 주의 2번: 대조군으로만 쓴다 (2.1).
            "_labels": {"new": row.get("isNew") == "T"},
        })

    return items, total, dropped


def dedupe(items: list[dict]) -> list[dict]:
    """상품 코드가 같은 항목을 하나로 접는다.

    2026-08-25 실측으로는 두 목록이 하나도 겹치지 않았다(795건 전부 고유). 그래도
    접는 이유는 이마트24가 같은 자리에서 157건 겹쳤기 때문이다 — 목록의 성격은 바뀐다.

    ⚠️ **가격이 다르면 예외를 던진다.** 서로 다른 상품이 같은 코드를 쓰고 있을 수 있고
    ([ADR-0001](../docs/adr/0001-product-id.md)), 조용히 접으면 한 상품이 사라진다.
    """
    kept: dict[str, dict] = {}
    order: list[str] = []

    for item in items:
        key = item["external_id"]
        if key not in kept:
            kept[key] = item
            order.append(key)
            continue
        first = kept[key]
        if first["price"] != item["price"]:
            raise ParseError(
                f"같은 코드({key})에 가격이 다르다: "
                f"{first['name']!r} {first['price']} vs {item['name']!r} {item['price']}."
            )
        log.info("  두 목록에 같은 상품이 있다 — 앞의 것을 쓴다: %s (%s)", first["name"], key)

    if len(order) != len(items):
        log.info("  중복 제거: %d건 → %d건", len(items), len(order))
    return [kept[k] for k in order]


# ── 수집 ─────────────────────────────────────────────────────────


def csrf_token(session: base.Session, list_url: str) -> str:
    """목록 페이지에서 CSRF 토큰을 얻는다. 세션 쿠키도 여기서 붙는다."""
    markup = session.get(list_url).text
    match = _CSRF_RE.search(markup)
    if not match:
        raise ParseError(f"CSRF 토큰을 찾지 못했다: {list_url}")
    return match.group(1)


def fetch_list(session: base.Session, list_key: str, token: str, *, week: str,
               scraped_at: str) -> list[dict]:
    """목록 하나를 끝까지. 소스가 밝힌 총건수와 대조한다."""
    label, _ = LISTS[list_key]
    items: list[dict] = []
    received = 0
    dropped: Counter = Counter()
    total: int | None = None

    for page in range(1, MAX_PAGES + 1):
        body = session.post(f"{SEARCH_URL}?CSRFToken={token}", data={
            "pageNum": page,
            "pageSize": PAGE_SIZE,
            "searchWord": "",
            "searchHPrice": "",
            "searchTPrice": "",
            "searchSrvFoodCK": list_key,
            "searchSort": "searchALLSort",
            "searchProduct": "productALL",
        }).text
        base.save_raw(week, SOURCE_ID, f"{list_key}_{page}", body, "json")

        page_items, total, page_dropped = parse_list(body, list_key, scraped_at=scraped_at)
        received += len(page_items) + sum(page_dropped.values())
        items.extend(page_items)
        dropped.update(page_dropped)
        if received >= total:
            break
    else:
        raise ParseError(f"{label}: {MAX_PAGES}페이지를 넘겼다. 페이지네이션이 끝나지 않는다.")

    # 소스가 스스로 밝힌 건수와 대조한다. 미리보기 응답을 전체로 착각하는 것을 막는다.
    if received != total:
        raise ParseError(
            f"{label}: {received}건을 받았는데 소스는 {total}건이라고 한다. "
            "페이지를 놓쳤을 가능성이 높다."
        )

    if dropped:
        log.info("  %s: 범위 밖 %d건 제외 (%s)", label, sum(dropped.values()),
                 ", ".join(f"{EXCLUDED_CATEGORIES[k]} {v}" for k, v in dropped.most_common()))
    log.info("  %s: %d건", label, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """GS25 카탈로그. 2026-08-25 실측 567건 / 4요청 (범위를 좁힌 뒤).

    한 목록이라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    keys = categories or list(LISTS)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    # 토큰은 세션마다 다르다. 매 실행 시 페이지를 먼저 GET한다.
    token = csrf_token(session, LISTS[keys[0]][1])

    raw: list[dict] = []
    for key in keys:
        raw.extend(fetch_list(session, key, token, week=week, scraped_at=scraped_at))

    items = dedupe(raw)
    log.info("GS25 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GS25 상품 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(LISTS),
                        help="목록키. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
