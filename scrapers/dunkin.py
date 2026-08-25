"""던킨 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 dunkin 항목, 골든 픽스처
`tests/fixtures/dunkin_list_cat1_p1.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.dunkindonuts.co.kr/menu?cat=<코드>&page=<N>
  Laravel + Inertia.js. HTML의 `<div id="app" data-page="{...}">`에 페이지 데이터가
  통째로 들어 있다 — `html.unescape()` 후 `json.loads()`면 순수 JSON이 나온다.
  세션·토큰 불필요. robots.txt는 `Allow: /`.

  ⚠️ `X-Inertia` 헤더를 붙이면 JSON만 받을 수 있지만 쓰지 않는다. 헤더에는
  `X-Inertia-Version`이 필요하고 그 값이 배포마다 바뀌어서, 버전이 어긋나면
  서버가 409로 전체 새로고침을 요구한다. **일반 브라우저와 같은 요청**을 보내고
  우리가 파싱하는 쪽이 깨질 자리가 하나 적다.

이 소스에서 조심할 것:

  1. ⚠️ **응답 키가 카테고리마다 다르다.** 대부분 `props.products`인데
     COFFEE(cat=6)만 `props.productCats`다. 서브카테고리 구분이 있는 카테고리
     (`SUBCATEGORY_DIV_YN: 1`)가 그렇다. 한 키만 보고 짜면 **그 카테고리가 통째로
     0건이 되고 예외도 안 난다.** 둘 다 본다.
  2. ⚠️ **두 키의 `id`가 별도 네임스페이스다.** 2026-08-25 실측: 216건 중
     2건이 충돌한다 — id 4는 `DONUT/카카오 후로스티드`와 `COFFEE/카푸치노`,
     id 132는 `COFFEE/자이언트 버킷 아메리카노`와 `BEVERAGE/밀크티`.
     그래서 `external_id`에 접두사를 붙인다(`p536` / `c8`).
     소스 원본 값은 `alt_ids.id`에 그대로 남긴다.
  3. ⚠️ **정찰 기록의 카테고리 코드가 틀렸다.** 기록은 `3 COFFEE / 5 BEVERAGE /
     6 SNACK&MORE`였으나 실측은 **3 BEVERAGE / 5 SNACK & MORE / 6 COFFEE**다.
  4. ⚠️ **`/menu/all`은 카테고리당 4건 미리보기다.** 스냅샷용으로 쓰면 안 된다.
  5. **이름이 3건 중복된다** (`티라미수 롤 케이크`, `소금우유 쿠키슈`,
     `에스프레소 쿠키슈` — 일반 매장판과 WONDERS판). 이름 해시로는 가를 수 없으나
     `id`가 있으므로 문제되지 않는다.
  6. **가격이 없다.** `price`는 항상 `null`이다.
  7. **설명문과 태그가 둘 다 상세에 있다**(`EXPLAIN`, `HASHTAG`) → `detail: True`.
     배스킨라빈스와 정반대다 — 그쪽은 태그를 목록이, 설명문을 상세가 준다.
  8. 카테고리 분류는 **cat1(5개) 단위**로만 싣는다. 서브카테고리(23종)까지
     `category_raw`에 넣으면 `snapshot.py`의 건수 검증이 `CATEGORIES`와
     대조하지 못해 조용히 전부 지나친다. 홈플러스가 같은 이유로
     **수집 단위와 `category_raw`를 일치**시켰다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/dunkin.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "dunkin"
BASE_URL = "https://www.dunkindonuts.co.kr"
LIST_URL = f"{BASE_URL}/menu?cat={{category}}&page={{page}}"
DETAIL_URL = f"{BASE_URL}/menu/view?cat={{cat1}}&sub={{cat2}}&id={{id}}"

# cat1 코드 → 응답의 `PRODUCT_CAT1_NM`. 주의 3번(정찰 기록과 다르다)을 실측으로 고쳤다.
CATEGORIES = {
    "1": "DONUT",
    "2": "FOOD",
    "3": "BEVERAGE",
    "5": "SNACK & MORE",
    "6": "COFFEE",
}

# 2026-08-25 실측. 총 216건 / 20요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"1": 91, "2": 15, "3": 59, "5": 31, "6": 20}

MAX_PAGES = 30          # 폭주 방지. 최대 카테고리(DONUT)가 8페이지였으므로 넉넉하다.

_DATA_PAGE_RE = re.compile(r'<div id="app"[^>]*\sdata-page="(.*?)"', re.S)

# 주의 1번·2번: 응답 키와 `external_id` 접두사가 짝을 이룬다.
_PAYLOAD_KEYS = (("products", "p"), ("productCats", "c"))


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(value) -> str | None:
    if value is None:
        return None
    text = html_mod.unescape(str(value)).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def extract_data_page(markup: str) -> dict:
    """Inertia의 `data-page` 속성에서 페이지 데이터를 꺼낸다.

    이 한 줄이 이 소스의 전부다. 마크업이 바뀌면 여기서 시끄럽게 죽는다 —
    조용히 0건을 내보내는 것보다 낫다(2.4).
    """
    match = _DATA_PAGE_RE.search(markup)
    if not match:
        raise ParseError(
            "`<div id=\"app\" data-page=…>`를 찾지 못했다. "
            "Inertia 마크업이 바뀌었을 가능성이 높다.")
    try:
        return json.loads(html_mod.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise ParseError(f"data-page가 JSON이 아니다: {exc}") from exc


def _payload(page_data: dict) -> tuple[dict, str]:
    """(목록 봉투, external_id 접두사). 주의 1번 — 키가 카테고리마다 다르다."""
    props = page_data.get("props") or {}
    for key, prefix in _PAYLOAD_KEYS:
        if key in props:
            return props[key], prefix
    raise ParseError(
        f"목록 키를 찾지 못했다. 기대: {[k for k, _ in _PAYLOAD_KEYS]}, "
        f"실제 props: {sorted(props)}")


def parse_page(page_data: dict, category_code: str,
               *, scraped_at: str) -> tuple[list[dict], int]:
    """페이지 데이터 → (스냅샷 항목들, 마지막 페이지 번호)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")

    envelope, prefix = _payload(page_data)
    rows = envelope.get("data") or []
    last_page = int((envelope.get("meta") or {}).get("last_page") or 1)

    items: list[dict] = []
    for row in rows:
        name = _clean(row.get("TITLE"))
        if not name:
            log.warning("이름이 없는 항목을 건너뛴다: id=%s", row.get("id"))
            continue

        product_id = row.get("id")
        cat1 = row.get("dd_product_cat1_id")
        cat2 = row.get("dd_product_cat2_id")

        items.append({
            "source_id": SOURCE_ID,
            # 주의 2번: 접두사가 없으면 products와 productCats의 id가 충돌한다.
            "external_id": f"{prefix}{product_id}" if product_id else _name_hash(name),
            "alt_ids": {"id": str(product_id)} if product_id else {},
            "name": name,
            "price": None,                    # 주의 6번: 가격을 주지 않는다
            # 주의 8번: cat1만 싣는다. 응답이 이름을 주므로 원문을 쓴다(4장).
            "category_raw": _clean(row.get("PRODUCT_CAT1_NM")),
            "description": None,              # 주의 7번: 설명문은 상세에 있다
            "tags": [],                       # 〃 태그도 상세에 있다
            "image_url": _absolute(row.get("MAIN_IMG_FILE")),
            "source_url": (DETAIL_URL.format(cat1=cat1, cat2=cat2, id=product_id)
                           if product_id and cat1 and cat2 else None),
            "scraped_at": scraped_at,
            # 소스의 신상 표시는 서브카테고리 `신제품`뿐이다(DONUT에만 있다).
            # 대조군으로만 보낸다 — 판정에는 쓰지 않는다 (2.1).
            "_labels": {"new": _clean(row.get("PRODUCT_CAT2_NM")) == "신제품"},
        })

    return items, last_page


def parse_detail(page_data: dict) -> dict:
    """상세 페이지 데이터 → {name, description, tags}.

    실측 구조(cat=1&sub=37&id=536):
        props.product.data.TITLE    "페이머스 글레이즈드"
        props.product.data.EXPLAIN  "더욱 촉촉하고 부드러워진 달콤한 정통 도넛"
        props.product.data.HASHTAG  [{"HASHTAG": "#글레이즈드"}, …]

    ⚠️ `props.products`(복수)는 같은 서브카테고리의 **다른 제품 목록**이다.
    `props.product`(단수)를 봐야 한다. 복수를 읽으면 첫 항목의 설명이 전 제품에 붙는다.
    """
    data = ((page_data.get("props") or {}).get("product") or {}).get("data") or {}
    tags = [t for t in ((_clean(h.get("HASHTAG")) or "").lstrip("#")
                        for h in (data.get("HASHTAG") or [])) if t]
    return {
        "name": _clean(data.get("TITLE")),
        "description": _clean(data.get("EXPLAIN")),
        "tags": tags,
    }


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_detail(session: base.Session, external_id: str, *, week: str) -> dict:
    """상품 1건의 상세. diff가 걸러낸 신상에만 쓴다.

    상세 URL은 cat1·cat2를 요구하는데 `external_id`에는 없다. 그런데 **셋 다
    아무 값이나 넣어도 열린다** — 서버가 `id`로만 조회한다(2026-08-25 실측).
    재현 가능하도록 도넛/클래식(1/37)으로 고정한다.
    """
    seq = external_id[1:]
    if external_id[:1] not in {p for _, p in _PAYLOAD_KEYS} or not seq.isdigit():
        raise ValueError(f"모르는 external_id 형식: {external_id!r} (p<숫자> 또는 c<숫자>)")

    resp = session.get(DETAIL_URL.format(cat1=1, cat2=37, id=seq))
    base.save_raw(week, SOURCE_ID, f"detail_{external_id}", resp.text, "html")
    return parse_detail(extract_data_page(resp.text))


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    """카테고리 하나를 마지막 페이지까지."""
    items: list[dict] = []
    seen: set[str] = set()
    last_page = 1
    page = 1

    while page <= min(last_page, MAX_PAGES):
        url = LIST_URL.format(category=category_code, page=page)
        markup = session.get(url).text
        base.save_raw(week, SOURCE_ID, f"cat{category_code}_p{page}", markup, "html")

        page_items, last_page = parse_page(extract_data_page(markup), category_code,
                                           scraped_at=scraped_at)
        # 서버가 마지막 페이지를 되감으면 같은 항목을 무한히 쌓게 된다. 본 적 없는 것만 받는다.
        fresh = [i for i in page_items if i["external_id"] not in seen]
        if page > 1 and not fresh:
            log.warning("  %s(%s) %d페이지가 이전 페이지를 되풀이한다. 여기서 멈춘다.",
                        CATEGORIES[category_code], category_code, page)
            break
        seen.update(i["external_id"] for i in fresh)
        items.extend(fresh)
        page += 1

    if last_page > MAX_PAGES:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 마지막 페이지가 {last_page}로 상한"
            f"({MAX_PAGES})을 넘는다. 페이지네이션이 예상과 다르다.")

    log.info("  %s(%s): %d건 / %d페이지",
             CATEGORIES[category_code], category_code, len(items), page - 1)
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """던킨 전체 카탈로그. 2026-08-25 실측 216건 / 20요청.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("던킨 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="던킨 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="cat1 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
