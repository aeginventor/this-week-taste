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


# ⚠️ 아래 셋은 `_robots_for`를 직접 부른다. `assert_allowed`로 부르면 **지금이 창
# 안인지에 따라 결과가 달라져서**, 창 안에서만 통과하는 테스트가 된다. 실제로 그렇게
# 썼다가 창이 닫히자마자 깨졌다(2026-08-25 KST 17:46).


def test_crawl_delay가_요청_간격을_올린다(session):
    sess = session(GS25_ROBOTS)
    sess._robots_for("http://gs25.example/gscvs/ko/products/x")
    assert sess._intervals["http://gs25.example"] == 10.0


def test_crawl_delay가_없으면_기본_간격_그대로(session):
    """지금 붙은 다른 소스들이 이 경우다. 수집 시간이 변하면 안 된다."""
    sess = session("User-agent: *\nDisallow: /admin\n")
    sess._robots_for("https://other.example/list")
    assert sess._intervals == {}
    assert sess._visit_windows == {"https://other.example": None}


def test_짧은_crawl_delay가_우리_하한을_내리지_않는다(session):
    """5장의 1초는 상한이 아니라 하한이다."""
    sess = session("User-agent: *\nCrawl-delay: 0.1\n")
    sess._robots_for("https://fast.example/list")
    assert sess._intervals == {}


# ── robots.txt 원본 보관 (ADR-0017 결정 3) ────────────────────────
#
# 2026-08-31에 러너에서 parisbaguette가 `RobotsDisallowed`로 막혔는데, 같은 파일을
# 로컬에서 받아 같은 파서에 넣으면 **허용**이 나왔다. 러너가 다른 robots.txt를 받은
# 것인데 **그것을 증명할 방법이 없었다** — 2.5의 원본 보관이 robots까지는 닿지 않았다.
#
# 보관이 조용히 안 되는 것이 이 코드의 위험이다. 수집은 성공하고 근거만 없다.


@pytest.fixture
def archiving(monkeypatch, tmp_path):
    """robots.txt만 가짜로 물려주고, 원본은 임시 디렉토리에 남긴다."""
    monkeypatch.setattr(base, "RAW_DIR", tmp_path)

    def make(robots_text, **kwargs):
        # min_interval=0: 이 파일은 보관을 재는 것이지 간격을 재는 것이 아니다.
        # 간격은 위쪽 테스트들이 본다.
        kwargs.setdefault("min_interval", 0)
        sess = base.Session(week="2026-W36", source_id="예시소스", **kwargs)
        monkeypatch.setattr(sess.session, "get",
                            lambda url, **kw: _Response(robots_text))
        return sess
    return make


def test_받은_robots를_원본으로_남긴다(archiving, tmp_path):
    sess = archiving(GS25_ROBOTS)
    sess._robots_for("http://gs25.example/gscvs/ko/products/x")
    saved = tmp_path / "2026-W36" / "예시소스" / "robots_gs25.example.txt"
    assert saved.read_text(encoding="utf-8") == GS25_ROBOTS


def test_호스트마다_따로_남는다(archiving, tmp_path):
    """한 소스가 호스트를 둘 이상 상대하면 서로 덮어쓰지 않아야 한다."""
    sess = archiving(GS25_ROBOTS)
    sess._robots_for("http://a.example/x")
    sess._robots_for("http://b.example/y")
    남은것 = sorted(p.name for p in (tmp_path / "2026-W36" / "예시소스").iterdir())
    assert 남은것 == ["robots_a.example.txt", "robots_b.example.txt"]


def test_주차나_소스를_모르면_남기지_않는다(monkeypatch, tmp_path):
    """`enrich.py`·`imagecheck.py`가 이 경우다. 그 주 robots는 수집이 이미 남겼다."""
    monkeypatch.setattr(base, "RAW_DIR", tmp_path)
    sess = base.Session()
    monkeypatch.setattr(sess.session, "get", lambda url, **kw: _Response(GS25_ROBOTS))
    sess._robots_for("http://gs25.example/x")
    assert not list(tmp_path.iterdir())


def test_보관에_실패해도_수집은_계속된다(archiving, monkeypatch, caplog):
    """근거를 남기는 일이지 수집의 조건이 아니다.

    다만 삼키지는 않는다 — 2.4가 금지하는 것은 `except: pass`다.
    """
    def 터진다(*args, **kwargs):
        raise OSError("디스크가 가득 찼다")
    monkeypatch.setattr(base, "save_raw", 터진다)

    sess = archiving(GS25_ROBOTS)
    with caplog.at_level("WARNING"):
        sess._robots_for("http://gs25.example/x")

    # 창 제약은 그대로 읽혔다 — 보관 실패가 파싱을 건드리지 않았다.
    assert sess._visit_windows["http://gs25.example"] == (time(4, 0), time(8, 45))
    assert "남기지 못했다" in caplog.text


def test_robots가_없어도_받은_응답을_남긴다(archiving, tmp_path):
    """404도 판정의 근거다. "파일이 없어서 허용했다"와 "못 받았다"는 다르다.

    CU가 이 경우다(HTTP 404). 나중에 그 소스가 robots를 놓으면 그 주부터 내용이
    달라지는데, 원본이 없으면 언제 바뀌었는지 말할 수 없다.
    """
    sess = archiving("<html>Not Found</html>")
    sess.session.get = lambda url, **kw: _Response("<html>Not Found</html>", 404)
    sess._robots_for("http://nofile.example/x")
    saved = tmp_path / "2026-W36" / "예시소스" / "robots_nofile.example.txt"
    assert saved.exists()
