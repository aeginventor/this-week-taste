"""소스 레지스트리 정합성 (CLAUDE.md 7장).

이 표는 `snapshot.py`·`enrich.py`·`publish.py` 셋이 함께 읽는다. 여기가 어긋나면
증상이 세 곳에서 따로 나타나고, 그중 몇은 예외 없이 조용히 틀린 값을 낸다 —
7장이 테스트를 쓰라고 한 바로 그 성질이다.

**소스를 추가할 때 이 파일을 고칠 일은 없다.** 표를 순회하므로 새 소스가 자동으로
검사 대상이 된다. 그것이 목록형 테스트를 쓰지 않는 이유다.
"""

import pytest

from pipeline import sources

CHANNELS = {"mart", "convenience", "cafe", "dessert", "restaurant", "fmcg"}


@pytest.mark.parametrize("source_id", sources.known())
def test_스크래퍼_모듈이_존재한다(source_id):
    """모듈은 `scrapers/<source_id>.py` 규칙으로 찾는다. 이름이 어긋나면 ImportError다."""
    module = sources.scraper(source_id)
    assert callable(module.fetch)
    assert module.SOURCE_ID == source_id


@pytest.mark.parametrize("source_id", sources.known())
def test_채널이_4장의_목록_안에_있다(source_id):
    """발행물의 `channel`은 자유 문자열이 아니다. 오타가 나면 웹 필터에서 통째로 빠진다."""
    assert sources.meta(source_id)["channel"] in CHANNELS


@pytest.mark.parametrize("source_id", sources.known())
def test_상세를_긁는다고_적힌_소스는_실제로_긁을_수_있다(source_id):
    """`detail: True`인데 `fetch_detail`이 없으면 enrich가 신상 전량에서 터진다."""
    fetcher = sources.detail_fetcher(source_id)
    if sources.has_detail(source_id):
        assert callable(fetcher)
    else:
        assert fetcher is None


@pytest.mark.parametrize("source_id", sources.known())
def test_카테고리_기준이_실제_카테고리_코드다(source_id):
    """`BOOTSTRAP_COUNTS`의 키가 `CATEGORIES`에 없으면 그 기준은 **조용히 무시된다.**

    `snapshot.py`는 기준에 있는 코드만 훑으므로, 오타 난 코드는 예외를 내지 않고
    검사에서 빠질 뿐이다. 카테고리 하나가 통째로 비어도 못 잡게 된다.
    """
    module = sources.scraper(source_id)
    unknown = set(getattr(module, "BOOTSTRAP_COUNTS", {})) - set(module.CATEGORIES)
    assert not unknown, f"{source_id}: CATEGORIES에 없는 코드 {sorted(unknown)}"


@pytest.mark.parametrize("source_id", sources.known())
def test_카테고리_이름이_유일하다(source_id):
    """`snapshot.py`가 `category_raw`(이름) → 코드로 역매핑해 건수를 센다.

    이름이 겹치면 역매핑에서 뒤엣것이 앞엣것을 덮어써, 겹친 카테고리 중 하나의
    건수가 통째로 0으로 집계된다. 예외는 나지 않는다.
    """
    labels = list(sources.scraper(source_id).CATEGORIES.values())
    assert len(set(labels)) == len(labels)


def test_모르는_소스는_막는다():
    with pytest.raises(ValueError, match="모르는 소스"):
        sources.meta("nonexistent")
