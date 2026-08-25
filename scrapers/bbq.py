"""BBQ 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 bbq 항목, 골든 픽스처
`tests/fixtures/bbq_menu_19.json`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://bbq.co.kr/api/delivery/menu/category   → 카테고리 목록
  GET https://bbq.co.kr/api/delivery/menu/<카테고리id> → 그 카테고리의 상품 전부
  Next.js SPA이지만 API가 같은 도메인에 인증 없이 노출된다. 페이지네이션 없음.
  robots.txt는 `Allow: /`.

★ **이 채널에서 유일하게 가격·설명문·영양·알레르기·원산지를 전부 준다.**

이 소스에서 조심할 것:

  1. ⚠️ **프로모션 카테고리 둘을 긁지 않는다**(`34 필릭스 PICK`, `17 추천`).
     둘은 카탈로그가 아니라 **큐레이션**이라 다른 카테고리와 겹친다.
     2026-08-25 실측: 8개 전부 긁으면 130건 중 고유 id가 105개뿐이라
     **25건이 중복**되고, `snapshot.py`의 유일성 검사가 발행을 멈춘다.
     여섯 개만 긁으면 105건 / 중복 0이고 카탈로그는 빠짐없이 덮인다.
  2. **응답이 봉투 없는 최상위 배열**이다. `{data: […]}`가 아니다.
  3. ⚠️ **상세가 클라이언트 렌더링이다.** `/products/<id>`가 200에 77KB를 주지만
     서버 응답에는 상품명이 없다. 2026-08-25에 브라우저로 열어 상품명·가격·설명이
     정상 표시되는 것을 확인하고 `source_url`로 채택했다(홈플러스와 같은 처리).
     **서버 응답으로는 이 URL을 검증할 수 없다** — `make check-images`가 이미지는
     보지만 상세 페이지는 보지 않는다.
  4. ⚠️ **이름에 `[NEW]` 접두사가 붙는다**(105건 중 8건). **떼지 않는다.**
     4장의 `name`은 소스 원문이고, 스크래퍼가 이름을 손대기 시작하면 소스마다
     규칙이 갈려 7장이 말하는 누수가 된다. 접두사가 떨어지는 주에는 diff가
     `changed`로 잡는데 그건 오탐이 아니라 실제로 이름이 바뀐 것이다.
     신상 여부는 `_labels`로 따로 보낸다.
  5. ⚠️ 이름에 ™·® 기호가 들어간다(`황금올리브치킨™`). **스크래퍼가 손대지 않는다** —
     `pipeline/normalize.py`의 `normalize_name`이 NFKC로 이미 접는다(™ → TM).
     동일성 판정은 모든 소스가 쓰는 자리라 거기 있어야 한다.
  6. **목록이 설명문을 준다**(105건 중 98건) → `detail: False`. 스타벅스와 같다.
  7. `menuPrice`는 정수이고 105/105 전부 있다. 이 채널에서 유일하다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/bbq.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "bbq"
BASE_URL = "https://bbq.co.kr"
CATEGORY_URL = f"{BASE_URL}/api/delivery/menu/category"
MENU_URL = f"{BASE_URL}/api/delivery/menu/{{category}}"
DETAIL_URL = f"{BASE_URL}/products/{{id}}"

# 카테고리 id → 응답의 `categoryName`. `/api/delivery/menu/category`에서 실측했다.
# **프로모션 둘(34 필릭스 PICK, 17 추천)은 일부러 뺐다** — 주의 1번.
CATEGORIES = {
    "18": "세트",
    "19": "치킨",
    "20": "피자&버거",
    "21": "사이드",
    "22": "소스&시즈닝&무",
    "23": "음료",
}

# 2026-08-25 실측. 총 105건 / 6요청(카테고리 목록 조회를 하지 않으므로).
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"18": 24, "19": 22, "20": 6, "21": 26, "22": 6, "23": 21}


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(value) -> str | None:
    if value is None:
        return None
    text = html_mod.unescape(str(value)).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_menu(payload, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """메뉴 배열 → (스냅샷 항목들, 이름이 없어 건너뛴 개수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")
    # 주의 2번: 봉투가 없다. dict가 오면 응답 구조가 바뀐 것이다.
    if not isinstance(payload, list):
        raise ParseError(
            f"카테고리 {category_code}: 응답이 배열이 아니다({type(payload).__name__}). "
            "API 응답 구조가 바뀌었을 가능성이 높다.")

    items: list[dict] = []
    skipped = 0

    for row in payload:
        name = _clean(row.get("menuName"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: id=%s", row.get("id"))
            continue

        menu_id = row.get("id")
        price = row.get("menuPrice")

        items.append({
            "source_id": SOURCE_ID,
            "external_id": str(menu_id) if menu_id else _name_hash(name),
            "alt_ids": {"id": str(menu_id)} if menu_id else {},
            # 주의 4번·5번: 이름을 손대지 않는다. `[NEW]`도 ™도 원문 그대로 간다.
            "name": name,
            "price": int(price) if isinstance(price, (int, float)) and price else None,
            "category_raw": CATEGORIES[category_code],
            # 주의 6번: 목록이 설명문을 준다. enrich는 이 소스를 건너뛴다.
            "description": _clean(row.get("description")),
            "tags": [],                       # 소스가 태그를 주지 않는다
            "image_url": _clean(row.get("menuImageUrl")),
            # 주의 3번: 브라우저에서만 렌더링된다. 2026-08-25에 눈으로 확인했다.
            "source_url": DETAIL_URL.format(id=menu_id) if menu_id else None,
            "scraped_at": scraped_at,
            # 대조군으로만 보낸다 — 판정에는 쓰지 않는다 (2.1).
            # `[NEW]`는 이름에 박혀 오므로 여기서 읽는다(주의 4번).
            "_labels": {
                "new": name.startswith("[NEW]"),
                "sold_out": bool(row.get("isSoldOut")),
            },
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    resp = session.get(MENU_URL.format(category=category_code))
    base.save_raw(week, SOURCE_ID, category_code, resp.text, "json")

    items, skipped = parse_menu(resp.json(), category_code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """BBQ 카탈로그. 2026-08-25 실측 105건 / 6요청.

    프로모션 카테고리 둘은 긁지 않는다(주의 1번). 한 카테고리라도 실패하면
    예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("BBQ 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BBQ 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 id. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
