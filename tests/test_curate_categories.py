"""채널별 자체 분류 목록 (CLAUDE.md 6장, 7장).

`curate.py`는 목록 없는 채널을 만나면 예외를 던지지 않고 **원본 카테고리로 발행한다**
(6장: 편집 품질보다 발행이 우선). 그래서 목록을 빠뜨려도 파이프라인은 멀쩡히 돌고,
발행물에만 소스 어휘(`과자/시리얼 > 과자/쿠키/파이`)가 우리 분류인 척 섞여 나온다.
로그 한 줄 말고는 아무 일도 일어나지 않는다 — 7장이 테스트를 쓰라고 한 성질이다.

그 조용한 실패를 **소스를 등록하는 시점에** 드러내는 것이 이 파일의 목적이다.
"""

import pytest

from pipeline import curate, sources


@pytest.mark.parametrize("source_id", sources.known())
def test_등록된_소스의_채널에는_분류_목록이_있다(source_id):
    channel = sources.meta(source_id)["channel"]
    assert channel in curate.CATEGORIES_BY_CHANNEL, (
        f"{source_id}의 채널 {channel!r}에 분류 목록이 없다. "
        "이대로 두면 이 소스의 category가 전부 원본 문자열로 발행된다."
    )


@pytest.mark.parametrize("channel", sorted(curate.CATEGORIES_BY_CHANNEL))
def test_목록에는_기타가_있다(channel):
    """모델이 고를 수 있는 도피처가 없으면 억지로 엉뚱한 분류를 고른다."""
    assert "기타" in curate.CATEGORIES_BY_CHANNEL[channel]


@pytest.mark.parametrize("channel", sorted(curate.CATEGORIES_BY_CHANNEL))
def test_목록에_중복이_없다(channel):
    items = curate.CATEGORIES_BY_CHANNEL[channel]
    assert len(set(items)) == len(items)


@pytest.mark.parametrize("channel", sorted(curate.CATEGORIES_BY_CHANNEL))
def test_채널_이름표가_짝을_이룬다(channel):
    """분류 목록만 추가하고 이름표를 잊으면 UnknownChannel로 떨어진다.

    증상이 "목록이 없다"로 나와서 실제 원인(이름표 누락)을 찾는 데 시간이 든다.
    """
    assert channel in curate.CHANNEL_LABEL


@pytest.mark.parametrize("channel", sorted(curate.CATEGORIES_BY_CHANNEL))
def test_프롬프트에_그_채널의_목록이_들어간다(channel):
    prompt = curate.system_prompt(channel)
    assert curate.CHANNEL_LABEL[channel] in prompt
    for name in curate.CATEGORIES_BY_CHANNEL[channel]:
        assert name in prompt


# ⚠️ 실재하지 않는 채널 이름을 쓴다. 아직 소스가 없는 진짜 채널 이름(`dessert` 등)을
# 쓰면 그 채널의 첫 소스를 붙이는 날 이 테스트가 같이 깨진다 — 2026-08-25에
# 배스킨라빈스를 붙이면서 실제로 그랬다. 이 테스트가 지키려는 것은 "특정 채널이
# 비어 있다"가 아니라 "모르는 채널이 와도 발행이 죽지 않는다"이다.
UNKNOWN_CHANNEL = "존재하지않는채널"


def test_모르는_채널은_UnknownChannel():
    assert UNKNOWN_CHANNEL not in curate.CATEGORIES_BY_CHANNEL
    with pytest.raises(curate.UnknownChannel, match="분류 목록이 없다"):
        curate.system_prompt(UNKNOWN_CHANNEL)


def test_모르는_채널이어도_발행은_계속된다(caplog):
    """6장: 편집 품질보다 발행 자체가 우선이다. 여기서 예외가 나가면 그 주가 통째로 죽는다."""
    items = [{"external_id": "x1", "name": "무언가", "category_raw": "소스 원본 분류"}]
    with caplog.at_level("ERROR"):
        result = curate.curate(items, {}, channel=UNKNOWN_CHANNEL)
    assert result["x1"]["category"] == "소스 원본 분류"
    assert result["x1"]["blurb"] is None
    assert "분류 목록이 없다" in caplog.text
