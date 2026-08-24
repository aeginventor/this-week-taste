"""이미지 표본 검사의 순수 부분. 판정이 틀려도 예외가 안 난다 (CLAUDE.md 7장)."""

import pytest

from pipeline import imagecheck


def _items(*specs):
    return [{"source_id": sid, "image_url": url} for sid, url in specs]


def test_소스별로_나눠서_표본을_뽑는다():
    items = _items(*[("cu", f"https://x/{i}") for i in range(30)],
                   *[("orion", f"https://y/{i}") for i in range(3)])
    s = imagecheck.sample(items, size=10, seed=1)
    assert len(s["cu"]) == 10
    assert len(s["orion"]) == 3, "표본 크기보다 적으면 있는 만큼만"


def test_이미지가_없는_항목은_빠진다():
    items = [{"source_id": "cu", "image_url": None},
             {"source_id": "cu", "image_url": ""},
             {"source_id": "cu", "image_url": "https://x/1"}]
    assert imagecheck.sample(items) == {"cu": ["https://x/1"]}


def test_이미지가_아예_없는_소스는_키가_안_생긴다():
    """홈플러스처럼 전부 있는 소스와, 없는 소스를 구분해야 한다."""
    assert imagecheck.sample([{"source_id": "cu", "image_url": None}]) == {}


def test_표본이_같은_seed면_같다():
    items = _items(*[("cu", f"https://x/{i}") for i in range(50)])
    assert imagecheck.sample(items, seed=7) == imagecheck.sample(items, seed=7)


@pytest.mark.parametrize("rate,checked,expected", [
    (1.0, 10, "ok"),
    (0.5, 10, "ok"),        # 경계값은 통과
    (0.4, 10, "broken"),
    (0.0, 10, "broken"),
    (0.0, 0, "unknown"),    # 표본이 없으면 판정하지 않는다
])
def test_판정_기준(rate, checked, expected):
    assert imagecheck.verdict(rate, checked) == expected
