"""bhc치킨 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 bhc 항목, 골든 픽스처
`tests/fixtures/bhc_products_1.json`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.bhc.co.kr/api/v1/web/categories/<카테고리id>/products
  같은 도메인에 인증 없이 열린 API. 페이지네이션 없음.
  응답 봉투는 `{status, message, code, body:[...]}`.

⚠️⚠️ **robots.txt가 `ClaudeBot`·`GPTBot`·`CCBot`·`Google-Extended`를 금지한다.**
우리 UA는 `ThisWeekTaste/1.0`이라 `User-agent: *` 그룹(허용)에 해당한다.
**UA에 `Claude` 문자열을 넣는 순간 금지 대상이 된다** — `scrapers/base.py`가
세션 생성 시 이를 거부하므로 코드로 강제되어 있다.
⚠️ `Content-Signal: ai-train=no, use=reference`도 명시되어 있다. 우리 용도
(요약 + 원문 링크)는 `use=reference`와 일치하나, **수집 데이터를 학습에 쓰면
이 소스는 재검토 대상이다.**

이 소스에서 조심할 것:

  1. ⚠️⚠️ **`isNew`가 `"Y"`/`"N"` **문자열**이다.** 파이썬에서 `"N"`은 참이므로
     `if row["isNew"]`로 짜면 **전건이 신상**이 된다. 2026-08-25 실측 158건 중
     실제 `"Y"`는 25건이다. 이마트24의 `opacity: 0` NEW와 같은 종류의 함정이다.
     `isBest`·`isLimited`도 같은 모양이다.
  2. ⚠️ **`productNm`에 줄바꿈과 후행 공백이 들어 있다** —
     `"뿌링클(반)+맛초킹라이스\\n+콜라500ml\\n"`. 공백을 접어 정규화한다.
  3. ⚠️ **카테고리 간 중복이 크다.** 2026-08-25 실측: 158건 중 고유 `productCd`는
     113개다(45건 중복). `productCd`로 접고 앞에 오는 카테고리가 분류를 가져간다.
  4. ⚠️ **`cateNm`은 카테고리 이름이 아니다.** 상품별 시리즈 태그의 **배열**이다
     (`["뿌링클"]`, `["킹"]`, `["후라이드"]`). 카테고리 id의 이름은 응답에 없어서
     `/menu/<id>` 페이지의 탭에서 읽었다.
  5. **가격이 없다.** `options`가 전부 빈 배열이다. `price`는 항상 `null`이다.
  6. **목록이 설명문을 준다**(`description`) → `detail: False`.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/bhc.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "bhc"
BASE_URL = "https://www.bhc.co.kr"
LIST_URL = f"{BASE_URL}/api/v1/web/categories/{{category}}/products"
DETAIL_URL = f"{BASE_URL}/menu/{{category}}"

# 카테고리 id → 이름. **응답이 주지 않아 `/menu/<id>` 탭에서 읽었다**(주의 4번).
# 순서가 의미를 갖는다 — 앞에 오는 카테고리가 중복 항목의 분류를 가져간다(주의 3번).
CATEGORIES = {
    "1": "CHICKEN",
    "23": "SIGNATURE",
    "47": "COLPOP",
    "50": "SIDE",
    "74": "뿌링클 유니버스",
}

# 2026-08-25 실측. 중복 제거 후 113건 / 5요청.
# ⚠️ 목록상으로는 33·27·11·59·28건이지만 45건이 앞 카테고리와 겹친다(주의 3번).
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"1": 33, "23": 12, "47": 0, "50": 59, "74": 9}
# ⚠️ `47`(COLPOP)이 **0인 것은 오류가 아니다.** 11건 전부가 앞 카테고리에
#    이미 실려 있다(2026-08-25 실측). 요청은 계속 보낸다 — 이 카테고리에만
#    실리는 상품이 생기면 그때 잡아야 하기 때문이다.
#    `snapshot.py`의 건수 검증은 기준이 0인 항목을 건너뛴다.


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(value) -> str | None:
    """줄바꿈과 연속 공백을 한 칸으로 접는다 (주의 2번)."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", html_mod.unescape(str(value))).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def is_yes(value) -> bool:
    """`"Y"` → True, `"N"`/`None`/`""` → False (주의 1번).

    이 함수가 없으면 `"N"`이 참으로 읽혀 전건이 신상이 된다.
    """
    return str(value or "").strip().upper() == "Y"


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_products(payload, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """상품 목록 JSON → (스냅샷 항목들, 이름이 없어 건너뛴 개수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")
    if not isinstance(payload, dict) or "body" not in payload:
        raise ParseError(
            f"카테고리 {category_code}: 응답에 body가 없다. 봉투 구조가 바뀌었을 "
            f"가능성이 높다: {sorted(payload) if isinstance(payload, dict) else type(payload)}")

    rows = payload.get("body") or []
    items: list[dict] = []
    skipped = 0

    for row in rows:
        name = _clean(row.get("productNm"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: productCd=%s", row.get("productCd"))
            continue

        code = _clean(row.get("productCd"))

        items.append({
            "source_id": SOURCE_ID,
            "external_id": code or _name_hash(name),
            "alt_ids": {"product_cd": code} if code else {},
            "name": name,
            "price": None,                    # 주의 5번: options가 전부 비어 있다
            "category_raw": CATEGORIES[category_code],
            # 주의 6번: 목록이 설명문을 준다. enrich는 이 소스를 건너뛴다.
            "description": _clean(row.get("description")),
            # 주의 4번: `cateNm`은 카테고리가 아니라 시리즈 태그의 배열이다.
            # 소스가 준 분류어이므로 4장의 `tags`에 그대로 싣는다.
            "tags": [t for t in (_clean(x) for x in (row.get("cateNm") or [])) if t],
            "image_url": _clean(row.get("mainImg")),
            # 개별 상품 URL이 없다 → 카테고리 목록 페이지 (ADR-0013 2층).
            "source_url": DETAIL_URL.format(category=category_code),
            "scraped_at": scraped_at,
            # 주의 1번: 문자열 "Y"/"N"이다. 대조군으로만 쓴다 (2.1).
            "_labels": {
                "new": is_yes(row.get("isNew")),
                "best": is_yes(row.get("isBest")),
                "limited": is_yes(row.get("isLimited")),
            },
        })

    return items, skipped


def dedupe(items: list[dict]) -> list[dict]:
    """같은 `productCd`를 하나로 접는다 (주의 3번).

    앞의 것을 남긴다 — `CATEGORIES` 순서가 분류 우선순위다.
    ⚠️ **이름이 다르면 예외를 던진다.** 키가 상품을 가리키지 않는다는 뜻이다.
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
        if first["name"] != item["name"]:
            raise ParseError(
                f"같은 productCd({key})에 이름이 다르다: "
                f"{first['name']!r} vs {item['name']!r}.")
    log.info("  중복 제거: %d건 → %d건", len(items), len(order))
    return [kept[k] for k in order]


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    resp = session.get(LIST_URL.format(category=category_code))
    base.save_raw(week, SOURCE_ID, category_code, resp.text, "json")

    items, skipped = parse_products(resp.json(), category_code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """bhc 전체 카탈로그. 2026-08-25 실측 113건 / 5요청 (중복 제거 후).

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    raw: list[dict] = []
    for code in codes:
        raw.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    items = dedupe(raw)
    log.info("bhc 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="bhc 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 id. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
