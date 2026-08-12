"""이상 상황 알림 (CLAUDE.md 2.4).

가장 나쁜 결과는 "조용히 빈 페이지가 발행되는 것"이다. 여기를 지나는 모든 것은
반드시 로그에 남고, `GH_TOKEN`이 있으면 GitHub Issue가 된다.

토큰이 없으면 로그로만 남긴다 — 알림 실패가 파이프라인을 죽이지는 않게 한다.
자동화(GitHub Actions)는 CLAUDE.md 8장 5단계라 아직 범위 밖이고, 여기는 그 자리만 잡아둔다.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

GH_API = "https://api.github.com"


class PipelineAnomaly(RuntimeError):
    """수집·판정 결과가 신뢰할 수 없다. 발행하지 않고 지난주를 유지한다."""


def raise_anomaly(title: str, body: str) -> None:
    """이상 상황을 알리고 예외를 던진다. 호출자는 이 예외를 잡아 삼키지 않는다."""
    notify(title, body)
    raise PipelineAnomaly(f"{title}\n{body}")


def notify(title: str, body: str) -> None:
    log.error("[이상] %s\n%s", title, body)

    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        log.warning("GH_TOKEN/GITHUB_REPOSITORY가 없어 Issue를 만들지 않는다 (로그로 대체)")
        return

    payload = json.dumps({"title": title, "body": body, "labels": ["pipeline"]}).encode()
    request = urllib.request.Request(
        f"{GH_API}/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "this-week-taste-pipeline",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            log.info("Issue 생성됨: %s", json.load(resp).get("html_url"))
    except (urllib.error.URLError, OSError) as exc:
        # 알림 실패가 본 작업을 덮어쓰지 않게 한다. 단 조용히 넘기지는 않는다.
        log.error("Issue 생성 실패 (원래 문제는 위 [이상] 로그를 볼 것): %s", exc)
