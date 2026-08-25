"""교촌치킨 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 kyochon 항목, 골든 픽스처
`tests/fixtures/kyochon_list_chicken.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.kyochon.com/menu/<탭>.asp
  순수 서버 렌더링 ASP. 파라미터 없이 부르면 그 탭 전체가 한 HTML에 온다.
  세션·토큰 불필요. 페이지네이션 없음.
  robots.txt에 `User-agent: *` 그룹이 아예 없다(Yeti만 명시) → 우리에게 적용될 규칙이 없다.

★ **우리가 붙인 소스 중 가장 싸다. 4요청에 101건 + 설명문 + 가격.**

이 소스에서 조심할 것:

  1. ⚠️ **정찰 기록의 탭 목록이 틀렸다.** 기록은 `/menu/burger.asp`를 들었으나
     그런 경로는 없다. 실측한 탭은 chicken · side · liquor · drink 넷이다.
  2. **목록이 설명문을 준다**(101/101) → `detail: False`. 스타벅스와 같은 이유로
     상세를 긁지 않는다 — 이미 가진 것을 버리고 다시 긁는 것은 예의가 아니다.
  3. **가격이 일부만 있다**(92/101). 없으면 `null`이다 — 4장이 nullable로 둔 자리다.
     `?code=1..21`로 시리즈 필터를 걸 수 있으나 전체를 한 번에 받는 쪽이 싸다.
  4. `dd`의 설명문에 `<br>`로 줄바꿈이 들어 있고 `※` 주석이 붙는 경우가 있다.
     줄바꿈은 공백으로 접는다. 주석은 소스 원문이므로 지우지 않는다(6장).
  5. **주류 탭이 둘 있다**(문베어 수제맥주 6건, 은하수 막걸리 3건). 범위 안이다 —
     CLAUDE.md 1장의 범위는 포장 식음료와 프랜차이즈 매장 신메뉴이고,
     주류는 편의점 분류 목록에도 이미 있다.
  6. **소스의 신상 라벨이 없다.** 항목 마크업에 배지가 없어 `_labels`를 채우지
     못한다 — 이 소스는 diff 오탐을 채점할 대조군이 없다(홈플러스·컴포즈와 같다).
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/kyochon.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "kyochon"
BASE_URL = "https://www.kyochon.com"
LIST_URL = f"{BASE_URL}/menu/{{tab}}.asp"

# 탭 코드 → 사람이 읽는 이름. 목록 페이지 상단 네비게이션에서 실측했다(주의 1번).
# `snapshot.py`의 건수 검증이 이 표를 역인덱스로 쓴다.
CATEGORIES = {
    "chicken": "치킨",
    "side": "사이드",
    "liquor": "문베어 수제맥주",
    "drink": "은하수 막걸리",
}

# 2026-08-25 실측. 총 101건 / 4요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"chicken": 69, "side": 23, "liquor": 6, "drink": 3}

_ID_RE = re.compile(r"id=(\d+)")
_PRICE_RE = re.compile(r"\d[\d,]*")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean_text(node) -> str | None:
    if node is None:
        return None
    # 주의 4번: `<br>`이 줄바꿈이므로 공백으로 접는다. get_text의 구분자가 그 일을 한다.
    text = html_mod.unescape(node.get_text(" ", strip=True))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


def parse_price(text: str | None) -> int | None:
    """`'23,000'` → `23000`. 숫자가 없으면 None (주의 3번)."""
    if not text:
        return None
    match = _PRICE_RE.search(text)
    return int(match.group().replace(",", "")) if match else None


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, tab: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if tab not in CATEGORIES:
        raise ValueError(f"모르는 탭: {tab!r}")

    soup = BeautifulSoup(markup, "html.parser")
    # 상품 블록의 표시는 `dl.txt > dt`다. 네비게이션의 li와 이것으로 갈린다.
    blocks = [li for li in soup.select("li") if li.select_one("dl.txt dt")]
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean_text(block.select_one("dl.txt dt"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        link = block.select_one("a[href*='view.asp']")
        match = _ID_RE.search(link.get("href", "") if link else "")
        item_id = match.group(1) if match else None

        image = block.select_one("p.img img")

        items.append({
            "source_id": SOURCE_ID,
            "external_id": item_id or _name_hash(name),
            "alt_ids": {"id": item_id} if item_id else {},
            "name": name,
            "price": parse_price(_clean_text(block.select_one("p.money strong"))),
            "category_raw": CATEGORIES[tab],
            # 주의 2번: 목록이 설명문을 준다. enrich는 이 소스를 건너뛴다.
            "description": _clean_text(block.select_one("dl.txt dd")),
            "tags": [],                       # 소스가 태그를 주지 않는다
            "image_url": _absolute(image.get("src") if image else None),
            "source_url": (f"{BASE_URL}/menu/view.asp?id={item_id}" if item_id else None),
            "scraped_at": scraped_at,
            # 주의 6번: 소스의 신상 라벨이 없다. `_labels`를 채우지 않는다.
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_tab(session: base.Session, tab: str, *, week: str,
              scraped_at: str) -> list[dict]:
    resp = session.get(LIST_URL.format(tab=tab))
    markup = resp.text
    base.save_raw(week, SOURCE_ID, tab, markup, "html")

    items, skipped = parse_list(markup, tab, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[tab]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[tab], tab, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """교촌 전체 카탈로그. 2026-08-25 실측 101건 / 4요청.

    한 탭이라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    tabs = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for tab in tabs:
        items.extend(fetch_tab(session, tab, week=week, scraped_at=scraped_at))

    log.info("교촌 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="교촌 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="탭 이름. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
