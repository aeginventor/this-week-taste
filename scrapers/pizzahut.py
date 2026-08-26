"""피자헛 피자 카탈로그.

정찰 근거: `sources/targets.yml`의 pizzahut 항목, 골든 픽스처
`tests/fixtures/pizzahut_*.json`. 아래 수치는 전부 2026-08-26 실측이다.

  GET /api/menu/pizza/all/VISIT                 → 프리미엄 9 + US오리진 8 (매장 불필요)
  GET /api/menu/<매장>/list/cheesefesta/VISIT   → 3x 치즈페스타 8 (+ 파스타 1)

**정찰이 "매장 선택까지 진행해야 메뉴 XHR이 뜬다"고 적어두고 멈춰 있던 소스다.**
그 추정은 틀렸다. 요청 형식은 사이트가 스스로 싣고 다니는 번들에 그대로 있었다 —
`/static/web/asset-loader.js` → `asset-manifest.json` → `main.<해시>.js`의
`{apiUrl:"/api"}`. 버거킹과 같은 자리에서 같은 이유로 막혀 있었다.

이 소스에서 조심할 것:

  1. ⚠️ **`/menu/pizza/all`은 전체가 아니다.** 이름이 `all`인데 `premium`+`usoriginal`
     뿐이고 **판촉 탭 `cheesefesta`의 8건이 통째로 빠진다**(전체의 32%). 하필 그 탭에
     사이트가 NEW 배지를 달아 두었다 — 신상이 들어오는 자리가 정확히 거기다.
     던킨 `/menu/all`, 파리바게뜨 `?cat1=`과 같은 함정이다. 브라우저로 탭을 열어 보고
     알았다. 그래서 **`BOOTSTRAP_COUNTS`가 분류 셋을 전부 갖는다** — 한 탭이 통째로
     빠지면 건수 검증이 시끄럽게 실패한다(2.4).
  2. ⚠️ **`cheesefesta`는 매장 코드가 필수다.** 매장 없는 변형은 전부 HTTP 400이다.
     `STORE_CD`는 직영점 하나로 고정했다 — 두 매장(0767·0722)을 대조해 9건이
     바이트 단위로 같았다. 매장마다 메뉴가 갈리는 소스였다면 이 상수가 거짓말이 된다.
  3. **판촉 탭에 피자가 아닌 것이 섞인다**(파스타 1건). `lclass`/`mclass`로 거른다.
     반대로 `/menu/pizza/all`은 피자만 와야 하므로, 거기 섞이면 예외로 알린다.
  4. **카탈로그 단위는 대표 메뉴(`rpstMenuCd`)다.** `items`는 사이즈(L·M)일 뿐
     별개 상품이 아니다. 사이트도 대표 단위로 목록을 그린다.
  5. **가격은 사이즈별로 갈려서 최저가를 싣는다.** 25종 중 5종은 한 사이즈뿐이다.
     도미노가 같은 처리를 한다(M 최저가).
  6. **목록이 설명문을 전부 준다**(`rpstDesc` 25/25) → `detail: False`.
     상세(`/api/menu/<매장>/menu/<코드>`)를 실제로 불러 봤으나 **목록보다 주는 것이
     없었다.** 스타벅스와 같은 이유로 상세를 긁지 않는다.
  7. ⚠️ **CF 피자는 개별 상품 URL이 없다.** `main.js`의 `cpath`가 PM·MG·US·PN·OH만
     분기하고 CF는 `undefined`다. 브라우저로 카드를 눌러도 URL이 안 바뀐다.
     그래서 CF는 **목록 페이지 URL**을 쓴다(ADR-0013의 2층, 이마트24와 같은 자리).
  8. ⚠️ **이미지가 응답에 없다.** `image`·`thumb` 필드는 25건 전부 `null`이다.
     별도 CDN에 있고 규칙은 `index.html`의 `imageRoot`와 `main.js`에서 역산했다
     (`IMAGE_URL` 참조). 실제로 열리는 것을 확인했다.
  9. **`badge`의 NEW는 판정에 쓰지 않는다**(2.1). 25건 중 2건이다. 대조군(`_labels`)으로만 둔다.
 10. ⚠️ **`saleStartDate`를 판정에 쓰지 않는다.** 출시일이 응답에 그대로 오지만
     그것은 소스가 주장하는 신상 신호이고, 2.1은 신상을 차집합으로만 판별한다.
     정찰에서 출시 빈도를 재는 데만 썼다(연 3~5건).
 11. `VISIT`과 `DELIVERY`는 응답이 완전히 같다 — 항목 17/17 일치, 가격 차이 0건.
     주문 방식이 카탈로그를 가르지 않으므로 하나만 부른다.

`rpstMenuCd`는 **출시일 순으로 25/25 단조 증가한다**(RPPZ0007 → RPPZ2275, 6년치).
CU의 `gd_idx`는 등록 순서 *추정*이었지만 이것은 출시일과 대조해 확인한 값이라
`alt_ids`에 숫자부를 실어 `publish.py`의 오탐 지표에 쓴다.

`best` 탭도 있으나 요청하지 않는다 — 위 둘의 부분집합에 하프앤하프 세트 1건이
더 붙을 뿐이고, 그 세트는 `lclass`가 `S`라 어차피 걸러진다.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/pizzahut.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "pizzahut"
BASE_URL = "https://www.pizzahut.co.kr"

ALL_URL = BASE_URL + "/api/menu/pizza/all/{order_type}"
TAB_URL = BASE_URL + "/api/menu/{store_cd}/list/{tab}/{order_type}"

# 주의 11번 — 어느 쪽을 넣어도 응답이 같다. 매장을 안 고른 방문자가 보는 값을 쓴다.
ORDER_TYPE = "VISIT"

# 주의 2번. 불광역점(직영). 0722(남동탄점)와 대조해 결과가 같은 것을 확인했다.
STORE_CD = "0767"

# 주의 1번·3번. `mixed`는 피자가 아닌 행이 섞여 오는 탭인가다.
#
#   all          매장 불필요. 피자만 와야 한다 — 섞이면 목록의 성격이 바뀐 것이다
#   cheesefesta  매장 필수. 판촉 탭이라 파스타가 1건 섞여 온다
TABS = (
    {"name": "all", "store": False, "mixed": False},
    {"name": "cheesefesta", "store": True, "mixed": True},
)

# 주의 8번. `index.html`의 `imageRoot`와 `main.js`의 조립 규칙을 그대로 옮긴 것이다.
# 접미사 `_s`는 목록 카드가 쓰는 크기다(다른 접미사는 전부 404였다).
IMAGE_ROOT = "https://akamai.pizzahut.co.kr/2020pizzahut-prod/public"
IMAGE_URL = IMAGE_ROOT + "/img/menu/{digital_key}_s.png"

# 개별 상품 페이지. `main.js`의 `cpath`에서 역산했다.
DETAIL_PATH = {"PM": "premium", "US": "usoriginal"}
MENU_URL = BASE_URL + "/menu/pizza/{path}/{digital_key}"

# 주의 7번. `cpath`가 분기하지 않는 분류는 목록 페이지를 쓴다 (ADR-0013의 2층).
LIST_PAGE = {"CF": BASE_URL + "/menu/pizza/cheesefesta"}

# `sclass` → `category_raw`에 넣을 표기.
#
# PM은 사이트 자신의 `getCategoryName()`이 "프리미엄"으로 매핑한다. US와 CF는 그 표에
# 없어서(빈 문자열을 돌려준다) 화면의 탭 이름을 따라 적었다.
# 표를 둬야 `snapshot.py`의 건수 검증이 이름을 코드로 되돌릴 수 있다.
CATEGORIES = {
    "PM": "프리미엄",
    "US": "US오리진",
    "CF": "3x 치즈페스타",
}

# 응답 본문이 이 값을 가질 때만 피자다.
PIZZA_LCLASS = "P"
PIZZA_MCLASS = "PZ"

# 2026-08-26 실측. **첫 수집 때만 쓰는 부트스트랩 기준이다**(ADR-0002).
#
# ⚠️ CF가 여기 있는 것이 주의 1번의 안전장치다. 치즈페스타 요청이 실패하거나
# 캠페인이 끝나 탭이 사라지면 이 기준이 어긋나 발행이 멈춘다.
BOOTSTRAP_COUNTS = {
    "PM": 9,
    "US": 8,
    "CF": 8,
}


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def _lowest_price(row: dict) -> int | None:
    """사이즈 중 최저가 (주의 5번). 값이 하나도 없으면 `None`이다."""
    prices = [item.get("price") for item in (row.get("items") or [])]
    usable = [int(p) for p in prices if isinstance(p, (int, float)) and p > 0]
    return min(usable) if usable else None


def _sequence(rpst_menu_cd: str) -> int | None:
    """`RPPZ2275` → 2275. 단조 증가 지표용 (모듈 docstring 참조).

    접두사가 예상과 다르면 숫자를 지어내지 않고 `None`을 돌려준다 —
    틀린 지표는 없는 지표보다 나쁘다(7장).
    """
    digits = rpst_menu_cd[4:]
    if not rpst_menu_cd.startswith("RPPZ") or not digits.isdigit():
        return None
    return int(digits)


def _source_url(sclass: str, digital_key: str) -> str:
    """개별 상품 URL이 있으면 그것을, 없으면 목록 페이지를 쓴다 (주의 7번)."""
    if sclass in DETAIL_PATH:
        return MENU_URL.format(path=DETAIL_PATH[sclass], digital_key=digital_key)
    return LIST_PAGE[sclass]


def parse_list(text: str, *, scraped_at: str, mixed: bool = False) -> list[dict]:
    """피자 목록 응답 → 스냅샷 항목들. 대표 메뉴 하나가 항목 하나다 (주의 4번).

    `mixed`는 피자가 아닌 행이 섞여 오는 탭인가다(주의 3번). 판촉 탭이면 건너뛰고,
    피자만 와야 하는 탭이면 예외를 던진다.
    """
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON이 아니다: {text[:200]!r}") from exc

    # ⚠️ HTTP 200에 오류 본문이 실려 오는 경로가 있다(`/menu/pastaandside/all`이
    # `{"type":"MessageException", ...}`를 준다). 맨 배열이 아니면 목록이 아니다.
    if not isinstance(rows, list):
        raise ParseError(f"목록이 배열이 아니다: {str(rows)[:200]}")
    if not rows:
        raise ParseError("피자 목록이 비었다. 응답 구조가 바뀌었거나 미리보기 응답이다.")

    items: dict[str, dict] = {}
    for row in rows:
        lclass, mclass = row.get("lclass"), row.get("mclass")
        if (lclass, mclass) != (PIZZA_LCLASS, PIZZA_MCLASS):
            if mixed:
                continue                       # 판촉 탭에 섞인 사이드다 (주의 3번)
            raise ParseError(
                f"피자가 아닌 항목이 목록에 있다: lclass={lclass!r} mclass={mclass!r} "
                f"({row.get('rpstName')!r}). 목록의 성격이 바뀌었다."
            )

        sclass = row.get("sclass")
        if sclass not in CATEGORIES:
            raise ParseError(
                f"모르는 분류다: {sclass!r} ({row.get('rpstName')!r}). "
                "CATEGORIES에 넣을지 사람이 정해야 한다."
            )

        name = (row.get("rpstName") or "").strip()
        if not name:
            raise ParseError(f"이름이 없는 항목이 있다: {str(row)[:200]}")

        rpst_menu_cd = str(row.get("rpstMenuCd") or "").strip()
        if not rpst_menu_cd:
            raise ParseError(f"rpstMenuCd가 없는 항목이 있다: {name}")
        if rpst_menu_cd in items:
            raise ParseError(f"대표 코드가 중복이다: {rpst_menu_cd} ({name})")

        # `digitalKey`는 대표 메뉴에서 `rpstMenuCd`와 같은 값이지만, 이미지와 상품
        # URL을 만드는 쪽은 사이트 코드가 `digitalKey`를 쓰므로 그쪽을 따른다.
        digital_key = str(row.get("digitalKey") or rpst_menu_cd).strip()
        sequence = _sequence(rpst_menu_cd)

        items[rpst_menu_cd] = {
            "source_id": SOURCE_ID,
            "external_id": rpst_menu_cd,
            "alt_ids": {"rpst_seq": sequence} if sequence is not None else {},
            "name": name,
            "price": _lowest_price(row),               # 주의 5번
            "category_raw": CATEGORIES[sclass],
            "description": (row.get("rpstDesc") or "").strip() or None,  # 주의 6번
            "tags": [],                                # 소스가 주지 않는다
            "image_url": IMAGE_URL.format(digital_key=digital_key),      # 주의 8번
            "source_url": _source_url(sclass, digital_key),              # 주의 7번
            "scraped_at": scraped_at,
            # 주의 9번: 대조군으로만 쓴다 (2.1).
            "_labels": {"new": row.get("badge") == "NEW"},
        }

    return list(items.values())


# ── 수집 ─────────────────────────────────────────────────────────


def _tab_url(tab: dict) -> str:
    if tab["store"]:
        return TAB_URL.format(store_cd=STORE_CD, tab=tab["name"], order_type=ORDER_TYPE)
    return ALL_URL.format(order_type=ORDER_TYPE)


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """피자헛 전체 피자. 2026-08-26 실측 25건 / 2요청.

    `categories`는 단독 실행에서 결과를 좁혀 보기 위한 것이다. 요청 수는 그대로 2건이다 —
    분류와 탭이 1:1로 대응하지 않는다.
    """
    week = week or weeks.current_week()
    scraped_at = weeks.scraped_at()
    session = base.Session()

    # 앞선 탭에서 먼저 잡힌 항목이 그 분류를 갖는다. 지금은 탭끼리 겹치지 않지만,
    # 겹치기 시작하면 `all`이 이긴다 — 판촉 탭보다 정규 분류가 낫다(버거킹 주의 2번).
    items: dict[str, dict] = {}
    for tab in TABS:
        resp = session.get(_tab_url(tab), headers={"Accept": "application/json",
                                                   "Accept-Language": "ko-KR"})
        resp.encoding = "utf-8"
        base.save_raw(week, SOURCE_ID, f"{tab['name']}_{ORDER_TYPE}", resp.text, "json")  # 2.5
        found = parse_list(resp.text, scraped_at=scraped_at, mixed=tab["mixed"])
        log.info("  %s: %d건", tab["name"], len(found))
        for item in found:
            items.setdefault(item["external_id"], item)

    result = list(items.values())
    if categories:
        unknown = [c for c in categories if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"모르는 분류 코드: {unknown}")
        wanted = {CATEGORIES[c] for c in categories}
        result = [i for i in result if i["category_raw"] in wanted]

    log.info("피자헛 총 %d건 / %d요청", len(result), session.request_count)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="피자헛 피자 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="분류 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
