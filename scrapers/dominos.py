"""도미노피자 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 dominos 항목, 골든 픽스처
`tests/fixtures/dominos_list_C0101.html`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://web.dominos.co.kr/goods/list?dsp_ctgr=<코드>
  서버 렌더링. 세션·토큰 불필요. 페이지네이션 없음.
  robots.txt가 `/goods/`와 `/bbs/`를 **명시적으로 허용**한다.
  ⚠️ `www.dominos.co.kr` → `web.dominos.co.kr/gate` → `/main` 2단 리다이렉트.

이 소스에서 조심할 것:

  1. ⚠️⚠️ **인코딩이 EUC-KR이다.** 이 프로젝트에서 유일하다.
     `resp.encoding`을 명시하지 않으면 제품명이 전부 깨진다. robots.txt까지 EUC-KR이다.
  2. ⚠️⚠️ **제품명에 라벨이 섞여 나온다.** `div.subject` 안에 `div.label-box`가
     들어 있어 `get_text()`를 그대로 쓰면 `치즈폴레 무슈스기간한정NEW`가 된다.
     **`label-box`를 떼고 남은 텍스트가 이름이고, 뗀 라벨은 `_labels`로 보낸다.**
     BBQ는 `[NEW]`가 이름 문자열 자체에 박혀 있어 뗄 수 없었지만(그래서 원문을 그대로
     둔다), 여기는 마크업이 분리돼 있어 정확히 가를 수 있다.
  3. ⚠️ **상품 코드가 네 군데에 흩어져 있다.** 피자는 `<a href="detail?...&code_01=">`,
     사이드 일부는 `getDetailSlide('SST798F1', ...)`, 음료는 `addGoods('RDK001L6')`,
     세트는 `addSideDish(...)`. 네 패턴을 다 봐야 전건에서 키가 나온다
     (2026-08-25 실측: 54/54).
  4. ⚠️ **이미지가 lazyload다.** `src`는 플레이스홀더 `bg.gif`이므로 **`data-src`**를 읽는다.
  5. ⚠️ **가격이 범위 표기다** — `L 36,900원~ / M 30,000원~`.
     **`M` 사이즈의 값을 `price`로 쓴다**(2026-08-25 결정). `~`가 "부터"이므로
     최저가로서 정확하고, 둘 중 작은 값이라 방문자가 본 가격보다 비쌀 일이 없다.
     M이 없으면 L을, 둘 다 없으면 `null`을 쓴다. **diff도 이 값으로 돈다.**
  6. ⚠️ **`div.hashtag`는 태그가 아니다.** 실측하니 마케팅 문구였다
     (`#No.1 패션 플랫폼 무신사와 No.1 피자 도미노가 만났다!`). 4장의 `tags`는
     소스가 준 *분류어*를 담는 자리이므로 여기 넣지 않고, **`description`으로 쓴다** —
     제품을 설명하는 문장이 맞고, 이 소스에는 다른 설명문이 없다.
  7. **상세 URL이 항목마다 있기도 없기도 하다**(실측 36/54). 피자는 `detail?...`가
     있고 음료·일부 사이드는 모달이라 없다. 없으면 **카테고리 목록 URL**을 쓴다
     ([ADR-0013](../docs/adr/0013-source-url-optional.md) 2층). 한 소스 안에서
     1층과 2층이 섞이는 첫 사례다.
  8. 같은 상품이 신제품 섹션과 일반 섹션에 두 번 실린다(실측 4건). 코드로 접는다.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__ in (None, ""):  # `python scrapers/dominos.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "dominos"
BASE_URL = "https://web.dominos.co.kr"
LIST_URL = f"{BASE_URL}/goods/list?dsp_ctgr={{code}}"

# `dsp_ctgr` 코드 → 사이트 탭 이름. 목록 페이지 네비게이션에서 실측했다.
# 정찰 기록은 "`/main`에서 전체 코드를 추가로 긁어야 한다"고 했으나 셋이 전부다.
CATEGORIES = {
    "C0101": "메뉴",
    "C0201": "사이드디시",
    "C0202": "음료&기타",
}

# 2026-08-25 실측. 중복 제거 후 50건 / 3요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"C0101": 23, "C0201": 13, "C0202": 14}

ENCODING = "euc-kr"          # 주의 1번

# 주의 3번: 네 패턴 전부를 본다.
_CODE_RE = re.compile(
    r"(?:code_01=|getDetailSlide\('|addGoods\('|addSideDish\(')([A-Z0-9]{6,12})")
_PRICE_RE = re.compile(r"\d[\d,]*")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", html_mod.unescape(text)).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_price(price_nodes) -> int | None:
    """`['L 36,900원~', 'M 30,000원~']` → `30000` (주의 5번).

    M을 우선하고, 없으면 L, 둘 다 없으면 None.
    """
    found: dict[str, int] = {}
    for node in price_nodes:
        text = node.get_text(" ", strip=True)
        size = "M" if node.select_one(".size_m") else ("L" if node.select_one(".size_l") else "")
        match = _PRICE_RE.search(text.replace(size, "", 1) if size else text)
        if match:
            found[size or "?"] = int(match.group().replace(",", ""))
    for key in ("M", "L", "?"):
        if key in found:
            return found[key]
    return None


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(markup: str, code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 HTML → (스냅샷 항목들, 이름이 없어 건너뛴 블록 수).

    ⚠️ `markup`은 **이미 EUC-KR에서 디코딩된 문자열**이어야 한다(주의 1번).
    """
    if code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {code!r}")

    soup = BeautifulSoup(markup, "html.parser")
    blocks = [li for li in soup.select("li") if li.select_one("div.subject")]
    items: list[dict] = []
    skipped = 0

    for block in blocks:
        subject = block.select_one("div.subject")
        # 주의 2번: 라벨을 떼어내야 이름이 온전해진다.
        label_box = subject.select_one("div.label-box")
        labels = ([_clean(x.get_text(strip=True)) for x in label_box.select("span.label")]
                  if label_box else [])
        labels = [x for x in labels if x]
        if label_box:
            label_box.extract()

        name = _clean(subject.get_text(" ", strip=True))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: %s", str(block)[:200])
            continue

        # 주의 3번: 링크와 onclick을 모두 훑는다.
        blob = " ".join((a.get("href") or "") + (a.get("onclick") or "")
                        for a in block.select("a"))
        match = _CODE_RE.search(blob)
        product_code = match.group(1) if match else None

        detail = block.select_one("a[href*='code_01=']")
        image = block.select_one("img.lazyload") or block.select_one("img")

        items.append({
            "source_id": SOURCE_ID,
            "external_id": product_code or _name_hash(name),
            "alt_ids": {"code_01": product_code} if product_code else {},
            "name": name,
            "price": parse_price(block.select("div.price-box span.price")),
            "category_raw": CATEGORIES[code],
            # 주의 6번: 해시태그는 분류어가 아니라 제품 설명이다.
            "description": _clean(
                (block.select_one("div.hashtag").get_text(" ", strip=True)
                 if block.select_one("div.hashtag") else None)),
            "tags": [],
            # 주의 4번: lazyload라 src는 플레이스홀더다.
            "image_url": _clean(image.get("data-src") if image else None),
            # 주의 7번: 상세가 있으면 그것, 없으면 목록 URL (ADR-0013).
            "source_url": (f"{BASE_URL}/goods/{detail.get('href').lstrip('/')}"
                           if detail and detail.get("href")
                           else LIST_URL.format(code=code)),
            "scraped_at": scraped_at,
            # 주의 2번에서 떼어낸 라벨. 대조군으로만 쓴다 (2.1).
            "_labels": {"new": "NEW" in labels, "badges": labels},
        })

    return items, skipped


def dedupe(items: list[dict]) -> list[dict]:
    """같은 상품 코드를 하나로 접는다 (주의 8번). 앞의 것을 남긴다."""
    kept: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        key = item["external_id"]
        if key not in kept:
            kept[key] = item
            order.append(key)
            continue
        first = kept[key]
        if first["name"] != item["name"]:
            raise ParseError(
                f"같은 코드({key})에 이름이 다르다: "
                f"{first['name']!r} vs {item['name']!r}.")
    log.info("  중복 제거: %d건 → %d건", len(items), len(order))
    return [kept[k] for k in order]


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    resp = session.get(LIST_URL.format(code=code))
    resp.encoding = ENCODING          # 주의 1번. 이 한 줄이 없으면 전부 깨진다
    markup = resp.text
    base.save_raw(week, SOURCE_ID, code, markup, "html")

    items, skipped = parse_list(markup, code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[code], code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """도미노 전체 카탈로그. 2026-08-25 실측 50건 / 3요청 (중복 제거 후).

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    raw: list[dict] = []
    for code in codes:
        raw.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    items = dedupe(raw)
    log.info("도미노 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="도미노 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="dsp_ctgr 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
