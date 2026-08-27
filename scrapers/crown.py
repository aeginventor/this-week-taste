"""크라운제과 제품 카탈로그.

정찰 근거: `docs/RECON_mart_fmcg.md` 7절. 골든 픽스처는 `tests/fixtures/crown_list_*.html`.

  GET https://www.crown.co.kr/product/index?searchCateCd=<탭코드>&currentPageNo=<쪽>
  서버 렌더링 HTML. 세션·토큰 불필요. 페이지당 12건.
  robots.txt가 **없다**(HTTP 404) → 금지 규칙도 없다. `base.Session`이 허용으로 간주한다.

이 소스에서 조심할 것 (전부 2026-08-27 실측):

  1. **`신제품` 탭이 다른 네 탭과 교집합이 0이다.** 비스킷·케이크·스낵·캔디/초콜릿만
     긁으면 신제품이 통째로 빠진다. 던킨·파리바게뜨·피자헛에 이어 **네 번째**로,
     "전체처럼 보이는 목록이 전체가 아닌" 소스다.
     그래서 `all` 탭의 총건수를 한 요청 더 써서 대조한다(`_assert_complete`).
     탭이 하나 늘어나면 우리 다섯 탭의 합이 모자라므로 시끄럽게 실패한다.
  2. ⚠️ **`신제품` 탭이 3건뿐이고 실제로 흔들린다.** 2026-08-26에 4건이었는데
     하루 뒤 `idx=389`(버터와플 with 이즈니)가 카탈로그 전체에서 사라져 3건이 됐다.
     상세 URL은 여전히 200을 주므로 목록에서만 내린 것이다.
     → 이 탭이 0~1건이 되면 `snapshot.py`의 건수 검증(직전 주의 30% 미만)에 걸려
     **소스 전체가 이월된다.** 오탐일 공산이 크지만 지금은 그대로 둔다 —
     문턱값을 손보는 것은 CLAUDE.md 8-1의 "먼저 묻는" 항목이다.
  3. **가격이 어디에도 없다.** 브랜드 사이트라 직접 판매를 하지 않는다(오리온과 같다).
     `price`는 항상 `null`이고, diff의 (이름, 가격) 계층이 무력해진다.
     다만 45건 실측에서 이름 중복은 0건이라 지금은 문제가 되지 않는다.
  4. **목록이 설명문을 45/45 준다**(`div.info > div`). 상세 페이지를 실제로 열어 봤으나
     제품정보 표(식품유형·내용량·소비기한)가 비어 있어 목록보다 주는 것이 없었다.
     스타벅스와 같은 이유로 `detail: False`다.
  5. **이미지 경로에 한글과 공백이 있다.** `/upload/system/product/<해시>_카라멜콘 … (2).jpg`.
     그대로 발행하면 깨지므로 퍼센트 인코딩해서 내보낸다. 인코딩한 주소로 200을 확인했다.
  6. 한 항목에 이미지가 2~3장(전면·후면)이다. 첫 장만 쓴다.
  7. `idx`가 주키다. 45건 중복 0건. **단조 증가 키로는 쓰지 않는다** — `idx=397`이
     `신제품`이 아니라 `케이크`에 있어서, 등록 순서와 신상 여부가 어긋난다.
     사이트에 날짜가 없어 검증할 방법도 없다(피자헛과 다른 점이다).
  8. `신제품` 탭 소속 여부를 `_labels.new`로 보낸다. **판정에 쓰지 않고**
     `snapshot.py`가 control 파일로 떼어 놓는다(2.1). 45건 중 3건이다.
     ⚠️ 채점표로 쓰려면 "지난주에도 붙어 있었나"를 먼저 확인해야 한다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/crown.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "crown"
BASE_URL = "https://www.crown.co.kr"
LIST_URL = f"{BASE_URL}/product/index?searchCateCd={{code}}&currentPageNo={{page}}"
DETAIL_URL = f"{BASE_URL}/product/view?idx={{idx}}"

# 탭 코드 → 표시 이름. `category_raw`에 이 이름이 들어간다.
# `신제품`은 나머지 넷과 교집합이 0이라 빼면 그만큼 사라진다 (주의 1번).
CATEGORIES = {
    "1478063307": "신제품",
    "1478063272": "비스킷",
    "1478063299": "케이크",
    "1478063302": "스낵",
    "1478063306": "캔디/초콜릿",
}

# 완전성 대조용. 우리가 긁는 다섯 탭의 합과 맞아야 한다 (주의 1번).
# 카테고리가 아니므로 CATEGORIES에 넣지 않는다 — 넣으면 전량이 이중 계산된다.
ALL_CODE = "all"

PAGE_SIZE = 12
MAX_PAGES = 20          # 45건 규모라 4쪽이면 끝난다. 무한 루프 방지용 상한이다.

# 실측 2026-08-27. 총 45건 / 7요청(다섯 탭 6쪽 + 완전성 대조 1).
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
# 탭마다 한 줄인 이유: 한 탭이 통째로 실패해도 총건수는 그럴듯하게 남는다.
BOOTSTRAP_COUNTS = {
    "1478063307": 3,
    "1478063272": 15,
    "1478063299": 6,
    "1478063302": 12,
    "1478063306": 9,
}

_IDX_RE = re.compile(r"view\('(\d+)'\)")


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


def _absolute_image(src: str | None) -> str | None:
    """이미지 경로를 절대 주소로. 한글·공백이 있으므로 퍼센트 인코딩한다 (주의 5번)."""
    if not src:
        return None
    src = html_mod.unescape(src.strip())
    if src.startswith("http"):
        return src
    return BASE_URL + urllib.parse.quote(src, safe="/")


def parse_total(markup: str) -> int:
    """소스가 밝힌 총건수(`총 <span>45</span>건 있습니다.`).

    받은 건수와 대조해야 페이지를 놓친 것을 알 수 있다. 없으면 예외다 —
    없는 것을 0으로 삼키면 페이지네이션이 첫 쪽에서 멈춘다.
    """
    soup = BeautifulSoup(markup, "html.parser")
    node = soup.select_one("div.search_area strong.tit span")
    if node is None or not (node.get_text(strip=True) or "").isdigit():
        raise ParseError("총건수를 찾지 못했다. 응답 구조가 바뀌었다.")
    return int(node.get_text(strip=True))


def parse_list(markup: str, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 탭 코드: {category_code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("ul.pro_list li.item")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        info = block.select_one("div.info")
        name = _clean_text(info.select_one("strong")) if info else None
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        idx_match = _IDX_RE.search(block.get("onclick") or "")
        idx = idx_match.group(1) if idx_match else None

        # 한 항목에 전면·후면 2~3장이 온다. 첫 장만 쓴다 (주의 6번).
        first_image = block.select_one("div.img img")

        items.append({
            "source_id": SOURCE_ID,
            "external_id": idx or _name_hash(name),
            "alt_ids": {"idx": idx} if idx else {},
            "name": name,
            "price": None,                      # 브랜드 사이트라 가격이 없다 (주의 3번)
            "category_raw": CATEGORIES[category_code],
            # 목록이 45/45 설명문을 준다. 상세를 다시 긁지 않는다 (주의 4번).
            "description": _clean_text(info.select_one("div")) if info else None,
            "tags": [],                         # 소스가 태그를 주지 않는다
            "image_url": _absolute_image(first_image.get("src") if first_image else None),
            "source_url": DETAIL_URL.format(idx=idx) if idx else None,
            "scraped_at": scraped_at,
            # `_` 접두 키는 스냅샷에 저장되지 않는다. 판정에 쓰지 않고 대조군으로만 쓴다 (주의 8번).
            "_labels": {"new": category_code == "1478063307"},
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    """탭 하나를 끝까지. 소스가 밝힌 총건수와 대조한다."""
    label = CATEGORIES[category_code]
    items: list[dict] = []
    received = 0
    total: int | None = None

    for page in range(1, MAX_PAGES + 1):
        markup = session.get(LIST_URL.format(code=category_code, page=page)).text
        base.save_raw(week, SOURCE_ID, f"{category_code}_{page}", markup, "html")

        total = parse_total(markup)
        page_items, skipped = parse_list(markup, category_code, scraped_at=scraped_at)
        if skipped:
            raise ParseError(
                f"{label}: 이름 없는 항목 {skipped}건. 응답 구조가 바뀌었을 가능성이 높다."
            )
        received += len(page_items)
        items.extend(page_items)
        if received >= total or not page_items:
            break
    else:
        raise ParseError(f"{label}: {MAX_PAGES}쪽을 넘겼다. 페이지네이션이 끝나지 않는다.")

    if received != total:
        raise ParseError(
            f"{label}: {received}건을 받았는데 소스는 {total}건이라고 한다. "
            "페이지를 놓쳤을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", label, category_code, len(items))
    return items


def _assert_complete(session: base.Session, got: int, *, week: str) -> None:
    """`전체` 탭이 밝힌 총건수와 우리가 모은 건수를 대조한다 (주의 1번).

    탭이 하나 늘어나면 우리 다섯 탭의 합이 모자라게 되는데, 그것을 알아채는
    유일한 방법이 **응답 밖에서 온 기준**이다. 요청 1건 값어치가 있다.
    """
    markup = session.get(LIST_URL.format(code=ALL_CODE, page=1)).text
    base.save_raw(week, SOURCE_ID, f"{ALL_CODE}_1", markup, "html")
    declared = parse_total(markup)
    if got != declared:
        raise ParseError(
            f"탭 다섯을 합쳐 {got}건인데 `전체` 탭은 {declared}건이라고 한다. "
            "우리가 모르는 탭이 생겼거나 한 탭이 통째로 빠졌다."
        )
    log.info("  완전성 대조: 탭 합계 %d == `전체` %d", got, declared)


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """크라운제과 전체 카탈로그. 실측 45건 / 7요청.

    한 탭이라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    # 일부 탭만 골라 돌릴 때는 대조가 성립하지 않는다(사람이 손으로 부를 때뿐이다).
    if categories is None:
        _assert_complete(session, len(items), week=week)

    log.info("크라운제과 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="크라운제과 카탈로그 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="탭 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    result = fetch(week=args.week, categories=args.category)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
