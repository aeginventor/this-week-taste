"""공통 HTTP 유틸. CLAUDE.md 5장의 요청 규칙을 한 곳에 모아둔 것이다.

여기는 **스크래퍼 프레임워크가 아니다.** 7장이 추상화 선행 구축을 금지하므로,
파싱이나 스키마에 관한 것은 넣지 않는다. 세션·재시도·간격·원본 저장까지만.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.robotparser
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

# 원본이 어디 사는지는 paths.py가 정한다. 저장소 밖일 수 있다(ADR-0011).
# scrapers 가 pipeline.weeks 를 쓰는 것과 같은 이유 — 공유 인프라는 한 곳에 둔다.
RAW_DIR = paths.RAW_DIR


class FetchError(RuntimeError):
    """재시도를 다 쓰고도 실패. 삼키지 말고 위로 던진다(2.4)."""


class RobotsDisallowed(RuntimeError):
    """robots.txt가 막은 경로. 우회하지 않는다(5장)."""


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
        self.request_count = 0

    # ── robots.txt ───────────────────────────────────────────────
    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
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

    def assert_allowed(self, url: str) -> None:
        if not self._robots_for(url).can_fetch(self.session.headers["User-Agent"], url):
            raise RobotsDisallowed(f"robots.txt가 막은 경로다. 우회하지 않는다: {url}")

    # ── 요청 ─────────────────────────────────────────────────────
    def _wait(self) -> None:
        gap = time.monotonic() - self._last_request_at
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)

    def _mark(self) -> None:
        self._last_request_at = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        self.assert_allowed(url)
        kwargs.setdefault("timeout", TIMEOUT)
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait()
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
