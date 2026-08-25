"""컴포즈커피 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 compose 항목, 골든 픽스처
`tests/fixtures/compose_list_303364.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://composecoffee.com/index.php?mid=compose
      &act=dispCafemenuGalleryList&category_srl=<코드>&page=<N>
  Rhymix CMS의 서버 렌더링 HTML. 세션·토큰 불필요.
  robots.txt는 게시판 경로(`/board_*`, `/qnaw/`, `/AS/` 등)만 막는다.
  메뉴 경로와 이미지 경로(`/files/`)는 허용된다.

이 소스에서 조심할 것:

  1. **가격이 없다.** 목록에도 상세에도 없다. `price`는 항상 `null`이다.
     diff의 (이름, 가격) 계층이 (이름, None)이 되므로 `item_srl` 매칭이 필수다.
     같은 채널의 스타벅스가 이미 그래서 공유 코드는 이 모양을 견딘다.
  2. **설명문이 어디에도 없다.** 상세에는 영양 정보(컵용량·칼로리·나트륨…)와
     알레르기 정보뿐이다. 홈플러스와 같은 이유로 `detail`은 False이고
     `blurb`는 항상 `null`이 된다 — 스타벅스가 "목록이 이미 줘서" 건너뛰는 것과
     이유가 정반대다.
  3. **소스의 신상 라벨이 없다.** 항목 마크업에 배지가 없어 `_labels`를 채우지
     못한다. 그래서 이 소스는 diff 오탐을 채점할 대조군이 없다(홈플러스와 같다).
  4. 카테고리별 수집이 전체를 정확히 덮는다. 9개 카테고리 합 197건 =
     필터 없는 전체 197건, 카테고리 간 중복 0건. Rhymix가 항목당 카테고리를
     하나만 주기 때문이다. 따라서 중복 제거가 필요 없다.
  5. **끝을 넘긴 페이지는 0건을 준다.** 마지막 페이지로 되감지 않으므로
     "0건이면 멈춘다"가 안전한 종료 조건이다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/compose.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "compose"
BASE_URL = "https://composecoffee.com"
LIST_URL = (f"{BASE_URL}/index.php?mid=compose&act=dispCafemenuGalleryList"
            "&category_srl={category}&page={page}")
DETAIL_URL = (f"{BASE_URL}/index.php?mid=compose&act=dispCafemenuGalleryItem"
              "&item_srl={item_srl}")

# `category_srl`. 목록 페이지의 <select id="mobile_category_select">에서 실측했다.
CATEGORIES = {
    "301298": "추천메뉴",
    "303364": "커피ㆍ콜드브루",
    "303365": "베버리지",
    "303366": "프라페ㆍ스무디",
    "303367": "밀크쉐이크",
    "303368": "에이드ㆍ주스",
    "303369": "티",
    "308857": "푸드ㆍ디저트",
    "303371": "아이스크림",
}

# 2026-08-25 실측. 총 197건 / 15요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {
    "301298": 20, "303364": 60, "303365": 19, "303366": 11, "303367": 7,
    "303368": 11, "303369": 35, "308857": 22, "303371": 12,
}

PAGE_SIZE = 20          # 서버 고정. 페이지당 20개.
MAX_PAGES = 30          # 폭주 방지. 최대 카테고리(커피)가 3페이지였으므로 넉넉하다.

_ITEM_SRL_RE = re.compile(r"item_srl=(\d+)")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean_text(node) -> str | None:
    if node is None:
        return None
    text = html_mod.unescape(node.get_text(strip=True))
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("a.cafemenu-menu-item")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean_text(block.select_one(".cafemenu-menu-name"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        match = _ITEM_SRL_RE.search(block.get("href", ""))
        item_srl = match.group(1) if match else None

        image = block.select_one(".cafemenu-menu-image img")

        # item_srl이 주키다. 197건 실측에서 중복 0건이었다.
        items.append({
            "source_id": SOURCE_ID,
            "external_id": item_srl or _name_hash(name),
            "alt_ids": {"item_srl": item_srl} if item_srl else {},
            "name": name,
            "price": None,                   # 컴포즈는 가격을 주지 않는다 (주의 1번)
            "category_raw": CATEGORIES[category_code],
            "description": None,             # 상세에도 없다 (주의 2번). enrich도 건너뛴다
            "image_url": _absolute(image.get("src") if image else None),
            "source_url": DETAIL_URL.format(item_srl=item_srl) if item_srl else None,
            "scraped_at": scraped_at,
            # 주의 3번: 소스의 신상 라벨이 없다. `_labels`를 채우지 않는다.
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    """카테고리 하나를 페이지 끝까지. 0건이 오면 끝이다 (주의 5번)."""
    items: list[dict] = []
    seen: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL.format(category=category_code, page=page)
        markup = session.get(url).text
        base.save_raw(week, SOURCE_ID, f"{category_code}_{page}", markup, "html")

        page_items, skipped = parse_list(markup, category_code, scraped_at=scraped_at)
        if skipped:
            raise ParseError(
                f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
                "응답 구조가 바뀌었을 가능성이 높다."
            )
        if not page_items:
            break

        # 끝을 넘기면 0건이 오는 것이 실측이지만, 되감기로 동작이 바뀌면
        # 같은 항목을 무한히 쌓게 된다. 본 적 없는 것만 받는다.
        fresh = [i for i in page_items if i["external_id"] not in seen]
        if not fresh:
            log.warning("  %s(%s) %d페이지가 이전 페이지를 되풀이한다. 여기서 멈춘다.",
                        CATEGORIES[category_code], category_code, page)
            break
        seen.update(i["external_id"] for i in fresh)
        items.extend(fresh)

        if len(page_items) < PAGE_SIZE:
            break
    else:
        raise ParseError(
            f"{CATEGORIES[category_code]}: {MAX_PAGES}페이지를 넘겼다. "
            "페이지네이션이 끝나지 않는다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """컴포즈 전체 메뉴. 2026-08-25 실측 197건 / 15요청.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("컴포즈 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="컴포즈 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
