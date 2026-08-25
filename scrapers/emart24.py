"""이마트24 상품 카탈로그.

정찰 근거: `sources/targets.yml`의 emart24 항목, 골든 픽스처
`tests/fixtures/emart24_list_pl_p1.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://emart24.co.kr/goods/<코드>?page=<N>
  순수 서버 렌더링. 세션·토큰 불필요. 페이지당 20개 고정.
  ⚠️ `www.emart24.co.kr`은 302로 `emart24.co.kr`에 넘긴다. 정찰 기록의 `www.`는 틀렸다.
  robots.txt는 창업 문의 경로 둘(`/founded/brief/req`, `/founded/recommend`)만
  막는다 — `/goods/`는 **명시적으로 허용**된다.

★ **개별 상품 URL이 없는 첫 소스다**([ADR-0013](../docs/adr/0013-source-url-optional.md)).
목록의 상품 링크가 전부 `href="#none"`이라 `source_url`에 **목록 페이지 URL**을 넣는다.

이 소스에서 조심할 것:

  1. ⚠️ **안정적인 상품 키가 이미지 파일명뿐이다.** 응답에 id 필드가 없다.
     `https://msave.emart24.co.kr/.../500x500/8800323762973.JPG` 에서 바코드를 뽑는다.
     2026-08-25 실측 727건 전부에서 뽑혔다(누락 0건). 못 뽑으면 이름 해시로 떨어진다.
  2. ⚠️ **`ff`는 `pl`의 부분집합에 가깝다.** 2026-08-25 실측: pl 545 + ff 182 = 727건인데
     바코드 기준 고유는 **566건**이다. 157건이 양쪽에 실린다. 그래서 **바코드로
     중복을 제거**하고, `ff`를 먼저 긁어 그쪽 분류를 남긴다 — `ff`(Fresh Food)는
     실제 상품 분류이고 `pl`(차별화 상품)은 그것을 포함하는 넓은 개념이라,
     반대로 하면 `ff` 건수가 pl 목록 변동에 따라 크게 흔들린다.
  3. ⚠️ **같은 목록 안에서도 같은 상품이 두 번 나온다**(pl 545건 중 14건).
     바코드·이름·가격이 전부 같은 완전 동일 항목이라 앞의 것을 남긴다.
     **CU의 바코드 중복과는 성격이 정반대다** — 그쪽은 *다른* 상품이 같은 바코드를
     공유했다([ADR-0001](../docs/adr/0001-product-id.md)). 그래서 여기서는
     **가격이 다르면 예외를 던진다.** 가격은 상품을 가르는 신호다(`normalize.py`).
     이름만 다른 것은 허용한다 — 목록마다 자르는 길이가 다르다
     (`손종원_new뉴욕스타일베이컨샌드` vs `…베이컨샌드위치`, 실측 1건).
  4. **행사 상품(`/goods/event`, 2,314건)은 긁지 않는다.** 카탈로그가 아니라
     프로모션이고, 116요청이 더 든다. 매주 통째로 바뀌어 diff 노이즈가 크다.
     `/goods/special`(추석 선물 특선)도 시즌 기획이라 뺀다.
  5. **설명문이 목록에 없다** → `detail: False`. 상세 페이지 자체가 없으므로
     긁을 곳도 없다. `blurb`는 항상 `null`이다(6장).
  6. **소스의 신상 라벨이 있다.** `.itemTit span.floatL`에 `NEW` 텍스트가 늘 있고
     **`style="opacity: 0;"`으로 숨긴다.** 텍스트만 보면 전건이 신상이 된다.
     `_labels`에 담아 대조군으로만 쓴다 — 판정에는 쓰지 않는다(2.1).
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/emart24.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "emart24"
BASE_URL = "https://emart24.co.kr"
LIST_URL = f"{BASE_URL}/goods/{{code}}?page={{page}}"

# 경로 코드 → 사이트 네비게이션의 이름(실측). **순서가 의미를 갖는다** — 주의 2번대로
# 먼저 오는 쪽이 중복 항목의 분류를 가져간다.
CATEGORIES = {
    "ff": "Fresh Food",
    "pl": "차별화 상품",
}

# 2026-08-25 실측. 중복 제거 후 566건 / 38요청.
# `pl`은 목록상 545건이지만 그중 161건이 `ff`와 겹치거나 자기 안에서 중복이라
# 384건만 남는다. **첫 수집 때만 쓰는 부트스트랩 기준이다.**
BOOTSTRAP_COUNTS = {"ff": 182, "pl": 384}

PAGE_SIZE = 20          # 서버 고정. pageLength를 넘겨도 무시한다(정찰 기록).
MAX_PAGES = 50          # 폭주 방지. 최대(pl)가 28페이지였으므로 넉넉하다.

_BARCODE_RE = re.compile(r"/(\d{8,14})\.[A-Za-z]+$")
_PRICE_RE = re.compile(r"\d[\d,]*")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean_text(node) -> str | None:
    if node is None:
        return None
    text = html_mod.unescape(node.get_text(" ", strip=True))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_price(text: str | None) -> int | None:
    """`'3,200 원'` → `3200`. 숫자가 없으면 None."""
    if not text:
        return None
    match = _PRICE_RE.search(text)
    return int(match.group().replace(",", "")) if match else None


def parse_barcode(image_url: str | None) -> str | None:
    """이미지 파일명에서 바코드를 뽑는다 (주의 1번).

    `.../500x500/8800323762973.JPG` → `8800323762973`
    이 소스에서 상품 키를 얻는 **유일한 방법**이다.
    """
    if not image_url:
        return None
    match = _BARCODE_RE.search(image_url)
    return match.group(1) if match else None


def is_new(label_node) -> bool:
    """주의 6번 — `NEW` 텍스트는 늘 있고 `opacity: 0`으로 숨긴다.

    텍스트 유무로 판정하면 전건이 신상이 된다.
    """
    if label_node is None:
        return False
    style = (label_node.get("style") or "").replace(" ", "")
    return "opacity:0" not in style


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수)."""
    if code not in CATEGORIES:
        raise ValueError(f"모르는 경로 코드: {code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = soup.select("div.itemWrap")
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        name = _clean_text(block.select_one(".itemtitle p a"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        image = block.select_one(".itemSpImg img")
        image_url = image.get("src") if image else None
        barcode = parse_barcode(image_url)

        items.append({
            "source_id": SOURCE_ID,
            "external_id": barcode or _name_hash(name),
            "alt_ids": {"barcode": barcode} if barcode else {},
            "name": name,
            "price": parse_price(_clean_text(block.select_one("a.price"))),
            "category_raw": CATEGORIES[code],
            "description": None,              # 주의 5번: 설명문이 없다
            "tags": [],
            "image_url": image_url,
            # ADR-0013: 개별 상품 URL이 없어 목록 페이지를 가리킨다.
            "source_url": f"{BASE_URL}/goods/{code}",
            "scraped_at": scraped_at,
            # 주의 6번: 대조군으로만 쓴다 (2.1).
            "_labels": {"new": is_new(block.select_one(".itemTit span.floatL"))},
        })

    return items, skipped


def dedupe(items: list[dict]) -> list[dict]:
    """바코드가 같은 항목을 하나로 접는다 (주의 2번·3번).

    앞의 것을 남긴다 — `fetch`가 `ff`를 먼저 부르므로 Fresh Food 분류가 우선한다.

    ⚠️ **가격이 다르면 예외를 던진다.** 같은 바코드에 다른 가격이면 서로 다른
    상품일 수 있고(CU가 그랬다, ADR-0001), 그걸 조용히 접으면 한 상품이 사라진다.
    이름만 다른 것은 허용한다 — 목록마다 자르는 길이가 달라서다(실측 1건).
    """
    kept: dict[str, dict] = {}
    order: list[str] = []
    renamed = 0

    for item in items:
        key = item["external_id"]
        if key not in kept:
            kept[key] = item
            order.append(key)
            continue

        first = kept[key]
        if first["price"] != item["price"]:
            raise ParseError(
                f"같은 키({key})에 가격이 다르다: "
                f"{first['name']!r} {first['price']} vs {item['name']!r} {item['price']}. "
                "서로 다른 상품이 같은 바코드를 쓰고 있을 수 있다(ADR-0001)."
            )
        if first["name"] != item["name"]:
            renamed += 1
            log.info("  같은 키(%s)에 이름 표기가 다르다 — 앞의 것을 쓴다: %r / %r",
                     key, first["name"], item["name"])

    if renamed:
        log.info("  이름 표기만 다른 중복: %d건", renamed)
    log.info("  중복 제거: %d건 → %d건", len(items), len(order))
    return [kept[k] for k in order]


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_code(session: base.Session, code: str, *, week: str,
               scraped_at: str) -> list[dict]:
    """경로 하나를 페이지 끝까지. 빈 페이지가 오면 끝이다."""
    items: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        markup = session.get(LIST_URL.format(code=code, page=page)).text
        base.save_raw(week, SOURCE_ID, f"{code}_{page}", markup, "html")

        page_items, skipped = parse_list(markup, code, scraped_at=scraped_at)
        if skipped:
            raise ParseError(
                f"{CATEGORIES[code]}: 이름 없는 항목 {skipped}건. "
                "응답 구조가 바뀌었을 가능성이 높다."
            )
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < PAGE_SIZE:
            break
    else:
        raise ParseError(
            f"{CATEGORIES[code]}: {MAX_PAGES}페이지를 넘겼다. "
            "페이지네이션이 끝나지 않는다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[code], code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """이마트24 카탈로그. 2026-08-25 실측 566건 / 38요청 (중복 제거 후).

    ⚠️ 순서가 의미를 갖는다 — `ff`를 먼저 부른다(주의 2번).
    한 경로라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    raw: list[dict] = []
    for code in codes:
        raw.extend(fetch_code(session, code, week=week, scraped_at=scraped_at))

    items = dedupe(raw)
    log.info("이마트24 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="이마트24 상품 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="경로 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
