"""diff가 걸러낸 신상만 상세 페이지로 보강한다 (CLAUDE.md 3장).

목록 페이지는 이름·가격·이미지까지만 준다. 설명문과 태그는 상세 페이지에만 있다.
전체 카탈로그의 상세를 매주 긁으면 5,100요청이라 불가능하지만, **신상 수십~수백 건만은
감당 가능하다.** 이 단계가 있어야 `curate.py`가 blurb를 창작하지 않고 요약만 하게 된다(6장).

출력: `data/enriched/<week>/<source_id>.json` — {external_id: {description, tags}}
실패한 항목은 그냥 빠진다. 보강은 있으면 좋은 것이지 발행을 막을 이유가 아니다.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import diff, weeks
from scrapers import base

log = logging.getLogger(__name__)

ENRICHED_DIR = Path(__file__).resolve().parent.parent / "data" / "enriched"


def enriched_path(week: str, source_id: str) -> Path:
    return ENRICHED_DIR / week / f"{source_id}.json"


def load_enriched(week: str, source_id: str) -> dict:
    path = enriched_path(week, source_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _detail_fetcher(source_id: str):
    if source_id == "cu":
        from scrapers import cu
        return cu.fetch_detail
    raise ValueError(f"상세 조회를 지원하지 않는 소스: {source_id!r}")


def run(source_id: str, week: str | None = None) -> Path:
    week = week or weeks.current_week()
    diff_path = diff.DIFF_DIR / week / f"{source_id}.json"
    if not diff_path.exists():
        raise FileNotFoundError(
            f"diff 결과가 없다: {diff_path}\n먼저 `python -m pipeline.diff`를 돌릴 것.")

    result = json.loads(diff_path.read_text(encoding="utf-8"))
    added = result["added"]
    if not added:
        log.info("신상이 없어 보강할 것이 없다.")

    fetch_detail = _detail_fetcher(source_id)
    session = base.Session()
    enriched: dict[str, dict] = {}
    failures = 0

    for index, item in enumerate(added, start=1):
        gd_idx = (item.get("alt_ids") or {}).get("gd_idx")
        if not gd_idx:
            log.warning("gd_idx가 없어 건너뛴다: %s", item["name"])
            continue
        try:
            detail = fetch_detail(session, gd_idx, week=week)
        except base.FetchError as exc:
            # 보강 실패는 발행을 막지 않는다. 다만 조용히 넘기지도 않는다.
            failures += 1
            log.error("상세 조회 실패 (%s / %s): %s", item["name"], gd_idx, exc)
            continue

        if detail["name"] and detail["name"] != item["name"]:
            # 목록과 상세의 이름이 다르면 gd_idx 매핑이 틀렸다는 뜻이다.
            log.error("이름 불일치 — 목록 %r vs 상세 %r (gdIdx=%s). 이 항목은 보강하지 않는다.",
                      item["name"], detail["name"], gd_idx)
            failures += 1
            continue

        enriched[item["external_id"]] = {
            "description": detail["description"],
            "tags": detail["tags"],
        }
        log.info("  [%d/%d] %s — 설명 %s / 태그 %d개", index, len(added), item["name"],
                 "있음" if detail["description"] else "없음", len(detail["tags"]))

    path = enriched_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

    with_description = sum(1 for v in enriched.values() if v["description"])
    log.info("보강 완료: 신상 %d건 중 %d건 (설명문 확보 %d건, 실패 %d건) → %s",
             len(added), len(enriched), with_description, failures, path)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="신상 항목 상세 보강")
    parser.add_argument("--source", default="cu")
    parser.add_argument("--week", help="생략하면 이번 주")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.source, args.week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
