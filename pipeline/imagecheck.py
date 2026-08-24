"""발행물의 이미지가 실제로 열리는지 표본 검사한다.

## 왜 필요한가

7장이 이미지 복제를 금지해서 원본 CDN 주소를 그대로 참조한다. 그래서 **소스가 CDN을
막거나 주소 규칙을 바꾸면 우리 사이트의 이미지가 통째로 깨진다.** 그런데 그건
파이프라인 어디에도 예외를 남기지 않는다 — 발행은 성공하고 사이트도 빌드되고,
그냥 회색 네모만 뜬다. 2.4가 말하는 "조용히 잘못되는 것"이다.

전수 검사는 하지 않는다. 항목당 요청이 하나씩 붙어 수백 건이 된다.
**소스별로 표본만 본다** — 통째로 깨지는 사고를 잡는 것이 목적이지
개별 404를 찾는 것이 아니다. 단종된 제품의 이미지가 빠지는 것은 정상이다.

    python -m pipeline.imagecheck --week 2026-W35
"""

from __future__ import annotations

import argparse
import logging
import random
import sys

from pipeline import publish, weeks
from scrapers import base

log = logging.getLogger(__name__)

SAMPLE_PER_SOURCE = 10
# 이 비율 아래로 떨어지면 개별 404가 아니라 통째로 막힌 것으로 본다.
MIN_PASS_RATE = 0.5


def sample(items: list[dict], size: int = SAMPLE_PER_SOURCE,
           seed: int | None = None) -> dict[str, list[str]]:
    """소스별로 이미지 주소를 표본 추출. 순수 함수라 네트워크 없이 테스트된다."""
    by_source: dict[str, list[str]] = {}
    for item in items:
        url = item.get("image_url")
        if url:
            by_source.setdefault(item["source_id"], []).append(url)
    rng = random.Random(seed)
    return {sid: rng.sample(urls, min(size, len(urls)))
            for sid, urls in by_source.items()}


def verdict(pass_rate: float, checked: int) -> str:
    """ok | broken | unknown. 표본이 없으면 판정하지 않는다."""
    if checked == 0:
        return "unknown"
    return "ok" if pass_rate >= MIN_PASS_RATE else "broken"


def run(week: str | None = None, *, seed: int | None = None) -> dict:
    week = week or weeks.current_week()
    published = publish.load_week(week)
    if published is None:
        raise FileNotFoundError(f"발행물이 없다: {publish.week_path(week)}")

    session = base.Session()
    result: dict[str, dict] = {}
    for source_id, urls in sorted(sample(published["items"], seed=seed).items()):
        ok = 0
        for url in urls:
            try:
                session.request("HEAD", url)
                ok += 1
            except base.RobotsDisallowed:
                log.info("%s: robots.txt가 이미지 경로를 막는다. 검사하지 않는다", source_id)
                urls = []
                break
            except Exception as exc:          # noqa: BLE001 — 무엇이 나오든 실패로 센다
                log.warning("%s: 열리지 않는다 %s (%s)", source_id, url, exc)
        rate = ok / len(urls) if urls else 0.0
        result[source_id] = {"checked": len(urls), "ok": ok,
                             "pass_rate": round(rate, 2),
                             "verdict": verdict(rate, len(urls))}
        log.info("%-10s %s (%d/%d)", source_id, result[source_id]["verdict"],
                 ok, len(urls))

    broken = [s for s, r in result.items() if r["verdict"] == "broken"]
    if broken:
        log.error("이미지가 통째로 깨진 소스: %s", ", ".join(broken))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="발행물 이미지 표본 검사")
    parser.add_argument("--week", help="생략하면 이번 주")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(args.week)
    # 깨졌으면 비영 종료한다. 배포 전 확인에 쓰려면 실패가 실패로 보여야 한다.
    return 1 if any(r["verdict"] == "broken" for r in result.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
