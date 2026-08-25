"""맥도날드 메뉴 카탈로그.

정찰 근거: `sources/targets.yml`의 mcdonalds 항목, 골든 픽스처
`tests/fixtures/mcdonalds_list_1.json`. 아래 수치는 전부 2026-08-25 실측이다.

  GET https://www.mcdonalds.co.kr/api/v1/kor/product/product/list
      ?page=1&view_rows=500&mainCategory=<코드>&subCategory=
  Nuxt SPA이지만 API가 같은 도메인에 인증 없이 열려 있다. robots.txt는 `Allow: /`.
  응답 봉투는 `{resultCode, resultMessage, resultObject:{totalCount, list}, isOk}`.

이 소스에서 조심할 것:

  1. ⚠️ **`mainCategory`를 비우면 전체가 오지 않는다.** 직전 조합 결과가 그대로 온다.
     반드시 카테고리를 순회한다.
  2. **`subCategory`는 비워도 된다.** 정찰 기록은 서브카테고리 순회가 필요하다고
     적었으나, 2026-08-25 실측에서 `mainCategory`만으로 그 카테고리 전량이 왔다
     (`totalCount`와 `len(list)`가 일치). 7요청이면 끝난다.
  3. ⚠️ **응답이 카테고리 이름을 주지 않는다**(`categoryName`이 `null`). 그래서
     `CATEGORIES`의 이름은 **사이트 메뉴 탭에서 읽어 우리가 붙인 것**이다.
  4. ⚠️⚠️ **제품명에 HTML 태그가 들어 있다** — `빅맥<sub class=reg>®</sub> 세트`.
     이것은 소스의 표기가 아니라 **마크업**이므로 벗긴다. BBQ의 `[NEW]`(순수 텍스트라
     그대로 둔다)와는 다른 경우다. 설명문(`korContent`)에도 `<br>\r\n`이 들어 있다.
  5. ⚠️ **카테고리 간에 같은 상품이 실린다.** 2026-08-25 실측: 110건 중 고유 `seq`는
     100개다(세트가 버거와 맥런치에 함께 실린다). **`seq`로 중복을 제거**하고,
     앞에 오는 카테고리가 분류를 가져간다.
  6. **가격 필드 자체가 없다.** `price`는 항상 `null`이다.
  7. ⚠️ **`regDate`가 `"2026-August-4th"` 형태다. 파싱하지 말 것.**
     신상 판정은 2.1의 차집합이 한다.
  8. **목록이 설명문을 준다**(`korContent`) → `detail: False`.
  9. 상세는 SPA라 서버 응답에 상품명이 없다. 2026-08-25에 브라우저로 열어
     정상 표시를 확인하고 `source_url`로 채택했다(홈플러스·BBQ와 같은 처리).
     경로는 `/kor/menu/detail/<seq>/<categorySeq>/<subCategorySeq>`.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/mcdonalds.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "mcdonalds"
BASE_URL = "https://www.mcdonalds.co.kr"
LIST_URL = (f"{BASE_URL}/api/v1/kor/product/product/list"
            "?page=1&view_rows=500&mainCategory={category}&subCategory=")
DETAIL_URL = f"{BASE_URL}/kor/menu/detail/{{seq}}/{{cat}}/{{sub}}"

# mainCategory 코드 → 이름. **응답이 이름을 주지 않아 사이트 탭에서 읽었다**(주의 3번).
# 순서가 의미를 갖는다 — 앞에 오는 카테고리가 중복 항목의 분류를 가져간다(주의 5번).
CATEGORIES = {
    "1": "버거",
    "2": "맥모닝",
    "3": "해피밀",
    "4": "사이드&디저트",
    "5": "맥카페&음료",
    "7": "맥런치",
    "8": "해피스낵",
}

# 2026-08-25 실측. 중복 제거 후 100건 / 7요청.
# **첫 수집 때만 쓰는 부트스트랩 기준이다** (`pipeline/snapshot.py` 참조).
BOOTSTRAP_COUNTS = {"1": 22, "2": 12, "3": 9, "4": 16, "5": 32, "7": 2, "8": 7}
# ⚠️ 위 값은 **중복 제거 뒤** 분류가 확정된 건수다. 목록상으로는 사이드&디저트 19,
#    맥런치 9건이지만 그중 3건·7건이 앞 카테고리에 이미 실려 있다(주의 5번).

_TAG_RE = re.compile(r"<[^>]+>")


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 부분 수집은 실패다 (2.4)."""


def strip_markup(value) -> str | None:
    """HTML 태그를 벗기고 공백을 접는다 (주의 4번).

    `'빅맥<sub class=reg>®</sub> 세트'` → `'빅맥® 세트'`
    `'매콤 새콤한<br>\\r\\n크림치즈 소스'` → `'매콤 새콤한 크림치즈 소스'`

    **기호(®·™)는 남긴다.** 그것은 마크업이 아니라 이름의 일부이고,
    동일성 판정은 `pipeline/normalize.py`의 NFKC가 접는다.
    """
    if value is None:
        return None
    text = _TAG_RE.sub(" ", str(value))
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE_URL + url


# ── 파싱 (네트워크와 분리한다. 골든 테스트가 여기를 친다) ──────────────


def parse_list(payload: dict, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 JSON → (스냅샷 항목들, 이름이 없어 건너뛴 개수)."""
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")
    if not isinstance(payload, dict) or "resultObject" not in payload:
        raise ParseError(
            f"카테고리 {category_code}: 응답에 resultObject가 없다. "
            f"봉투 구조가 바뀌었을 가능성이 높다: {sorted(payload) if isinstance(payload, dict) else type(payload)}")

    envelope = payload["resultObject"] or {}
    rows = envelope.get("list") or []
    items: list[dict] = []
    skipped = 0

    for row in rows:
        name = strip_markup(row.get("korName"))
        if not name:
            skipped += 1
            log.warning("이름이 없는 항목을 건너뛴다: seq=%s", row.get("seq"))
            continue

        seq = row.get("seq")
        cat = row.get("categorySeq") or category_code
        sub = row.get("subCategorySeq") or 1

        items.append({
            "source_id": SOURCE_ID,
            "external_id": str(seq) if seq else _name_hash(name),
            "alt_ids": {"seq": str(seq)} if seq else {},
            "name": name,
            "price": None,                    # 주의 6번: 가격 필드가 없다
            "category_raw": CATEGORIES[category_code],
            # 주의 8번: 목록이 설명문을 준다. enrich는 이 소스를 건너뛴다.
            "description": strip_markup(row.get("korContent")),
            "tags": [],                       # 소스가 태그를 주지 않는다
            "image_url": _absolute(row.get("pcImageUrl") or row.get("pcListImageUrl")),
            # 주의 9번: SPA다. 브라우저에서만 렌더링된다(2026-08-25 확인).
            "source_url": (DETAIL_URL.format(seq=seq, cat=cat, sub=sub) if seq else None),
            "scraped_at": scraped_at,
            # `newIcon`은 2026-08-25 실측에서 110건 전부 빈 문자열이었다.
            # 대조군으로만 보낸다 — 판정에는 쓰지 않는다 (2.1).
            "_labels": {"new": bool((row.get("newIcon") or "").strip())},
        })

    return items, skipped


def dedupe(items: list[dict]) -> list[dict]:
    """같은 `seq`를 하나로 접는다 (주의 5번).

    앞의 것을 남긴다 — `CATEGORIES` 순서가 분류 우선순위다.
    ⚠️ **이름이 다르면 예외를 던진다.** 같은 seq에 다른 이름이면 키가 상품을
    가리키지 않는다는 뜻이라, 조용히 접으면 한 상품이 사라진다.
    """
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
                f"같은 seq({key})에 이름이 다르다: {first['name']!r} vs {item['name']!r}. "
                "seq가 상품을 가리키지 않는다.")
    log.info("  중복 제거: %d건 → %d건", len(items), len(order))
    return [kept[k] for k in order]


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    resp = session.get(LIST_URL.format(category=category_code))
    base.save_raw(week, SOURCE_ID, category_code, resp.text, "json")

    items, skipped = parse_list(resp.json(), category_code, scraped_at=scraped_at)
    if skipped:
        raise ParseError(
            f"{CATEGORIES[category_code]}: 이름 없는 항목 {skipped}건. "
            "응답 구조가 바뀌었을 가능성이 높다."
        )

    log.info("  %s(%s): %d건", CATEGORIES[category_code], category_code, len(items))
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """맥도날드 전체 카탈로그. 2026-08-25 실측 100건 / 7요청 (중복 제거 후).

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
    log.info("맥도날드 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="맥도날드 메뉴 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="mainCategory 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(fetch(week=args.week, categories=args.category),
                     ensure_ascii=False, indent=2))
