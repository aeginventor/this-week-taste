"""공통 HTTP 유틸. CLAUDE.md 5장의 요청 규칙을 한 곳에 모아둔 것이다.

여기는 **스크래퍼 프레임워크가 아니다.** 7장이 추상화 선행 구축을 금지하므로,
파싱이나 스키마에 관한 것은 넣지 않는다. 세션·재시도·간격·원본 저장까지만.
"""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.robotparser
from datetime import datetime, time as clock, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from pipeline import paths

log = logging.getLogger(__name__)

# CLAUDE.md 5장: User-Agent에 연락 가능한 식별자를 넣는다.
# 도메인이 확정되면 THIS_WEEK_TASTE_UA 환경변수로 덮어쓴다.
# ⚠️ 이 문자열에 'Claude'/'ClaudeBot'을 절대 넣지 말 것. 일부 사이트(bhc 등)가
#    robots.txt에서 ClaudeBot을 Disallow하고 있어 넣는 순간 금지 대상이 된다.
# ⚠️ 이 주소의 /about 페이지가 실제로 존재해야 한다. 없으면 "연락 가능한 식별자"가
#    아니라 지키지 못한 약속이 된다. 페이지는 web/app/about/page.tsx,
#    주소는 web/config/site.ts의 `url` — 셋이 어긋나면 안 된다.
DEFAULT_USER_AGENT = "ThisWeekTaste/1.0 (+https://this-week-taste.vercel.app/about)"
# `or`를 쓰는 이유: 환경변수가 **빈 문자열로 설정된** 경우를 기본값으로 되돌린다.
# os.environ.get(키, 기본값)은 빈 문자열을 그대로 돌려주므로, CI에서 변수를
# 정의만 하고 값을 안 채우면 UA 없이 요청이 나간다. 아무 예외도 나지 않는다.
USER_AGENT = os.environ.get("THIS_WEEK_TASTE_UA") or DEFAULT_USER_AGENT

TIMEOUT = 15
MAX_ATTEMPTS = 3
MIN_INTERVAL = 1.0  # 요청 간 최소 간격(초). 동시 요청은 하지 않는다.
                    # 소스의 robots.txt가 `Crawl-delay`로 더 긴 간격을 요구하면 그쪽을 따른다.

# `Visit-time`은 UTC로 적는다(robots 확장 규약). 사람에게 보일 때만 KST로 바꾼다.
KST = timezone(timedelta(hours=9))

# 원본이 어디 사는지는 paths.py가 정한다. 저장소 밖일 수 있다(ADR-0011).
# scrapers 가 pipeline.weeks 를 쓰는 것과 같은 이유 — 공유 인프라는 한 곳에 둔다.
RAW_DIR = paths.RAW_DIR


class FetchError(RuntimeError):
    """재시도를 다 쓰고도 실패. 삼키지 말고 위로 던진다(2.4)."""


class RobotsDisallowed(RuntimeError):
    """robots.txt가 막은 경로. 우회하지 않는다(5장)."""


class VisitTimeClosed(RuntimeError):
    """robots.txt가 정한 방문 시간대 밖이다. 몰래 긁지 않고 시끄럽게 멈춘다(2.4, 5장)."""


# ── robots.txt의 시각 제약 ───────────────────────────────────────
#
# `urllib.robotparser`는 `Crawl-delay`까지만 읽고 `Visit-time`은 버린다. 비표준
# 확장이라 그렇다. 그래도 **사이트가 명시한 의사**이므로 우리는 지킨다(5장).
# 원문을 직접 훑어야 해서 파싱을 여기 둔다.

_VISIT_TIME = re.compile(r"^(\d{3,4})\s*-\s*(\d{3,4})$")


def _agent_matches(agent: str, user_agent: str) -> bool:
    """robots의 그룹 이름이 우리 UA에 적용되는가. robotparser와 같은 규칙."""
    return agent == "*" or agent in user_agent.lower()


def parse_visit_time(text: str, user_agent: str) -> tuple[clock, clock] | None:
    """robots.txt 원문에서 우리에게 적용되는 `Visit-time` 창을 뽑는다 (UTC).

    그룹이 여럿이면 **이름이 우리를 지목한 그룹이 `*`보다 우선한다.**
    없으면 None — 시간 제약이 없다는 뜻이다.
    """
    specific: tuple[clock, clock] | None = None
    wildcard: tuple[clock, clock] | None = None
    agents: list[str] = []
    collecting = False

    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()

        if field == "user-agent":
            if not collecting:
                agents = []
                collecting = True
            agents.append(value.lower())
            continue

        collecting = False
        if field != "visit-time":
            continue
        match = _VISIT_TIME.match(value.replace(" ", ""))
        if not match:
            log.warning("Visit-time을 읽지 못했다: %r — 제약 없음으로 둔다", value)
            continue
        try:
            window = (_clock(match.group(1)), _clock(match.group(2)))
        except ValueError:
            log.warning("Visit-time 값이 시각이 아니다: %r", value)
            continue
        if any(a == "*" for a in agents):
            wildcard = window
        if any(a != "*" and _agent_matches(a, user_agent) for a in agents):
            specific = window

    return specific or wildcard


def _clock(hhmm: str) -> clock:
    hhmm = hhmm.zfill(4)
    return clock(int(hhmm[:2]), int(hhmm[2:]))


def within_visit_time(window: tuple[clock, clock] | None, now: clock) -> bool:
    """지금이 창 안인가. 창이 없으면 언제나 참이다.

    끝 시각은 **포함**한다(`0400-0845`면 08:45:00도 허용). 자정을 넘기는 창
    (`2200-0300`)도 다룬다 — 그런 소스는 아직 없지만 뒤집힌 창을 조용히
    "언제나 거짓"으로 만들면 그 소스는 영영 수집되지 않는다.
    """
    if window is None:
        return True
    start, end = window
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


class Session:
    """호스트 하나를 상대하는 세션. 요청 간격과 재시도를 강제한다."""

    def __init__(self, *, user_agent: str = USER_AGENT, min_interval: float = MIN_INTERVAL):
        # 5장은 **연락 가능한 식별자**를 요구한다. 빈 UA는 식별자가 아니다.
        # 시끄럽게 막는다 — 조용히 익명으로 긁는 것이 가장 나쁘다 (2.4).
        if not (user_agent or "").strip():
            raise ValueError("User-Agent가 비었다. THIS_WEEK_TASTE_UA를 확인할 것")
        if "claude" in user_agent.lower():
            raise ValueError("User-Agent에 'Claude'를 넣지 말 것 (base.py 주석 참조)")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        # 호스트별 시각 제약. robots.txt를 읽을 때 한 번 채운다.
        self._visit_windows: dict[str, tuple[clock, clock] | None] = {}
        self._intervals: dict[str, float] = {}
        self.request_count = 0

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    # ── robots.txt ───────────────────────────────────────────────
    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        origin = self._origin(url)
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                self._wait()
                resp = self.session.get(robots_url, timeout=TIMEOUT)
                self._mark()
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    log.info("robots.txt 확인: %s (%d바이트)", robots_url, len(resp.content))
                    self._apply_limits(origin, rp, resp.text)
                else:
                    # 파일이 없으면 금지 규칙도 없다. CU가 이 경우(HTTP 404).
                    rp.allow_all = True
                    log.info("robots.txt 없음(HTTP %d): %s → 허용으로 간주",
                             resp.status_code, robots_url)
            except requests.RequestException as exc:
                # robots.txt를 못 읽으면 막힌 것으로 보고 멈춘다. 추측으로 긁지 않는다.
                raise RobotsDisallowed(f"robots.txt를 읽을 수 없다: {robots_url} ({exc})") from exc
            self._robots[origin] = rp
        return self._robots[origin]

    def _apply_limits(self, origin: str, rp: urllib.robotparser.RobotFileParser,
                      text: str) -> None:
        """robots.txt가 요구한 요청 간격과 방문 시간대를 이 호스트에 걸어둔다.

        `Crawl-delay`는 우리 기본 간격보다 길 때만 의미가 있다. 짧게 적혀 있어도
        내리지 않는다 — 5장의 1초는 상한이 아니라 하한이다.
        """
        user_agent = self.session.headers["User-Agent"]

        delay = rp.crawl_delay(user_agent)
        if delay and float(delay) > self.min_interval:
            self._intervals[origin] = float(delay)
            log.info("  robots가 요청 간격 %.0f초를 요구한다 (%s)", float(delay), origin)

        window = parse_visit_time(text, user_agent)
        self._visit_windows[origin] = window
        if window:
            log.info("  robots가 방문 시간대를 제한한다: %s~%s UTC (KST %s~%s)",
                     *_window_labels(window))

    def assert_allowed(self, url: str) -> None:
        if not self._robots_for(url).can_fetch(self.session.headers["User-Agent"], url):
            raise RobotsDisallowed(f"robots.txt가 막은 경로다. 우회하지 않는다: {url}")

        window = self._visit_windows.get(self._origin(url))
        now = datetime.now(timezone.utc)
        if not within_visit_time(window, now.time()):
            start_utc, end_utc, start_kst, end_kst = _window_labels(window)
            raise VisitTimeClosed(
                f"robots.txt가 정한 방문 시간대 밖이다: {url}\n"
                f"  허용  {start_utc}~{end_utc} UTC (KST {start_kst}~{end_kst})\n"
                f"  지금  {now:%H:%M} UTC (KST {now.astimezone(KST):%H:%M})\n"
                "  창이 열린 뒤에 다시 돌린다. 우회하지 않는다(5장)."
            )

    # ── 요청 ─────────────────────────────────────────────────────
    def _wait(self, url: str | None = None) -> None:
        interval = self.min_interval
        if url is not None:
            interval = max(interval, self._intervals.get(self._origin(url), 0.0))
        gap = time.monotonic() - self._last_request_at
        if gap < interval:
            time.sleep(interval - gap)

    def _mark(self) -> None:
        self._last_request_at = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        self.assert_allowed(url)
        kwargs.setdefault("timeout", TIMEOUT)
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait(url)
            try:
                resp = self.session.request(method, url, **kwargs)
                self._mark()
                self.request_count += 1
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                self._mark()
                last_exc = exc
                if attempt == MAX_ATTEMPTS:
                    break
                backoff = 2 ** (attempt - 1)  # 1s, 2s
                log.warning("요청 실패 (%d/%d) %s %s: %s — %.0f초 후 재시도",
                            attempt, MAX_ATTEMPTS, method, url, exc, backoff)
                time.sleep(backoff)
        raise FetchError(f"{MAX_ATTEMPTS}회 시도 후 실패: {method} {url}") from last_exc

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)


def _window_labels(window: tuple[clock, clock]) -> tuple[str, str, str, str]:
    """창을 UTC와 KST 두 표기로. 로그와 예외 메시지가 같은 말을 쓰게 한다."""
    def kst(value: clock) -> str:
        return f"{(value.hour + 9) % 24:02d}:{value.minute:02d}"
    start, end = window
    return (f"{start:%H:%M}", f"{end:%H:%M}", kst(start), kst(end))


def save_raw(week: str, source_id: str, request_id: str, body: str | bytes, ext: str) -> Path:
    """원본 응답 보관 (CLAUDE.md 2.5).

    `data/raw/<week>/<source_id>/<request_id>.<ext>`
    파서가 깨져도 원본이 있으면 재처리할 수 있다. 없으면 그 주는 영영 잃는다.
    """
    path = RAW_DIR / week / source_id / f"{request_id}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")
    return path
