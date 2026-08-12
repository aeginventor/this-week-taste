"""제품명 정규화. `diff.py`가 같은 제품인지 판정할 때 쓴다.

여기서 무엇을 **하지 않는지**가 무엇을 하는지보다 중요하다.

## POS 접두사(`샐)`, `삼)`, `빅삼)`)를 제거하지 않는다

정찰 보고서는 접두사를 노이즈로 보고 제거를 권했다. 실제 데이터가 이를 반박한다.
CU 간편식사 1페이지 40건에서만 접두사 제거 시 충돌하는 쌍이 2쌍(5%) 나온다:

    삼)치킨마요삼각   1,400원  8801771035527
    빅삼)치킨마요삼각 1,700원  8800336392051   ← 접두사만 빼면 둘 다 "치킨마요삼각"

    삼)참치마요삼각   1,200원  8800279675761
    빅삼)참치마요삼각 1,700원  8800279675723

바코드도 가격도 다른 **별개 상품**이다. 접두사는 노이즈가 아니라 규격 정보
(삼각김밥 / 빅사이즈 삼각김밥)다. 제거하면 5%가 조용히 오병합된다.

## 이름만으로 같은 제품이라고 판정하지 않는다

CU는 제품명을 12자에서 자른다. 서로 다른 상품이 잘린 뒤 같은 문자열이 될 수 있다.
`diff.py`의 이름 기반 매칭이 항상 가격과 복합인 이유다.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")
# 표시용으로만 쓰는 POS 접두사 패턴. 판정에는 절대 쓰지 않는다.
_POS_PREFIX_RE = re.compile(r"^([^()\s]{1,4})\)\s*")


def normalize_name(name: str) -> str:
    """비교용 이름. 표기 차이만 지우고 의미는 건드리지 않는다.

    - NFKC 정규화 (전각/반각, 호환 문자 통일)
    - 연속 공백 1칸으로 축약, 앞뒤 공백 제거
    - 영문 대소문자 통일
    """
    text = unicodedata.normalize("NFKC", name)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.lower()


def split_pos_prefix(name: str) -> tuple[str | None, str]:
    """`'샐)오리지널닭가슴살샐러'` → `('샐', '오리지널닭가슴살샐러')`.

    **표시용이다.** 화면에서 접두사를 배지로 빼거나 숨기는 데 쓴다.
    제품 동일성 판정에 쓰면 서로 다른 상품이 병합된다 (모듈 설명 참조).
    """
    match = _POS_PREFIX_RE.match(name)
    if not match:
        return None, name
    return match.group(1), name[match.end():]


def similarity(a: str, b: str) -> float:
    """정규화된 이름 두 개의 유사도 (0.0~1.0)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()
