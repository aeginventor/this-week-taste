"""맘스터치 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 momstouch 항목, 골든 픽스처
`tests/fixtures/momstouch_list_CG0005.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://momstouch.co.kr/menu/new.php?s_sect1=<코드>
  순수 서버 렌더링(정찰에서 XHR이 한 건도 발생하지 않는 것을 확인했다).
  세션·토큰 불필요. 페이지네이션 없음.
  ⚠️ `robots.txt`가 302로 홈에 넘어간다 → 규칙 없음(허용). `base.Session`이 확인한다.

이 소스에서 조심할 것:

  1. ⚠️ **제품명이 두 조각으로 나뉜다** — `<h3><span>Cider</span>사이다</h3>`.
     `span`이 영문명이고 그 **뒤의 텍스트 노드**가 한글명이다. `get_text()`를 그대로
     쓰면 `Cider사이다`가 된다. `span`을 떼고 남은 텍스트를 이름으로 쓴다.
     ⚠️ `span`이 비어 있는 항목도 많다(영문명이 없는 경우).
  2. ⚠️ **이미지가 `<img src>`가 아니다.** `<figure><span style="background-image:
     url('/upload_file/...')">` 형태의 인라인 CSS라 일반 파서로는 못 잡는다.
     `style` 속성에서 정규식으로 뽑는다.
  3. **`new` 탭은 긁지 않는다.** 2026-08-25 실측: 8탭 70건 중 고유 id가 66개인데,
     차이 4건이 정확히 `new` 탭의 4건이다 — **전부 다른 탭에도 실려 있다.**
     빼면 중복이 0이 되고 요청도 하나 준다. 신상 여부는 항목의 `i.new` 배지로 알 수 있다.
  4. **`또잇`(CG0045)도 긁지 않는다.** 실측 0건이라 건수 검증의 기준이 될 수 없다.
     카테고리가 부활하면 `CATEGORIES`에 넣는다.
  5. **목록이 설명문을 준다** → `detail: False`. 두 종류가 있다 —
     `p.sub-text`(짧은 홍보 문구)와 그 뒤 `p`(제품 설명). **뒤의 것을 쓴다.**
  6. 가격이 없다. `price`는 항상 `null`이다.
  7. 상세 URL이 있다 — `go_view('304')`가 `view.php?idx=304`로 간다(실측 확인).
     ⚠️ 원본 JS는 목록 상태(`s_sect1` 등)를 쿼리에 잔뜩 붙이지만 **`idx` 하나면 열린다.**
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/momstouch.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "momstouch"
BASE_URL = "https://momstouch.co.kr"
LIST_URL = f"{BASE_URL}/menu/new.php?s_sect1={{code}}"
DETAIL_URL = f"{BASE_URL}/menu/view.php?idx={{idx}}"

# `s_sect1` 코드 → 사이트 탭 이름. `new`와 `CG0045`는 뺐다(주의 3번·4번).
CATEGORIES = {
    "CG0005": "버거",
    "CG0004": "치킨",
    "CG0003": "맘스세트",
    "CG0002": "사이드",
    "CG0001": "음료",
    "CG0046": "피자",
}

# 2026-08-25 실측. 총 66건 / 6요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"CG0005": 12, "CG0004": 12, "CG0003": 10,
                    "CG0002": 12, "CG0001": 9, "CG0046": 11}

_IDX_RE = re.compile(r"go_view\(['\"]?(\d+)")
_BG_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", html_mod.unescape(text)).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


def parse_name(h3) -> tuple[str | None, str | None]:
    """`<h3><span>Cider</span>사이다</h3>` → `('사이다', 'Cider')` (주의 1번).

    한글명이 `name`이고 영문명은 버린다 — 4장의 `name`은 하나뿐이고,
    이 소스에서 사람이 읽는 이름은 한글 쪽이다.
    """
    if h3 is None:
        return None, None
    span = h3.select_one("span")
    english = _clean(span.get_text(strip=True)) if span else None
    if span:
        span.extract()
    return _clean(h3.get_text(" ", strip=True)), english


def parse_image(figure) -> str | None:
    """인라인 CSS `background-image: url(...)`에서 경로를 뽑는다 (주의 2번)."""
    if figure is None:
        return None
    for node in figure.select("[style]"):
        match = _BG_RE.search(node.get("style") or "")
        if match:
            return _absolute(match.group(1).strip())
    return None


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = [li for li in soup.select("li") if li.select_one("h3")]
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name, _english = parse_name(block.select_one("h3"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        link = block.select_one("a[href*='go_view']")
        match = _IDX_RE.search(link.get("href", "") if link else "")
        idx = match.group(1) if match else None

        # 주의 5번: `p.sub-text`는 홍보 문구, 그 뒤 `p`가 제품 설명이다.
        paragraphs = [p for p in block.select("p")
                      if "sub-text" not in (p.get("class") or [])]
        description = _clean(paragraphs[-1].get_text(" ", strip=True)) if paragraphs else None

        items.append({
            "source_id": SOURCE_ID,
            "external_id": idx or _name_hash(name),
            "alt_ids": {"idx": idx} if idx else {},
            "name": name,
            "price": None,                    # 주의 6번: 가격을 주지 않는다
            "category_raw": CATEGORIES[code],
            "description": description,       # 주의 5번
            "tags": [],
            "image_url": parse_image(block.select_one("figure")),
            "source_url": DETAIL_URL.format(idx=idx) if idx else None,
            "scraped_at": scraped_at,
            # 소스의 신상 배지. 대조군으로만 쓴다 — 판정에는 쓰지 않는다 (2.1).
            "_labels": {"new": block.select_one("i.new") is not None},
        })

    return items, skipped


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    markup = session.get(LIST_URL.format(code=code)).text
    base.save_raw(week, SOURCE_ID, code, markup, "html")

    items, skipped = parse_list(markup, code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )
    if not items:
        raise ParseError(
            f"{CATEGORIES[code]}({code}): 0건. 카테고리 코드가 바뀌었을 수 있다 "
            "(2026-08-25에 `또잇`이 이 이유로 빠졌다).")

    log.info("  %s(%s): %d건", CATEGORIES[code], code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """맘스터치 전체 카탈로그. 2026-08-25 실측 66건 / 6요청.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("맘스터치 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="맘스터치 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="s_sect1 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
