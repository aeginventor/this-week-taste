"""홈플러스 온라인몰 식품 카탈로그.

정찰 근거: `docs/RECON_mart_fmcg.md`, `sources/targets.yml`의 homeplus 항목,
골든 픽스처 `tests/fixtures/homeplus_list_200095.json`.

  GET https://mfront.homeplus.co.kr/category/item.json
      ?categoryDepth=2&categoryId=<M 코드>&page=<n>&perPage=100&sort=RANK
  JSON. 세션·토큰·storeId 불필요. robots.txt는 `/favorite`, `/mypage`만 막는다.

**이것은 온라인 배송 가능 품목의 카탈로그이지 오프라인 매장 카탈로그가 아니다.**
신선식품은 사실상 비어 있고 가공식품만 채워져 있다.

이 소스에서 조심할 것 (2026-08-12~13 실측):

  1. **`sort=RANK`가 없으면 HTTP 200 + SUCCESS + totalCount 0이 온다.** 무음 실패다.
     `categoryDepth`도 항상 2여야 하고, `categoryId`는 반드시 M 레벨 코드(2xxxxx)다.
     L 레벨 코드나 다른 depth를 넣어도 똑같이 조용히 0건이 온다.
     그래서 `fetch_category()`가 0건을 그냥 넘기지 않고 기대치와 대조한다.
  2. **상세 페이지 URL은 `storeId`가 아니라 `storeType`을 받는다.**
     `?itemNo=…&storeId=37`은 "현재 판매중인 상품이 아닙니다" 껍데기(9.5KB)를 준다.
     이전 정찰이 상세를 클라이언트 렌더링이라고 판단한 것은 이 오해 때문이었다.
     `storeType`을 주면 108KB짜리 서버 렌더링 문서가 온다.
  3. **설명문이 사실상 없다.** 상세 응답의 `itemDesc`는 거의 전부 `<img>` 한 줄이다
     (표본 51건 중 텍스트 설명은 1건). 그래서 이 소스는 `enrich`를 붙이지 않는다.
     스타벅스가 "목록이 이미 다 줘서" 건너뛰는 것과 이유가 정반대다.
     `description`은 항상 `None`이고, 따라서 `blurb`도 `null`로 발행된다 (6장).
  4. **이미지 URL은 응답에 없고 `itemNo`에서 만든다.** `imgChgDt`·`imgDispYn`만 온다.
     `https://image.homeplus.kr/it/<itemNo>s0640` 규칙을 실측으로 확인했다.
     ⚠️ 없는 itemNo도 HTTP 404가 아니라 200 + 플레이스홀더 이미지를 준다.
     그래서 상태 코드로는 존재 여부를 알 수 없고, `imgDispYn`이 유일한 근거다.
  5. **소스에 신상 라벨이 없다.** `labelList`는 비어 있고 `itemType`은 전 항목 "N"이다.
     즉 이 소스는 CLAUDE.md 8장의 `source_new_label` 채점표를 만들 수 없다.
     diff 품질은 다른 소스로 재야 한다.
  6. **`brandNm`은 전 항목 null이다.** PB(홈플러스시그니처·심플러스)는 `itemNm`
     접두사로만 알 수 있다. 지금은 쓰지 않는다.
  7. 가격은 **정가(`salePrice`)를 쓴다.** `dcPrice`는 행사가라 매주 바뀌고,
     그걸 넣으면 diff의 `changed`가 할인 시작·종료로 가득 찬다.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python scrapers/homeplus.py` 로도 돌게 한다
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import weeks
from scrapers import base

log = logging.getLogger(__name__)

SOURCE_ID = "homeplus"
BASE_URL = "https://mfront.homeplus.co.kr"
LIST_URL = (f"{BASE_URL}/category/item.json"
            "?categoryDepth=2&categoryId={category}&page={page}&perPage={per_page}&sort=RANK")
DETAIL_URL = f"{BASE_URL}/item?itemNo={{item_no}}&storeType={{store_type}}"
IMAGE_URL = "https://image.homeplus.kr/it/{item_no}s0640"

PER_PAGE = 100  # 실측 상한. 200 이상은 HTTP 500이다.

# M 레벨 카테고리 코드 → `<R 이름> > <M 이름>`.
#
# 트리는 `GET /category/mobile/getMap.json` 1회로 얻는다: R(22) → L(19) → M. **M이 리프다.**
# 그중 식품 계열 R 17개 아래의 M 리프를 2026-08-13에 받아 적었다.
# 라벨을 `R > M`으로 잡은 이유는 **127개 전부 유일하기 때문**이다. 이 유일성이
# `snapshot.py`의 카테고리별 건수 검증(이름 → 코드 역매핑)이 성립하는 근거다.
# L을 빼도 되는 것은 R과 L이 거의 같은 이름이라서다(다른 경우: 채소 > 친환경/유기농).
#
# ⚠️ `건강식품` R 아래의 마사지·치아관리·한방/의료용품과 의약외품 4개는 **뺐다.**
#    식음료가 아니다. 넣으면 curate가 전부 `기타`로 떨궈 발행물만 지저분해진다.
#
# ⚠️ 2026-08-24에 **신선 원물 5개 R을 더 뺐다** — 과일·채소·정육/계란·수산물/건어물·쌀/잡곡
#    (123 → 75개, 130 → 약 80요청). 우리가 모으는 것은 **식품류 공산품**이고
#    신선식품은 매주 "신상"이 도는 성격이 아니다. 같은 이유로 CU도 생활용품을 뺐다.
#    범위를 넓히기로 하면 그때 다시 붙인다.
CATEGORIES = {
    # 견과
    "200034": "견과 > 곡물가공/건강분말",
    "200035": "견과 > 믹스넛/하루견과",
    "200036": "견과 > 브라질넛/마카다미아",
    "200037": "견과 > 선물세트",
    "200038": "견과 > 씨앗/잣/견과스낵",
    "200039": "견과 > 아몬드/호두/땅콩",
    "200040": "견과 > 캐슈넛/피스타치오",
    # 델리/치킨/초밥
    "200117": "델리/치킨/초밥 > 초밥/김밥",
    "200118": "델리/치킨/초밥 > 치킨/튀김/구이",
    "200116": "델리/치킨/초밥 > 샌드위치/사이드메뉴",
    # 우유/유제품
    "200059": "우유/유제품 > 우유",
    "200058": "우유/유제품 > 요거트/요구르트",
    "200060": "우유/유제품 > 치즈/버터",
    "200056": "우유/유제품 > 냉장디저트/음료",
    "200057": "우유/유제품 > 두유",
    # 냉장/냉동
    "200669": "냉장/냉동 > 피자/핫도그/치킨",
    "200070": "냉장/냉동 > 돈까스/떡갈비/너겟",
    "200670": "냉장/냉동 > 떡볶이/면류",
    "200071": "냉장/냉동 > 밀키트",
    "200671": "냉장/냉동 > 전/볶음/국탕",
    "200069": "냉장/냉동 > 냉동밥/죽/스프",
    "200072": "냉장/냉동 > 만두",
    "200097": "냉장/냉동 > 아이스크림/디저트/얼음",
    # 두부/김치/반찬
    "200063": "두부/김치/반찬 > 두부/나물",
    "200061": "두부/김치/반찬 > 김치",
    "200062": "두부/김치/반찬 > 냉장소스/냉장장류",
    "200064": "두부/김치/반찬 > 반찬/젓갈",
    "200068": "두부/김치/반찬 > 햄/소시지",
    "200066": "두부/김치/반찬 > 어묵/맛살/단무지",
    "200067": "두부/김치/반찬 > 유부초밥/김밥재료",
    # 커피/차
    "200114": "커피/차 > 커피믹스",
    "200110": "커피/차 > 원두커피/캡슐커피",
    "200108": "커피/차 > 드립백/더치커피",
    "200106": "커피/차 > 커피음료",
    "200107": "커피/차 > 녹차/보리차/기타차",
    "200111": "커피/차 > 전통차/액상차/꿀",
    "200115": "커피/차 > 코코아/핫초코",
    # 생수/음료
    "200100": "생수/음료 > 생수/탄산수",
    "200104": "생수/음료 > 과일/야채음료",
    "200105": "생수/음료 > 탄산/이온/비타민음료",
    "200102": "생수/음료 > 전통/차/기타음료",
    "200103": "생수/음료 > 전통주",
    # 과자/시리얼
    "200095": "과자/시리얼 > 과자/쿠키/파이",
    "200127": "과자/시리얼 > 떡/한과/전통과자",
    "200098": "과자/시리얼 > 시리얼/간식류소시지",
    "200099": "과자/시리얼 > 초콜릿/캔디/젤리/껌",
    # 베이커리/잼
    "200123": "베이커리/잼 > 식빵/모닝롤/베이글",
    "200126": "베이커리/잼 > 케이크/머핀/쿠키",
    "200122": "베이커리/잼 > 베이커리생지/냉동생지",
    "200682": "베이커리/잼 > 디저트빵",
    "200124": "베이커리/잼 > 기타 빵류",
    "200125": "베이커리/잼 > 잼/스프레드",
    # 라면/즉석식품/통조림
    "200091": "라면/즉석식품/통조림 > 라면/수입면류",
    "200089": "라면/즉석식품/통조림 > 당면/건면/스파게티",
    "200093": "라면/즉석식품/통조림 > 즉석식품/누룽지/죽",
    "200094": "라면/즉석식품/통조림 > 카레/짜장",
    "200092": "라면/즉석식품/통조림 > 참치/스팸/축수산통조림",
    "200090": "라면/즉석식품/통조림 > 옥수수/피클/과일통조림",
    # 장류/양념/제빵
    "200074": "장류/양념/제빵 > 고추장/된장/쌈장/간장",
    "200081": "장류/양념/제빵 > 소스",
    "200661": "장류/양념/제빵 > 케찹/마요네즈",
    "200077": "장류/양념/제빵 > 밀가루/분말류",
    "200078": "장류/양념/제빵 > 소금/설탕",
    "200073": "장류/양념/제빵 > 고추가루/깨/향신료",
    "200076": "장류/양념/제빵 > 다시다/미원/맛소금",
    "200080": "장류/양념/제빵 > 식초/물엿/맛술/액젓",
    "200079": "장류/양념/제빵 > 식용유/참기름",
    "200082": "장류/양념/제빵 > 시럽/제빵믹스",
    # 건강식품 (식음료가 아닌 M 4개는 위 주석대로 제외했다)
    "200663": "건강식품 > 비타민/프로폴리스/혈행개선제",
    "200665": "건강식품 > 유산균",
    "200666": "건강식품 > 콜라겐/다이어트/프로틴",
    "200662": "건강식품 > 루테인/밀크씨슬/관절",
    "200667": "건강식품 > 홍삼/녹용",
    "200664": "건강식품 > 소화제/자양강장/숙취해소",
    "200668": "건강식품 > 기타 건강식품",
}

# 2026-08-13 실측. 총 2,966건 / 130요청 / 약 2분. **첫 수집 때만 쓰는 부트스트랩 기준이다**
# (`pipeline/snapshot.py` 참조). 직전 주 스냅샷이 생기면 그쪽이 언제나 기준이 된다.
#
# 0건인 카테고리가 있다. **온라인 배송 가능 품목만 노출되기 때문이지 수집이 실패한
# 것이 아니다.** 기대치 0은 검사에서 건너뛰므로 오탐을 내지 않는다.
# (신선 원물 R을 뺀 뒤로 0건 카테고리는 크게 줄었다 — 대부분 거기 몰려 있었다.)
BOOTSTRAP_COUNTS = {
    # 견과
    "200034": 12, "200035": 2, "200036": 1, "200037": 0, "200038": 1,
    "200039": 9, "200040": 3,
    # 델리/치킨/초밥
    "200117": 7, "200118": 5, "200116": 4,
    # 우유/유제품
    "200059": 126, "200058": 152, "200060": 167, "200056": 141, "200057": 13,
    # 냉장/냉동
    "200669": 81, "200070": 50, "200670": 119, "200071": 62, "200671": 80,
    "200069": 35, "200072": 75, "200097": 35,
    # 두부/김치/반찬
    "200063": 84, "200061": 67, "200062": 35, "200064": 42, "200068": 120,
    "200066": 91, "200067": 27,
    # 커피/차
    "200114": 15, "200110": 6, "200108": 2, "200106": 6, "200107": 32,
    "200111": 26, "200115": 13,
    # 생수/음료
    "200100": 7, "200104": 14, "200105": 19, "200102": 8, "200103": 0,
    # 과자/시리얼
    "200095": 169, "200127": 0, "200098": 21, "200099": 56,
    # 베이커리/잼
    "200123": 15, "200126": 12, "200122": 5, "200682": 8, "200124": 15, "200125": 11,
    # 라면/즉석식품/통조림
    "200091": 86, "200089": 24, "200093": 64, "200094": 19, "200092": 22, "200090": 8,
    # 장류/양념/제빵
    "200074": 25, "200081": 71, "200661": 8, "200077": 13, "200078": 17,
    "200073": 15, "200076": 14, "200080": 17, "200079": 18, "200082": 13,
    # 건강식품
    "200663": 1, "200665": 0, "200666": 4, "200662": 0, "200667": 0,
    "200664": 7, "200668": 0,
}


class ParseError(RuntimeError):
    """응답 구조가 예상과 다르다. 사이트가 바뀌었다는 뜻이므로 조용히 넘기지 않는다."""


# ── 파싱 (네트워크 없이 단독으로 검증 가능하게 분리) ──────────────────


def _name_hash(name: str) -> str:
    return "nh" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _category_label(row: dict, category_code: str) -> str:
    """`<R 이름> > <M 이름>`. 응답이 이름을 주므로 원문을 쓴다 (CLAUDE.md 4장).

    응답 값이 `CATEGORIES`와 어긋나면 예외를 던진다. 어긋난다는 것은 소스가
    카테고리를 개편했다는 뜻이고, 그대로 두면 `snapshot.py`의 건수 검증이
    "기준에 없던 카테고리"로만 흘려보내 조용히 지나간다.
    """
    label = f"{(row.get('rcateNm') or '').strip()} > {(row.get('mcateNm') or '').strip()}"
    expected = CATEGORIES[category_code]
    if label != expected:
        raise ParseError(
            f"카테고리 {category_code}: 응답이 {label!r}인데 기대는 {expected!r}. "
            "소스가 카테고리 트리를 바꿨을 가능성이 높다. "
            "getMap.json을 다시 떠서 CATEGORIES를 갱신할 것."
        )
    return expected


def parse_list(payload: dict, category_code: str, *, scraped_at: str) -> tuple[list[dict], int]:
    """목록 JSON → (스냅샷 항목들, 총 페이지 수).

    `returnCode`가 SUCCESS여도 내용이 비어 있을 수 있다(주의 1번). 건수 판단은
    호출자가 한다. 여기서는 구조만 본다.
    """
    if category_code not in CATEGORIES:
        raise ValueError(f"모르는 카테고리 코드: {category_code!r}")
    if payload.get("returnCode") != "SUCCESS":
        raise ParseError(f"returnCode가 SUCCESS가 아니다: {payload.get('returnCode')!r}")

    data = payload.get("data")
    if not isinstance(data, dict) or "dataList" not in data:
        raise ParseError("data.dataList가 없다. 응답 구조가 바뀌었다.")

    total_page = (payload.get("pagination") or {}).get("totalPage") or 1
    items: list[dict] = []

    for row in data["dataList"]:
        name = (row.get("itemNm") or "").strip()
        if not name:
            raise ParseError(f"itemNm이 없는 항목: {str(row)[:200]}")

        item_no = row.get("itemNo")
        # 이미지는 itemNo로 만든다. 없는 itemNo도 200을 주므로(주의 4번)
        # imgDispYn이 "이 상품에 이미지가 있는가"의 유일한 근거다.
        image_url = (IMAGE_URL.format(item_no=item_no)
                     if item_no and row.get("imgDispYn") == "Y" else None)
        store_type = row.get("storeType") or "HYPER"

        items.append({
            "source_id": SOURCE_ID,
            # itemNo가 주키다. 카탈로그 전체에서 유일한지는 fetch()가 매번 검사한다.
            "external_id": item_no or _name_hash(name),
            "alt_ids": {},          # 두 번째 안정적 키가 없다. docId는 itemNo를 품고 있어 독립적이지 않다
            "name": name,           # CU와 달리 절삭되지 않는다
            "price": row.get("salePrice"),   # 정가. 행사가(dcPrice)가 아니다 (주의 7번)
            "category_raw": _category_label(row, category_code),
            "description": None,    # 상세에도 없다. enrich를 붙이지 않는다 (주의 3번)
            "image_url": image_url,
            "source_url": (DETAIL_URL.format(item_no=item_no, store_type=store_type)
                           if item_no else None),
            "scraped_at": scraped_at,
        })

    return items, total_page


# ── 수집 ─────────────────────────────────────────────────────────


def fetch_category(session: base.Session, category_code: str, *, week: str,
                   scraped_at: str) -> list[dict]:
    """카테고리 하나를 끝까지. 페이지가 여럿이면 전부 돈다."""
    items: list[dict] = []
    page = 1
    total_page = 1

    while page <= total_page:
        url = LIST_URL.format(category=category_code, page=page, per_page=PER_PAGE)
        resp = session.get(url)
        base.save_raw(week, SOURCE_ID, f"{category_code}_{page}", resp.text, "json")

        page_items, total_page = parse_list(resp.json(), category_code, scraped_at=scraped_at)
        items.extend(page_items)
        page += 1

    log.info("  %s(%s): %d건 / %d페이지",
             CATEGORIES[category_code], category_code, len(items), total_page)
    return items


def fetch(*, week: str | None = None, categories: list[str] | None = None) -> list[dict]:
    """홈플러스 식품 카탈로그 전체.

    한 카테고리라도 실패하면 예외를 위로 던진다. 부분 수집은 실패다 (2.4).
    """
    week = week or weeks.current_week()
    codes = categories or list(CATEGORIES)
    scraped_at = weeks.scraped_at()
    session = base.Session()

    items: list[dict] = []
    for code in codes:
        items.extend(fetch_category(session, code, week=week, scraped_at=scraped_at))

    log.info("홈플러스 총 %d건 / %d요청", len(items), session.request_count)
    return items


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="홈플러스 카탈로그 수집 (stdout으로 JSON 출력)")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                        help="M 레벨 카테고리 코드. 반복 지정 가능. 생략하면 전체")
    parser.add_argument("--week", help="원본 저장 주차. 생략하면 이번 주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    result = fetch(week=args.week, categories=args.category)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
