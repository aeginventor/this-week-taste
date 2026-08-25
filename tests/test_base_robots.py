"""robots.txt의 시각 제약 (CLAUDE.md 5장).

`urllib.robotparser`는 `Crawl-delay`까지만 읽고 `Visit-time`은 버린다. 비표준
확장이기 때문이다. 그래서 그 줄을 우리가 직접 읽는데, **틀려도 예외가 나지 않는다** —
창을 못 읽으면 "제약 없음"이 되어 아무 때나 긁게 되고, 반대로 그룹을 잘못 고르면
남의 창을 우리 창으로 알고 영영 못 긁게 된다. 7장이 말하는 "틀려도 조용한 곳"이다.

gs25가 이 규칙을 가진 첫 소스다(`Crawl-delay: 10`, `Visit-time: 0400-0845` UTC).
"""

from datetime import time

import pytest

from scrapers import base

UA = "ThisWeekTaste/1.0 (+https://example.test/about)"

GS25_ROBOTS = """
# For all robots
User-agent: *

Disallow: /gscvs/ko/cart

Request-rate: 1/10              # maximum rate is one page every 10 seconds
Crawl-delay: 10                 # 10 seconds between page requests
Visit-time: 0400-0845           # only visit between 04:00 and 08:45 UTC

User-agent: MJ12bot
Disallow: /
"""


def test_실제_robots에서_창을_읽는다():
    assert base.parse_visit_time(GS25_ROBOTS, UA) == (time(4, 0), time(8, 45))


def test_제약이_없으면_None이다():
    robots = "User-agent: *\nDisallow: /admin\n"
    assert base.parse_visit_time(robots, UA) is None


def test_다른_봇의_창을_우리_것으로_읽지_않는다():
    robots = "User-agent: Yeti\nVisit-time: 0100-0200\n\nUser-agent: *\nDisallow: /admin\n"
    assert base.parse_visit_time(robots, UA) is None


def test_우리를_지목한_그룹이_별표보다_우선한다():
    robots = (
        "User-agent: *\nVisit-time: 0400-0845\n\n"
        "User-agent: thisweektaste\nVisit-time: 0000-2359\n"
    )
    assert base.parse_visit_time(robots, UA) == (time(0, 0), time(23, 59))


def test_그룹_이름이_여럿이어도_적용된다():
    robots = "User-agent: Googlebot\nUser-agent: *\nVisit-time: 0400-0845\n"
    assert base.parse_visit_time(robots, UA) == (time(4, 0), time(8, 45))


def test_읽을_수_없는_값은_제약_없음으로_둔다():
    """막느니 여는 쪽으로 떨어뜨린다. 창을 지어내면 그 소스는 영영 못 긁는다."""
    assert base.parse_visit_time("User-agent: *\nVisit-time: 아무때나\n", UA) is None
    assert base.parse_visit_time("User-agent: *\nVisit-time: 9999-0000\n", UA) is None


def test_창의_양_끝은_포함한다():
    window = (time(4, 0), time(8, 45))
    assert base.within_visit_time(window, time(4, 0))
    assert base.within_visit_time(window, time(8, 45))
    assert not base.within_visit_time(window, time(3, 59))
    assert not base.within_visit_time(window, time(8, 46))


def test_창이_없으면_언제나_참이다():
    assert base.within_visit_time(None, time(3, 0))


def test_자정을_넘기는_창():
    """뒤집힌 창을 '언제나 거짓'으로 다루면 그 소스는 영영 수집되지 않는다."""
    window = (time(22, 0), time(3, 0))
    assert base.within_visit_time(window, time(23, 30))
    assert base.within_visit_time(window, time(2, 0))
    assert not base.within_visit_time(window, time(12, 0))


# ── Session에 실제로 걸리는가 ────────────────────────────────────


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.content = text.encode()


@pytest.fixture
def session(monkeypatch):
    """robots.txt만 가짜로 물려준다. 테스트가 네트워크를 치면 안 된다."""
    def make(robots_text):
        sess = base.Session()
        monkeypatch.setattr(sess.session, "get",
                            lambda url, **kw: _Response(robots_text))
        return sess
    return make


def test_창_밖이면_요청을_거부한다(session, monkeypatch):
    sess = session(GS25_ROBOTS)
    monkeypatch.setattr(base, "within_visit_time", lambda window, now: False)
    with pytest.raises(base.VisitTimeClosed) as caught:
        sess.assert_allowed("http://gs25.example/gscvs/ko/products/x")
    # 사람이 언제 다시 돌려야 하는지 알 수 있어야 한다.
    assert "04:00" in str(caught.value) and "13:00" in str(caught.value)


def test_창_안이면_통과한다(session, monkeypatch):
    sess = session(GS25_ROBOTS)
    monkeypatch.setattr(base, "within_visit_time", lambda window, now: True)
    sess.assert_allowed("http://gs25.example/gscvs/ko/products/x")


def test_crawl_delay가_요청_간격을_올린다(session):
    sess = session(GS25_ROBOTS)
    sess.assert_allowed("http://gs25.example/gscvs/ko/products/x")
    assert sess._intervals["http://gs25.example"] == 10.0


def test_crawl_delay가_없으면_기본_간격_그대로(session):
    """지금 붙은 다른 소스들이 이 경우다. 수집 시간이 변하면 안 된다."""
    sess = session("User-agent: *\nDisallow: /admin\n")
    sess.assert_allowed("https://other.example/list")
    assert sess._intervals == {}
    assert sess._visit_windows == {"https://other.example": None}


def test_짧은_crawl_delay가_우리_하한을_내리지_않는다(session):
    """5장의 1초는 상한이 아니라 하한이다."""
    sess = session("User-agent: *\nCrawl-delay: 0.1\n")
    sess.assert_allowed("https://fast.example/list")
    assert sess._intervals == {}
