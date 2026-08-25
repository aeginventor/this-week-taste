"""파리바게뜨 제품 카탈로그.

정찰 근거: `sources/targets.yml`의 parisbaguette 항목, 골든 픽스처
`tests/fixtures/parisbaguette_list_bread_p1.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.paris.co.kr/wp-admin/admin-ajax.php
      ?action=pb_get_product_list&cat1=<카테고리 슬러그>&per_page=100&paged=<N>
  WordPress. 응답은 **HTML 조각**이고 `<ul data-total-count="170">`으로 전체 건수를 준다.
  세션·토큰 불필요. robots.txt는 `/wp-admin/`을 막으면서
  **`/wp-admin/admin-ajax.php`는 명시적으로 허용**한다(`Allow:`).

이 소스에서 조심할 것:

  1. ⚠️⚠️ **`/products/?cat1=<...>` 페이지는 카탈로그가 아니다.** 카테고리당 12건
     미리보기다(정찰 기록의 "cat1 순회로 250건"은 틀렸다). `/products/` 첫 화면은
     카테고리당 8건이고, 거기 박힌 `data-total-count`(45·30·49…)도 **하위 카테고리
     기준**이라 전체 건수가 아니다. **던킨 `/menu/all`과 같은 종류의 함정이다.**
  2. ⚠️ **카테고리 슬러그가 표시 이름과 다르다.** `간편식`의 슬러그는
     `퍼스트클래스키친`이고, `샌드위치/샐러드`는 `샌드위치-샐러드`다.
     슬러그는 `/wp-json/wp/v2/product_category`에서 실측했다.
  3. ⚠️ **첫 `<img>`는 base64 플레이스홀더다.** `img.guide`가 아니라 **`img.product-tb`**를
     읽어야 한다. 도미노의 lazyload와 같은 종류의 함정이다.
  4. **`external_id`는 상세 URL의 슬러그다.** 2026-08-25 실측 519건에서 중복 0건.
     ⚠️ 정찰 기록이 "슬러그에 한글 퍼센트 인코딩이 섞인다"고 경고했는데 **현재 목록에는
     0건**이다. 다만 REST API에는 그런 항목이 보이므로(`%ed%95%ab...` = 핫도그도넛)
     **디코딩을 걸어둔다** — 인코딩된 채로 키를 만들면 대소문자만 달라져도 다른 키가 된다.
  5. **이름이 6건 중복된다**(`단팥빵`·`소보루빵` 등이 카테고리를 달리해 두 번).
     슬러그가 다르므로 문제되지 않지만, 이름 해시로는 가를 수 없다.
  6. 가격이 없다. `price`는 항상 `null`이다.
  7. **설명문은 상세에만 있다**(`div.product-excerpt`) → `detail: True`.
     배스킨라빈스와 같은 배치다.
  8. ⚠️ 정찰이 "diff 궁합 **보통**"으로 적었다. 519건으로 카탈로그가 크고 시즌 회전이
     빨라 첫 diff에서 건수가 과다할 수 있다. W36에서 확인한다.
  9. ⚠️ **요청을 빠르게 던지면 503이 온다.** 2026-08-25 정찰 중 `base.Session`을
     쓰지 않고 13번쯤 연달아 보냈다가 막혔다. 간격 1초를 반드시 지킬 것.
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

if __package__ in (None, ""):  # `python scrapers/parisbaguette.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "parisbaguette"
BASE_URL = "https://www.paris.co.kr"
LIST_URL = (f"{BASE_URL}/wp-admin/admin-ajax.php?action=pb_get_product_list"
            "&cat1={slug}&per_page={size}&paged={page}")
DETAIL_URL = f"{BASE_URL}/product/{{slug}}/"

# 카테고리 **슬러그** → 표시 이름 (주의 2번). 슬러그는 REST taxonomy에서 실측했다.
CATEGORIES = {
    "브레드": "브레드",
    "케이크": "케이크",
    "샌드위치-샐러드": "샌드위치/샐러드",
    "선물": "선물",
    "디저트-스낵": "디저트/스낵",
    "커피-음료": "커피/음료",
    "퍼스트클래스키친": "간편식",
}

# 2026-08-25 실측. 총 519건 / 8요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {
    "브레드": 170, "케이크": 53, "샌드위치-샐러드": 59, "선물": 61,
    "디저트-스낵": 74, "커피-음료": 75, "퍼스트클래스키친": 27,
}

PAGE_SIZE = 100         # 서버가 존중한다(실측). 브레드 170건이 2요청에 온다.
MAX_PAGES = 10          # 폭주 방지. 최대(브레드)가 2페이지였으므로 넉넉하다.

_SLUG_RE = re.compile(r"/product/([^/]+)/?$")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", html_mod.unescape(text)).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_slug(href: str | None) -> str | None:
    """상세 URL에서 슬러그를 뽑아 **디코딩**한다 (주의 4번).

    `/product/potato-chewy-rice-cake-1pcs/` → `potato-chewy-rice-cake-1pcs`
    `/product/%ed%95%ab%eb%8f%84%ea%b7%b8%eb%8f%84%eb%84%9b/` → `핫도그도넛`
    """
    if not href:
        return None
    match = _SLUG_RE.search(href)
    return urllib.parse.unquote(match.group(1)) if match else None


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_total(markup: str) -> int | None:
    """`<ul data-total-count="170">` → 170. 건수 검증의 근거다."""
    node = BeautifulSoup(markup, "html.parser").select_one("[data-total-count]")
    if node is None:
        return None
    try:
        return int(node["data-total-count"])
    except (KeyError, ValueError):
        return None


def parse_list(markup: str, slug: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML 조각 → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if slug not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 슬러그: {slug!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("a.product-list-item")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean(block.select_one("h3.product-name").get_text(strip=True)
                      if block.select_one("h3.product-name") else None)
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        href = block.get("href")
        product_slug = parse_slug(href)
        # 주의 3번: 첫 img는 base64 플레이스홀더다.
        image = block.select_one("img.product-tb")

        items.append({
            "source_id": SOURCE_ID,
            "external_id": product_slug or _name_hash(name),
            "alt_ids": {"slug": product_slug} if product_slug else {},
            "name": name,
            "price": None,                    # 주의 6번: 가격을 주지 않는다
            "category_raw": CATEGORIES[slug],
            "description": None,              # 주의 7번: 설명문은 상세에 있다
            "tags": [],
            "image_url": _clean(image.get("src") if image else None),
            "source_url": href or (DETAIL_URL.format(slug=urllib.parse.quote(product_slug))
                                   if product_slug else None),
            "scraped_at": scraped_at,
            # 목록 조각에 신상 배지가 없다. `_labels`를 채우지 않는다.
        })

    return items, skipped


def parse_detail(markup: str) -> dict:
    """상세 페이지 → {name, description, tags}.

    실측 구조:
        <div class="product-basic-info">
          <h1 class="product-name">감자쫀떡(1개입)</h1>
          <div class="product-meta">
            <div class="product-excerpt">담백한 감자에 달콤 짭짜름한 버터를 …</div>

    태그는 상세에 없다. `[]`를 주면 `enrich.py`가 스냅샷의 태그를 보존한다(4장).
    """
    soup = BeautifulSoup(markup, "html.parser")
    return {
        "name": _clean(soup.select_one("h1.product-name").get_text(strip=True)
                       if soup.select_one("h1.product-name") else None),
        "description": _clean(soup.select_one("div.product-excerpt").get_text(" ", strip=True)
                              if soup.select_one("div.product-excerpt") else None),
        "tags": [],
    }


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_detail(session: base.Session, external_id: str, *, week: str) -> dict:
    """상품 1건의 상세. diff가 걸러낸 신상에만 쓴다.

    `external_id`가 디코딩된 슬러그이므로 요청 전에 다시 인코딩한다(주의 4번).
    """
    url = DETAIL_URL.format(slug=urllib.parse.quote(external_id))
    resp = session.get(url)
    base.save_raw(week, SOURCE_ID, f"detail_{external_id}", resp.text, "html")
    return parse_detail(resp.text)


def fetch_category(session: base.Session, slug: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    """카테고리 하나를 끝까지. `data-total-count`로 다 받았는지 확인한다."""
    items: list[dict] = []
    total: int | None = None

    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL.format(slug=urllib.parse.quote(slug), size=PAGE_SIZE, page=page)
        markup = session.get(url).text
        base.save_raw(week, SOURCE_ID, f"{slug}_{page}", markup, "html")

        if total is None:
            total = parse_total(markup)

        page_items, skipped = parse_list(markup, slug, scraped_at=scraped_at)
        if skipped:
            raise ParseError(
                f"{CATEGORIES[slug]}: 이름 없는 항목 {skipped}건. "
                "응답 구조가 바뀌었을 가능성이 높다.")
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < PAGE_SIZE:
            break
    else:
        raise ParseError(
            f"{CATEGORIES[slug]}: {MAX_PAGES}페이지를 넘겼다. "
            "페이지네이션이 끝나지 않는다.")

    # 소스가 스스로 밝힌 전체 건수와 맞는지 본다. 어긋나면 페이지를 놓친 것이다.
    if total is not None and len(items) != total:
        raise ParseError(
            f"{CATEGORIES[slug]}: {len(items)}건을 받았는데 소스는 {total}건이라고 한다. "
            "페이지를 놓쳤을 가능성이 높다.")

    log.info("  %s(%s): %d건", CATEGORIES[slug], slug, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """파리바게뜨 전체 카탈로그. 2026-08-25 실측 519건 / 8요청.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    slugs = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for slug in slugs:
        items.extend(fetch_category(session, slug, week=week, scraped_at=scraped_at))

    log.info("파리바게뜨 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="파리바게뜨 제품 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 슬러그. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
