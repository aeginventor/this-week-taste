"""이상 알림 (CLAUDE.md 2.4).

11장이 "`alert.py`의 Issue 생성 — **한 번도 실행 안 됨**"으로 적어둔 자리다.

여기가 조용히 고장 나면 특히 나쁘다. 수집은 봇이 월요일에 혼자 돌고, 이상이 나면
파이프라인은 지난주를 이월하고 **성공으로 끝난다** — 사이트도 멀쩡해 보인다.
그 사실을 밖으로 꺼내는 유일한 통로가 이 파일이고, `notify()`는 자기 실패를
로그로만 남긴다. **알림 장치의 고장을 알려줄 수단이 알림뿐**이라는 뜻이다.

그래서 요청이 실제로 나가는 모양과, 실패해도 본 작업이 죽지 않는 것을 여기서 지킨다.
실제 GitHub API가 그 요청을 받아주는지는 테스트가 답할 수 없다 — 그건 토큰을 주고
한 번 만들어봐야 안다.
"""

import json
import urllib.error

import pytest

from pipeline import alert


@pytest.fixture
def captured(monkeypatch):
    """urlopen을 가로채 나가는 요청을 붙잡는다. 테스트가 GitHub을 치면 안 된다."""
    calls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"html_url": "https://github.com/o/r/issues/1"}).encode()

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return _Response()

    monkeypatch.setattr(alert.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "aeginventor/this-week-taste")
    return calls


def test_토큰이_있으면_Issue를_만든다(captured):
    alert.notify("제목", "본문")

    assert len(captured) == 1
    request = captured[0]
    assert request.full_url == (
        "https://api.github.com/repos/aeginventor/this-week-taste/issues")
    assert request.get_method() == "POST"

    payload = json.loads(request.data)
    assert payload == {"title": "제목", "body": "본문", "labels": ["pipeline"]}


def test_인증_헤더가_붙는다(captured):
    alert.notify("제목", "본문")
    headers = {k.lower(): v for k, v in captured[0].header_items()}
    assert headers["authorization"] == "Bearer test-token"
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["content-type"] == "application/json"
    # UA를 안 보내면 GitHub API가 403을 준다.
    assert headers["user-agent"] == "this-week-taste-pipeline"


@pytest.mark.parametrize("missing", ["GH_TOKEN", "GITHUB_REPOSITORY"])
def test_설정이_없으면_로그로_대체한다(captured, monkeypatch, caplog, missing):
    """둘 중 하나만 없어도 요청을 보내지 않는다. 로컬 실행이 여기 해당한다."""
    monkeypatch.delenv(missing)
    with caplog.at_level("WARNING"):
        alert.notify("제목", "본문")
    assert captured == []
    assert "Issue를 만들지 않는다" in caplog.text


def test_Issue_생성이_실패해도_파이프라인은_죽지_않는다(monkeypatch, caplog):
    """알림 실패가 본 작업을 덮어쓰면 안 된다. 단 조용히 넘기지도 않는다."""
    def boom(request, timeout=None):
        raise urllib.error.URLError("연결 실패")

    monkeypatch.setattr(alert.urllib.request, "urlopen", boom)
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    with caplog.at_level("ERROR"):
        alert.notify("제목", "본문")     # 예외가 밖으로 나가면 실패다
    assert "Issue 생성 실패" in caplog.text


def test_이상은_로그에도_반드시_남는다(captured, caplog):
    """토큰이 있든 없든 로그가 먼저다. Issue는 그다음이다."""
    with caplog.at_level("ERROR"):
        alert.notify("제목", "본문")
    assert "[이상] 제목" in caplog.text


def test_raise_anomaly는_알린_뒤_예외를_던진다(captured):
    """호출자가 이 예외를 삼키면 조용한 빈 페이지가 발행된다 (2.4)."""
    with pytest.raises(alert.PipelineAnomaly) as caught:
        alert.raise_anomaly("제목", "본문")
    assert "제목" in str(caught.value) and "본문" in str(caught.value)
    assert len(captured) == 1
