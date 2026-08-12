"""스타벅스 코리아 음료·푸드 카탈로그.

정찰 근거: `docs/RECON_franchise.md`, 골든 픽스처 `tests/fixtures/starbucks_cold_brew.json`.

  POST https://www.starbucks.co.kr/menu/productListAjax.do
       CATE_CD=<카테고리 코드>
  Referer가 필요하다. 세션·토큰은 불필요. 응답은 JSON.
  robots.txt는 302로 에러페이지를 준다(= 파일 없음) → 명시적 금지 규칙 없음.

이 소스에서 조심할 것 (전부 2026-08-12 실측으로 확인했다):

  1. **`CATE_CD=0`으로 한 번에 받지 않는다.** 정찰은 그렇게 1,179건을 받았는데,
     MD(텀블러·머그·에코백)가 절반 가까이 섞이고 `product_CD`가 202건 중복된다.
     같은 제품이 여러 카테고리에 노출되기 때문이다.
     **카테고리별로 18번 요청하면 326건에 중복 0건**이고 MD가 아예 안 섞인다.
     요청을 늘려서 문제를 없앤 것이지, 받아놓고 걸러낸 것이 아니다.
  2. **가격이 없다.** `price` 필드는 있지만 326건 전부 빈 문자열이다. 항상 `null`이다.
     오리온과 같은 이유로 diff의 (이름, 가격) 계층이 무력하다. `product_CD` 매칭이 필수다.
  3. **설명문이 목록에 이미 있다** (`content`, 326/326). 그래서 `description`을 채우고
     `enrich`는 이 소스의 상세를 긁지 않는다(4장). 상세 페이지를 326번 다시 칠 이유가 없다.
  4. **`cate_CD`가 응답에 전부 빈 값이다.** 카테고리는 우리가 요청에 쓴 코드에서
     역산해 `category_raw`에 넣는다(CLAUDE.md 4장이 허용하는 형태).
  5. `newicon`(Y/N)과 `new_SDATE`(예: `20260702`)는 **판정에 쓰지 않는다** (CLAUDE.md 2.1).
     `_labels`에 담아 대조군으로만 쓴다. `new_SDATE`는 라벨이 아니라 **날짜**라서
     다른 소스의 불리언 라벨보다 채점표로서 값이 크다.
  6. 빈 카테고리가 둘 있다(따뜻한 푸드, 푸드 기타). 오리온의 마켓오네이처와 같은 경우다.
  7. MD 섹션의 원두(`product_coffee`)와 시럽(`product_syrup`)은 **넣지 않았다.**
     먹는 것이긴 하지만 스타벅스가 굿즈로 분류한 것이고, 우리 판단으로 뒤집기
     시작하면 경계가 흐려진다. 필요해지면 FOOD_CATEGORIES에 추가하면 된다.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/starbucks.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "starbucks"
BASE_URL = "https://www.starbucks.co.kr"
LIST_URL = f"{BASE_URL}/menu/productListAjax.do"
LIST_REFERER = f"{BASE_URL}/menu/drink_list.do"
DRINK_DETAIL_URL = f"{BASE_URL}/menu/drink_view.do?product_cd={{product_cd}}"

# 카테고리 코드 → 표시 이름.
# 코드는 drink_list.do / food_list.do 의 인라인 JS에서 실측했다(주의 1번).
# MD(product_list.do)의 코드는 넣지 않는다 — 그것이 MD를 거르는 방법이다.
DRINK_CATEGORIES = {
    "W0000171": "콜드 브루",
    "W0000060": "브루드 커피",
    "W0000003": "에스프레소",
    "W0000004": "프라푸치노",
    "W0000005": "블렌디드",
    "W0000422": "리프레셔",
    "W0000061": "피지오",
    "W0000075": "티",
    "W0000053": "음료 기타",
    "W0000062": "주스",
}
FOOD_CATEGORIES = {
    "W0000013": "베이커리",
    "W0000032": "케이크",
    "W0000033": "샌드위치",
    "W0000054": "따뜻한 푸드",
    "W0000055": "과일·요거트",
    "W0000056": "스낵",
    "W0000064": "아이스크림",
    "W0000123": "푸드 기타",
}
CATEGORIES = {**DRINK_CATEGORIES, **FOOD_CATEGORIES}


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 사이트가 바뀌었다는 뜻이므로 조용히 넘기지 않는다."""


# ── 파싱 (네트워크 없이 단독으로 검증 가능하게 분리) ──────────────────


def _text(value) -> str | None:
    """빈 문자열을 None으로 접는다. 스타벅스는 미상을 `""`로 준다."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _image_url(row: dict) -> str | None:
    """`img_UPLOAD_PATH` + `file_PATH`. 둘 다 있어야 완성된다."""
    path = _text(row.get("file_PATH"))
    if not path:
        return None
    if path.startswith("http"):
        return path
    prefix = _text(row.get("img_UPLOAD_PATH")) or ""
    return f"{prefix}{path}" if prefix else None


def parse_list(payload, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 JSON → (스냅샷 항목들, 이름이 없어 건너뛴 항목 수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")

    rows = payload.get("list") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ParseError(f"목록이 리스트가 아니다: {type(rows).__name__}")

    items: list[dict] = []
    skipped = 0

    for row in rows:
        name = _text(row.get("product_NM"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(row)[:200])
            continue

        product_cd = _text(row.get("product_CD"))

        items.append({
            "source_id": SOURCE_ID,
            "external_id": product_cd or _name_hash(name),
            "alt_ids": {"product_cd": product_cd} if product_cd else {},
            "name": name,
            "price": None,                      # 326건 전부 빈 문자열이다 (주의 2번)
            "category_raw": CATEGORIES[category_code],
            "description": _text(row.get("content")),   # 목록이 준다 (주의 3번)
            "image_url": _image_url(row),
            "source_url": DRINK_DETAIL_URL.format(product_cd=product_cd) if product_cd else None,
            "scraped_at": scraped_at,
            # `_` 접두 키는 스냅샷에 저장되지 않는다. 판정에 쓰지 않고 대조군으로만 쓴다.
            "_labels": {
                "new": row.get("newicon") == "Y",
                # 라벨이 아니라 날짜다. 채점표로서 불리언보다 값이 크다 (주의 5번).
                "new_start_date": _text(row.get("new_SDATE")),
            },
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    resp = session.post(
        LIST_URL,
        data={"CATE_CD": category_code},
        headers={"Referer": LIST_REFERER, "X-Requested-With": "XMLHttpRequest"},
    )
    base.save_raw(week, SOURCE_ID, category_code, resp.text, "json")

    items, skipped = parse_list(resp.json(), category_code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """스타벅스 음료·푸드 카탈로그. 카테고리당 1요청, 총 18요청 / 약 326건.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("스타벅스 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="스타벅스 카탈로그 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    result = fetch(week=args.week, categories=args.category)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
