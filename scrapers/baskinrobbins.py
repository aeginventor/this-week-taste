"""배스킨라빈스 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 baskinrobbins 항목, 골든 픽스처
`tests/fixtures/baskinrobbins_list_A.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.baskinrobbins.co.kr/menu/list.php?category=<코드>            (A F B E)
  GET https://www.baskinrobbins.co.kr/menu/list_subcategory.php?category=<코드> (C D)
  순수 서버 렌더링. 세션·토큰 불필요. 페이지네이션 없음 — 한 요청에 전부 온다.
  robots.txt는 **HTTP 404**라 금지 규칙이 없다(CU와 같은 경우).

이 소스에서 조심할 것:

  1. ⚠️ **seq가 두 네임스페이스로 갈린다.** A·F·B·E는 `view.php?seq=`를,
     C·D는 `view_subcategory.php?seq=`를 쓰는데 **둘 다 1부터 시작한다.**
     2026-08-25 실측: 128건 중 고유 seq는 120건 — **8건이 충돌한다**
     (seq 1·3·7·8·17·19·24·79). 그래서 `external_id`에 네임스페이스 접두사를
     붙인다(`p1124` / `s79`). 소스 원본 값은 `alt_ids.seq`에 그대로 남긴다.
     CLAUDE.md 4장이 "추측하지 말고 실측할 것"이라고 경고한 자리가 이것이다.
  2. **가격이 없다.** 목록에도 상세에도 없다. `price`는 항상 `null`이다.
     같은 채널의 스타벅스·컴포즈가 이미 그래서 공유 코드는 이 모양을 견딘다.
  3. ★ **소스가 태그를 준다.** `span.menu-list__hash`가 `#크림치즈 #조청카라멜`
     형태로 목록에 실려 온다. 우리가 붙인 소스 중 **처음 있는 일**이라
     2026-08-25에 스냅샷 스키마에 `tags`를 넣었다(4장). LLM이 이름만 보고
     지어내는 것보다 소스 원문이 언제나 낫다(6장).
  4. **설명문은 상세에만 있다** → `detail: True`. 태그는 목록이, 설명문은 상세가
     준다 — 둘의 출처가 갈리는 첫 소스다. `enrich.py`가 상세 결과로 태그를
     덮어쓰지 않고 보존한다(4장의 `tags` 계약).
  5. ⚠️ 제품명에 HTML 엔티티가 그대로 온다(`&#40;Lessly Edition&#41;`).
     `html.unescape()`가 필수다.
  6. **`/menu/fom.php`(이달의 맛)는 긁지 않는다.** 정찰 기록은 이것을 카탈로그의
     일곱 번째 요청으로 적었으나, 실측하니 **캠페인 소개 페이지**였다 —
     `menu-fom__*` 구조에 상품 링크가 하나도 없고, 소개된 맛은 아이스크림(A)
     목록에 이미 들어 있다. 긁으면 중복 항목이 생기고 `external_id`도 못 만든다.
     이달의 맛 교체는 A 카테고리의 차집합이 잡아낸다.
  7. **소스의 신상 라벨이 있다**(`li.menu-list__item--new`). `_labels`에 담아
     대조군으로만 보낸다 — 판정에는 쓰지 않는다(2.1). ⚠️ 스타벅스의 NEW가
     28건 중 26건이 지난 스냅샷에도 있어 무효였으므로, **이 라벨도 W36에
     "지난주에도 붙어 있었나"를 확인하기 전에는 채점표로 쓰지 않는다.**
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/baskinrobbins.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "baskinrobbins"
BASE_URL = "https://www.baskinrobbins.co.kr"

# 카테고리 코드 → 사람이 읽는 이름. `snapshot.py`의 건수 검증이 이 표를 역인덱스로
# 쓰므로(`_category_counts`) 형태는 {코드: 이름}이어야 한다.
# 목록 페이지 상단 네비게이션에서 실측했다.
CATEGORIES = {
    "A": "아이스크림",
    "F": "프리팩",
    "B": "아이스크림 케이크",
    "E": "디저트",
    "C": "음료",
    "D": "커피",
}

# 카테고리마다 목록 경로와 상세 경로가 갈린다 (주의 1번).
# 이 표가 `external_id` 접두사의 근거이기도 하다.
_ROUTES = {
    "A": ("list.php", "view.php", "p"),
    "F": ("list.php", "view.php", "p"),
    "B": ("list.php", "view.php", "p"),
    "E": ("list.php", "view.php", "p"),
    "C": ("list_subcategory.php", "view_subcategory.php", "s"),
    "D": ("list_subcategory.php", "view_subcategory.php", "s"),
}

# 2026-08-25 실측. 총 128건 / 6요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {
    "A": 29, "F": 23, "B": 24, "E": 23, "C": 17, "D": 12,
}

_SEQ_RE = re.compile(r"seq=(\d+)")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean_text(node) -> str | None:
    if node is None:
        return None
    text = html_mod.unescape(node.get_text(" ", strip=True))
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


def parse_tags(text: str | None) -> list[str]:
    """`#크림치즈 #조청카라멜 #현미그라함쿠키` → ['크림치즈', '조청카라멜', '현미그라함쿠키'].

    `#`이 없으면 태그가 아니다 — 빈 목록을 준다. 소스가 안 준 것을 만들지 않는다(6장).
    """
    if not text:
        return []
    return [t.strip() for t in html_mod.unescape(text).split("#") if t.strip()]


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")
    _, detail_page, prefix = _ROUTES[category_code]

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("li.menu-list__item")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean_text(block.select_one("strong.menu-list__title"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        link = block.select_one("a.menu-list__link")
        match = _SEQ_RE.search(link.get("href", "") if link else "")
        seq = match.group(1) if match else None

        image = block.select_one("img.menu-list__image")
        hash_node = block.select_one("span.menu-list__hash")

        items.append({
            "source_id": SOURCE_ID,
            # 주의 1번: 네임스페이스를 붙이지 않으면 C·D가 A·F·B·E와 충돌한다.
            "external_id": f"{prefix}{seq}" if seq else _name_hash(name),
            "alt_ids": {"seq": seq} if seq else {},
            "name": name,
            "price": None,                    # 주의 2번: 가격을 주지 않는다
            "category_raw": CATEGORIES[category_code],
            "description": None,              # 주의 4번: 설명문은 상세에만 있다
            "tags": parse_tags(hash_node.get_text(" ", strip=True) if hash_node else None),
            "image_url": _absolute(image.get("src") if image else None),
            "source_url": (f"{BASE_URL}/menu/{detail_page}?seq={seq}" if seq else None),
            "scraped_at": scraped_at,
            # 주의 7번: 대조군으로만 쓴다. 판정에는 쓰지 않는다 (2.1).
            "_labels": {"new": "menu-list__item--new" in (block.get("class") or [])},
        })

    return items, skipped


def parse_detail(markup: str) -> dict:
    """상세 페이지 → {name, description, tags}.

    실측 구조(seq=1124):
        <p class="menu-view-header__category">ICECREAM</p>
        <h2 class="menu-view-header__title">
          <span class="…__title--en">SALTY RICE SYRUP NEW YORK CHEESE CAKE</span>
          <span class="…__title--ko">솔티 조청 뉴욕치즈케이크</span>
        </h2>
        <p class="menu-view-header__text">크림치즈 아이스크림에 달콤하고 …</p>

    ⚠️ **한글 제목만 이름으로 쓴다.** `__title` 전체를 읽으면 영문명이 앞에 붙어
    목록의 이름과 달라지고, `enrich.py`의 이름 대조가 전량 불일치로 떨어진다.

    태그는 상세에 없다 — 목록이 준다(주의 3번). 여기서 `[]`를 주면
    `enrich.py`가 스냅샷의 태그를 보존한다(4장의 `tags` 계약).
    """
    soup = BeautifulSoup(markup, "html.parser")
    return {
        "name": _clean_text(soup.select_one(".menu-view-header__title--ko")),
        "description": _clean_text(soup.select_one("p.menu-view-header__text")),
        "tags": [],
    }


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_detail(session: base.Session, external_id: str, *, week: str) -> dict:
    """상품 1건의 상세. diff가 걸러낸 신상에만 쓴다.

    `external_id`는 우리가 붙인 접두사를 달고 있다(`p1124` / `s79`).
    상세 경로가 그 접두사로 갈리므로 여기서 되돌린다 — **접두사를 떼고 숫자만
    쓰면 C·D 항목이 엉뚱한 상품의 상세를 가져온다**(주의 1번의 8건 충돌).
    """
    prefix, seq = external_id[:1], external_id[1:]
    page = {"p": "view.php", "s": "view_subcategory.php"}.get(prefix)
    if page is None or not seq.isdigit():
        raise ValueError(f"모르는 external_id 형식: {external_id!r} (p<숫자> 또는 s<숫자>)")

    resp = session.get(f"{BASE_URL}/menu/{page}?seq={seq}")
    base.save_raw(week, SOURCE_ID, f"detail_{external_id}", resp.text, "html")
    return parse_detail(resp.text)


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    list_page, _, _ = _ROUTES[category_code]
    url = f"{BASE_URL}/menu/{list_page}?category={category_code}"
    resp = session.get(url)
    markup = resp.text
    base.save_raw(week, SOURCE_ID, category_code, markup, "html")

    items, skipped = parse_list(markup, category_code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """배스킨라빈스 전체 카탈로그. 2026-08-25 실측 128건 / 6요청.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("배스킨라빈스 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="배스킨라빈스 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
