"""오리온 제품 카탈로그.

정찰 근거: `docs/RECON_mart_fmcg.md` 7절, 골든 픽스처 `tests/fixtures/orion_list_0101.html`.

  GET https://www.orionworld.com/goods/list/<목록번호>?category=<코드>
  서버 렌더링 HTML. 세션·토큰 불필요.
  robots.txt는 `/thdadmin/`, `/upload/`만 막는다. 목록·상세 경로는 허용된다.

이 소스에서 조심할 것 (전부 2026-08-12 실측으로 확인했다):

  1. **가격이 어디에도 없다.** 목록에도 상세에도 없다. 브랜드 사이트라 직접 판매를
     하지 않기 때문이다. `price`는 항상 `null`이다. 이것이 diff에 영향을 준다 —
     (이름, 가격) 계층이 사실상 (이름, None)이 되므로 동명이인을 못 가른다.
     실제로 `후레쉬베리`가 goodsno 6과 137로 두 건 있다. `goodsno` 매칭이 필수다.
  2. **목록 번호와 카테고리 코드가 짝으로 묶여 있다.** `category=0201`은 `list/35`에서만
     나오고 다른 목록 번호에서는 0건이다. 네비게이션에서 실측한 짝을 그대로 쓴다.
  3. **페이지네이션이 없다.** `page=2`를 붙이면 0건이 온다. 카테고리당 1요청이다.
  4. **`마켓오네이처`(0201)는 실제로 빈 카테고리다.** 사이트에 링크는 있는데 제품이 없다.
     빼지 않고 남겨둔다 — 나중에 제품이 생기면 그때 diff가 신상으로 잡아야 한다.
  5. 제품명이 `<h8>`에 있다. 표준 태그가 아니지만 파서가 처리한다.
     `<a>` 전체 텍스트를 쓰면 신제품 배지의 "신제품"이 이름 앞에 붙는다.
  6. `span.icon.new`(소스의 신상 라벨)는 **판정에 쓰지 않는다** (CLAUDE.md 2.1).
     `_labels`에 담아 보내고 snapshot.py가 별도 파일로 분리한다.
     정찰에서 이 라벨이 8건이었고 카탈로그가 115건이라, CU(671/5,082)보다
     대조군으로서 훨씬 쓸 만하다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/orion.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "orion"
BASE_URL = "https://www.orionworld.com"
LIST_URL = f"{BASE_URL}/goods/list/{{list_no}}?category={{category}}"
DETAIL_URL = f"{BASE_URL}/goods/view/{{list_no}}?goodsno={{goodsno}}&category={{category}}"

# 카테고리 코드 → 표시 이름. `category_raw`에 이 이름이 들어간다.
# 계층이 두 단계면 `>`로 잇는다 (CLAUDE.md 4장).
CATEGORIES = {
    "0101": "파이",
    "0102": "스낵",
    "0103": "비스킷",
    "0104": "캔디",
    "0105": "껌",
    "0106": "초콜릿",
    "0107": "마켓오",
    "0201": "마켓오네이처",
    "0202": "오!그래놀라",
    "0203": "오!그래놀라 바",
    "0204": "한끼바",
    "0301": "닥터유 > 용암수/면역수",
    "0302": "닥터유 > 바/볼",
    "0303": "닥터유 > 음료/파우더",
    "0304": "닥터유 > 스낵",
}

# 카테고리 코드 → 목록 번호. 네비게이션 링크에서 실측했다(주의 2번).
# `03`(닥터유)은 0301~0304의 합집합이라 넣지 않는다. 넣으면 이중 계산된다.
LIST_IDS = {
    "0101": 26, "0102": 27, "0103": 28, "0104": 29, "0105": 30,
    "0106": 31, "0107": 32,
    "0201": 35, "0202": 36, "0203": 37, "0204": 139,
    "0301": 38, "0302": 125, "0303": 126, "0304": 129,
}

# 실측 2026-08-12. 총 115건 / 15요청. `0201`(마켓오네이처)은 사이트에 링크는 있는데
# 제품이 0건이다. 기대치 0은 검사에서 건너뛰므로 오탐을 내지 않는다.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {
    "0101": 11, "0102": 24, "0103": 24, "0104": 23, "0105": 3,
    "0106": 4, "0107": 2, "0201": 0, "0202": 6, "0203": 2,
    "0204": 1, "0301": 3, "0302": 5, "0303": 6, "0304": 1,
}

_GOODSNO_RE = re.compile(r"goodsno=(\d+)")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 사이트가 바뀌었다는 뜻이므로 조용히 넘기지 않는다."""


# ── 파싱 (네트워크 없이 단독으로 검증 가능하게 분리) ──────────────────


def _clean_text(node) -> str | None:
    if node is None:
        return None
    text = html_mod.unescape(node.get_text(strip=True))
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_list(markup: str, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select('a[href*="/goods/view/"]')
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        # ⚠️ block.get_text()를 쓰면 안 된다. 신제품 배지의 "신제품"이 이름 앞에 붙는다.
        name = _clean_text(block.select_one("h8"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        goodsno_match = _GOODSNO_RE.search(block.get("href", ""))
        goodsno = goodsno_match.group(1) if goodsno_match else None

        img = block.select_one("img")
        image_url = img.get("src") if img else None
        if image_url and image_url.startswith("/"):
            image_url = BASE_URL + image_url

        # goodsno가 주키다. 115건 실측에서 중복 0건이었다.
        # 이름은 중복이 있으므로(후레쉬베리 ×2) 이름 해시로는 가를 수 없다.
        items.append({
            "source_id": SOURCE_ID,
            "external_id": goodsno or _name_hash(name),
            "alt_ids": {"goodsno": goodsno} if goodsno else {},
            "name": name,
            "price": None,                      # 오리온은 가격을 주지 않는다 (주의 1번)
            "category_raw": CATEGORIES[category_code],
            "description": None,        # 오리온도 상세에만 있다. enrich가 채운다
            "image_url": image_url,
            "source_url": DETAIL_URL.format(
                list_no=LIST_IDS[category_code], goodsno=goodsno,
                category=category_code) if goodsno else None,
            "scraped_at": scraped_at,
            # `_` 접두 키는 스냅샷에 저장되지 않는다. 판정에 쓰지 않고 대조군으로만 쓴다.
            "_labels": {"new": block.select_one("span.icon.new") is not None},
        })

    return items, skipped


def parse_detail(markup: str) -> dict:
    """상세 페이지 → {name, description, tags}.

    실측 구조(goodsno=175):
        <h3>오뜨 애플파이</h3>
        <p>사각사각 씹히는 애플 콩포트가 들어간 데일리 디저트!</p>
        <dl>중량 175g / 칼로리 720kcal / 소비기한 6개월 / 알러지 …</dl>

    `dl`은 영양·알러지 정보라 태그가 아니다. CU의 태그(`샐러드`, `간편식사` 같은
    분류어)에 대응하는 것이 오리온에는 없으므로 `tags`는 항상 비어 있다.
    지어내지 않는다 (CLAUDE.md 6장).
    """
    soup = BeautifulSoup(markup, "html.parser")
    return {
        "name": _clean_text(soup.select_one("h3")),
        "description": _clean_text(soup.select_one("p")),
        "tags": [],
    }


def fetch_detail(session: base.Session, goodsno: str, *, week: str) -> dict:
    """상품 1건의 상세. diff가 걸러낸 신상에만 쓴다."""
    # 상세는 목록 번호·카테고리를 안 봐도 열린다. 아무 값이나 넣어도 되지만
    # 재현 가능하도록 파이(26/0101)로 고정한다.
    url = DETAIL_URL.format(list_no=26, goodsno=goodsno, category="0101")
    resp = session.get(url)
    base.save_raw(week, SOURCE_ID, f"detail_{goodsno}", resp.text, "html")
    return parse_detail(resp.text)


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    url = LIST_URL.format(list_no=LIST_IDS[category_code], category=category_code)
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
    """오리온 전체 카탈로그. 카테고리당 1요청, 총 15요청 / 약 115건.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("오리온 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="오리온 카탈로그 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    result = fetch(week=args.week, categories=args.category)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
