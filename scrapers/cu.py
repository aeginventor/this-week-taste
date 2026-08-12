"""CU (BGF리테일) 전 카테고리 카탈로그.

정찰 근거: `docs/RECON_REPORT.md` 1.1절, 골든 픽스처 `tests/fixtures/cu_productAjax_p1.html`.

  POST https://cu.bgfretail.com/product/productAjax.do
       pageIndex=1&searchMainCategory=10&codeParent=10&listType=0
  응답은 JSON이 아니라 HTML 조각(`<li class="prod_list">`). 세션·토큰 불필요.
  robots.txt는 HTTP 404(파일 없음) → 금지 규칙 없음.

이 소스에서 조심할 것 (전부 실측으로 확인했다):

  1. 제품명이 **소스 단계에서 12자로 잘려 있다** (`샐)오리지널닭가슴살샐러`).
     상세 페이지도 동일하므로 우리 파싱 문제가 아니다. 복원하지 않는다 (CLAUDE.md 6장).
  2. 이미지 파일명이 바코드인데 일부는 `8809655892303_1.jpg`처럼 접미사가 붙는다.
     40건 중 5건. `_` 앞까지만 취한다.
  3. 이미지 URL이 프로토콜 상대 경로(`//tqk...`)다. `https:`를 붙여야 한다.
  4. **목록은 gdIdx 오름차순이다.** 1페이지가 가장 오래된 상품이고 신상은 마지막 페이지에 있다.
     페이지를 끝까지 돌지 않으면 신상을 영영 못 본다.
  5. `.tag > span.new`(소스의 신상 라벨)는 **판정에 쓰지 않는다** (CLAUDE.md 2.1).
     검증용 대조군으로만 쓰려고 `_labels`에 담아 보내고, snapshot.py가 별도 파일로 분리한다.
     `_` 로 시작하는 키는 스냅샷 파일에 저장되지 않는다.

카테고리는 응답 본문에 없다. 우리가 요청한 `searchMainCategory`로 역산해 `category_raw`에 넣는다
(CLAUDE.md 4장이 허용하는 형태). 그래서 계층 구분자 `>` 없이 1단계 이름뿐이다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/cu.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "cu"
BASE_URL = "https://cu.bgfretail.com"
LIST_URL = f"{BASE_URL}/product/productAjax.do"
LIST_REFERER = f"{BASE_URL}/product/product.do?category=product&depth2=4"
DETAIL_URL = f"{BASE_URL}/product/view.do?category=product&gdIdx={{gd_idx}}"

# 실측: 페이지당 40개 고정. 서버가 다른 값을 받지 않는다.
PAGE_SIZE = 40
# 폭주 방지. 최대 카테고리(식품)가 43페이지였으므로 넉넉하다.
MAX_PAGES = 200

# `searchMainCategory` = `codeParent`. 정찰 실측 건수는 snapshot.py의 기대치와 맞춰 둔다.
CATEGORIES = {
    "10": "간편식사",
    "20": "즉석조리",
    "30": "과자류",
    "40": "아이스크림",
    "50": "식품",
    "60": "음료",
    "70": "생활용품",
}

_GD_IDX_RE = re.compile(r"view\((\d+)\)")
_BARCODE_RE = re.compile(r"^\d{8,14}$")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 사이트가 바뀌었다는 뜻이므로 조용히 넘기지 않는다."""


# ── 파싱 (네트워크 없이 단독으로 검증 가능하게 분리) ──────────────────


def _clean_text(node) -> str | None:
    if node is None:
        return None
    text = html_mod.unescape(node.get_text(strip=True))
    return text or None


def _parse_price(node) -> int | None:
    text = _clean_text(node)
    if not text:
        return None
    digits = text.replace(",", "").strip()
    if not digits.isdigit():
        log.warning("가격을 숫자로 읽을 수 없다: %r", text)
        return None
    return int(digits)


def _barcode_from_image(image_url: str | None) -> str | None:
    """이미지 파일명에서 바코드를 뽑는다. `.../8809655892303_1.jpg` → `8809655892303`."""
    if not image_url:
        return None
    stem = image_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    candidate = stem.split("_", 1)[0]
    return candidate if _BARCODE_RE.match(candidate) else None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_list(markup: str, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML 조각 → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수).

    개별 블록은 방어적으로 다루되(5장), 건너뛴 수를 돌려주어 호출자가 시끄럽게
    실패할 수 있게 한다(2.4). 여기서 예외를 삼키지는 않는다.
    """
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("li.prod_list")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean_text(block.select_one("div.name > p"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        img = block.select_one("img.prod_img")
        image_url = img.get("src") if img else None
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url  # 프로토콜 상대 URL

        gd_match = _GD_IDX_RE.search(str(block))
        gd_idx = gd_match.group(1) if gd_match else None

        barcode = _barcode_from_image(image_url)
        # ⚠️ 주키는 gd_idx다. 바코드가 아니다.
        # 전 카탈로그 5,082건 실측: gd_idx는 중복 0건, **바코드는 16건이 중복**(32항목).
        # 같은 물리적 제품이 CU 카탈로그에 두 번 등록돼 있고, 가격이 다른 경우도 있다:
        #     8801114153819  풀무원)나주식수육곰탕  8,000원 (gd=20181)
        #     8801114153819  풀무원)나주식수육곰탕  9,900원 (gd=24447)
        # 둘은 따로 보여줘야 하는 별개 항목이므로 id가 이를 구분할 수 있어야 한다.
        # 바코드는 '물리적 제품'을, gd_idx는 '카탈로그 항목'을 가리킨다. 우리가 발행하는
        # 단위는 카탈로그 항목이다. 바코드는 alt_ids에 남아 diff의 1순위 매칭 키로 쓰이고,
        # 나중에 편의점 4사 교차 대조에도 그대로 쓸 수 있다.
        external_id = gd_idx or barcode or _name_hash(name)

        items.append({
            "source_id": SOURCE_ID,
            "external_id": external_id,
            "alt_ids": {k: v for k, v in (("barcode", barcode), ("gd_idx", gd_idx)) if v},
            "name": name,
            "price": _parse_price(block.select_one("div.price > strong")),
            "category_raw": CATEGORIES[category_code],
            "image_url": image_url,
            "source_url": DETAIL_URL.format(gd_idx=gd_idx) if gd_idx else None,
            "scraped_at": scraped_at,
            # `_` 접두 키는 스냅샷 파일에 저장되지 않는다. 판정에 쓰지 않고 검증 대조군으로만 쓴다.
            "_labels": {
                "new": block.select_one("div.tag span.new") is not None,
                "best": block.select_one("div.tag span.best") is not None,
            },
        })

    return items, skipped


def has_next_page(markup: str) -> bool:
    """'더보기' 버튼이 있으면 다음 페이지가 있다."""
    return "prodListBtn-w" in markup


def parse_detail(markup: str) -> dict:
    """상세 페이지 → {name, description, tags}.

    목록 응답에 없는 두 가지가 여기 있다(실측, `cu_product_detail.html`):
        <dt>상품 설명</dt> <ul class="prodExplain"><li>…</li></ul>
        <dt>태그</dt>      <ul class="prodTag" id="taglist"><li>샐러드</li><li>간편식사</li></ul>
    ⚠️ `ul.prodTag`는 페이지에 두 번 나온다(제목 옆 빈 것 + 태그 목록). `#taglist`로 특정할 것.
    """
    soup = BeautifulSoup(markup, "html.parser")
    description = _clean_text(soup.select_one("ul.prodExplain li"))
    tags = [t for t in (_clean_text(li) for li in soup.select("ul#taglist li")) if t]
    return {
        "name": _clean_text(soup.select_one("p.tit")),
        "description": description,
        "tags": tags,
    }


def fetch_detail(session: base.Session, gd_idx: str, *, week: str) -> dict:
    """상품 1건의 상세 정보. diff가 걸러낸 신상에만 쓴다(전량 조회는 5,100요청이 된다)."""
    resp = session.get(DETAIL_URL.format(gd_idx=gd_idx))
    base.save_raw(week, SOURCE_ID, f"detail_{gd_idx}", resp.text, "html")
    return parse_detail(resp.text)


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    items: list[dict] = []
    previous_page_keys: set[str] | None = None

    for page in range(1, MAX_PAGES + 1):
        resp = session.post(
            LIST_URL,
            data={
                "pageIndex": str(page),
                "searchMainCategory": category_code,
                "searchSubCategory": "",
                "listType": "0",
                "searchCondition": "",
                "searchUseYn": "",
                "gdIdx": "0",
                "codeParent": category_code,
            },
            headers={
                "Referer": LIST_REFERER,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        markup = resp.text
        base.save_raw(week, SOURCE_ID, f"{category_code}_{page}", markup, "html")

        page_items, skipped = parse_list(markup, category_code, scraped_at=scraped_at)
        if skipped:
            raise ParseError(
                f"{CATEGORIES[category_code]} {page}페이지: 이름 없는 항목 {skipped}건. "
                "응답 구조가 바뀌었을 가능성이 높다."
            )

        page_keys = {i["external_id"] for i in page_items}
        if previous_page_keys is not None and page_keys and page_keys == previous_page_keys:
            raise ParseError(
                f"{CATEGORIES[category_code]} {page}페이지가 직전 페이지와 동일하다. "
                "페이지네이션이 전진하지 않는다."
            )
        previous_page_keys = page_keys

        items.extend(page_items)
        log.info("  %s(%s) %d페이지: %d건 (누적 %d)",
                 CATEGORIES[category_code], category_code, page, len(page_items), len(items))

        if len(page_items) < PAGE_SIZE or not has_next_page(markup):
            break
    else:
        raise ParseError(
            f"{CATEGORIES[category_code]}: {MAX_PAGES}페이지를 넘었다. 종료 조건이 안 먹는다."
        )

    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """CU 전체 카탈로그. CLAUDE.md 5장: 각 스크래퍼는 이 함수 하나를 노출한다.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4) —
    빠진 카테고리가 diff에서 통째로 '단종'으로 잡히기 때문이다.
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        log.info("수집: %s (%s)", CATEGORIES[code], code)
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("CU 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="CU 카탈로그 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    result = fetch(week=args.week, categories=args.category)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
