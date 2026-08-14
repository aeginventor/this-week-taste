"""소스별 값을 담는 표. **CLAUDE.md 7장이 허용하는 '표 하나'가 여기다.**

7장은 소스 고유 어휘가 `pipeline/`에 새는 것을 금지하면서, 소스별 값을 담는 표
하나는 예외로 둔다. 그런데 그 표가 `snapshot.py`·`enrich.py`·`publish.py`에
하나씩 흩어져 있었다. 4개째 소스를 붙이기 전에 한 곳으로 모은다.

**여기에 들어오는 것과 안 들어오는 것**

  들어온다   소스마다 답이 다른 *사실* — 브랜드명, 채널, 상세 페이지 유무,
             단조 증가 키 이름. 파이프라인이 소스를 몰라도 되게 하는 값들이다.
  안 들어온다 소스의 *내용* — 카테고리 코드, 부트스트랩 건수, 파싱 규칙.
             그것은 해당 스크래퍼 파일이 갖는다. 여기로 옮기면 이 파일이
             소스 4개의 사정을 전부 아는 두 번째 하드코딩 더미가 된다.

스크래퍼 모듈은 `scrapers/<source_id>.py`로 찾는다. 이 규칙이 3장의 "소스별 파일
1개"와 같은 규칙이라 따로 표를 둘 필요가 없다.
"""

from __future__ import annotations

import importlib
from types import ModuleType

# source_id → 파이프라인이 알아야 하는 값들.
#
#   brand / channel   발행물에 그대로 실린다 (4장). channel은
#                     mart|convenience|cafe|dessert|restaurant|fmcg 중 하나.
#   detail            상세 페이지를 긁을 값어치가 있는가. `enrich.py`가 본다.
#   monotonic_key     단조 증가하는 정수 키의 `alt_ids` 이름. 없으면 None.
#                     `publish.py`의 오탐 지표가 이 키가 있는 소스에만 실린다.
SOURCES: dict[str, dict] = {
    "cu": {
        "brand": "CU",
        "channel": "convenience",
        # 목록이 이름·가격까지만 준다. 설명문과 태그는 상세에만 있다.
        "detail": True,
        # gd_idx는 자동 증가라 "신상은 지난주 최댓값보다 크다"가 성립한다.
        "monotonic_key": "gd_idx",
    },
    "orion": {
        "brand": "오리온",
        "channel": "fmcg",
        "detail": True,
        # goodsno도 정수지만 목록이 오름차순이 아니라 확인이 더 필요하다.
        # 확인되지 않은 소스는 넣지 않는다 — 틀린 지표는 없는 지표보다 나쁘다.
        "monotonic_key": None,
    },
    "starbucks": {
        "brand": "스타벅스",
        "channel": "cafe",
        # 목록이 326/326 전부에 설명문을 준다. 이미 가진 것을 버리고 다시 긁지 않는다.
        "detail": False,
        # product_cd는 13자리 상품코드라 증가 순서가 아니다.
        "monotonic_key": None,
    },
}


def known() -> list[str]:
    return list(SOURCES)


def meta(source_id: str) -> dict:
    try:
        return SOURCES[source_id]
    except KeyError:
        raise ValueError(
            f"모르는 소스: {source_id!r}. 등록된 소스: {', '.join(SOURCES)}"
        ) from None


def scraper(source_id: str) -> ModuleType:
    """`scrapers/<source_id>.py`를 불러온다."""
    meta(source_id)          # 표에 없는 소스는 여기서 막는다
    return importlib.import_module(f"scrapers.{source_id}")


def has_detail(source_id: str) -> bool:
    return bool(meta(source_id)["detail"])


def detail_fetcher(source_id: str):
    """상세 조회 함수. 상세를 긁지 않는 소스는 None을 준다.

    예외가 아니라 None인 이유: 상세가 없는 것은 사고가 아니라 그 소스의 성질이다.
    `enrich.py`가 이것을 보고 조용히 건너뛰되, 건너뛴 사실은 기록한다.
    """
    if not has_detail(source_id):
        return None
    return scraper(source_id).fetch_detail


def monotonic_key(source_id: str) -> str | None:
    return meta(source_id)["monotonic_key"]
