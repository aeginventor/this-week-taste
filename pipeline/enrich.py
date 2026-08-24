"""diff가 걸러낸 신상만 상세 페이지로 보강한다 (CLAUDE.md 3장).

CU는 목록이 이름·가격·이미지까지만 준다. 설명문과 태그는 상세 페이지에만 있다.
전체 카탈로그의 상세를 매주 긁으면 5,100요청이라 불가능하지만, **신상 수십~수백 건만은
감당 가능하다.** 이 단계가 있어야 `curate.py`가 blurb를 창작하지 않고 요약만 하게 된다(6장).

**상세를 긁지 않는 소스가 두 종류 있다.** 둘 다 `pipeline/sources.py`의 `detail`이 False다.

  이미 있어서   스타벅스. 목록 응답이 326건 전부에 설명문을 준다. 스냅샷의
                `description`을 그대로 쓴다(4장). 이미 가진 것을 버리고 다시 긁는 것은
                소스 서버에 대한 예의도 아니다.
  거기에도 없어서 홈플러스. 상세의 `itemDesc`가 거의 전부 `<img>` 한 줄이다
                (표본 51건 중 텍스트 1건). 긁어도 얻을 것이 없으므로 요청하지 않는다.
                `description`은 없는 채로 남고, `blurb`는 `null`로 발행된다(6장).

두 번째가 중요하다 — **설명문이 없는 것은 실패가 아니라 그 소스의 성질이다.**
실패로 취급하면 매주 실패 카운트가 신상 건수만큼 쌓여 2.4의 경보가 무의미해진다.

출력: `data/enriched/<week>/<source_id>.json` — {external_id: {description, tags}}
실패한 항목은 그냥 빠진다. 보강은 있으면 좋은 것이지 발행을 막을 이유가 아니다.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import alert, diff, paths, sources, weeks
from scrapers import base

log = logging.getLogger(__name__)

ENRICHED_DIR = paths.ENRICHED_DIR

# 상세 조회 요청 수의 상한. 신상 하나마다 요청이 한 번 더 나가므로 여기가
# 이 파이프라인에서 요청량이 튈 수 있는 유일한 자리다(목록 요청 수는 고정이다).
#
# 상한을 두는 진짜 이유는 예의가 아니라 **신호**다. 신상이 수백 건이라는 것은
# 그 자체로 diff 매칭이 깨졌다는 뜻이고(8장 판단표), 그 상태로 긁으면
# 버그가 소스 사이트를 대신 두들긴다.
#
# ⚠️ 이 값에는 아직 실측 근거가 없다. 진짜 한 주치 신상이 몇 건인지 본 적이 없다.
# 첫 실제 diff를 본 뒤 조인다.
MAX_DETAIL_FETCHES = 500


def enriched_path(week: str, source_id: str) -> Path:
    return ENRICHED_DIR / week / f"{source_id}.json"


def load_enriched(week: str, source_id: str) -> dict:
    path = enriched_path(week, source_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(week: str, source_id: str, enriched: dict, *, failures: int, total: int) -> Path:
    path = enriched_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

    with_description = sum(1 for v in enriched.values() if v["description"])
    log.info("보강 완료: 신상 %d건 중 %d건 (설명문 확보 %d건, 실패 %d건) → %s",
             total, len(enriched), with_description, failures, path)
    return path


def _detail_fetcher(source_id: str):
    """상세 조회 함수. 상세를 긁지 않는 소스는 None이다 (모듈 docstring 참조)."""
    return sources.detail_fetcher(source_id)


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

    # 목록이 이미 설명문을 준 항목은 상세를 긁지 않는다 (4장 `description`).
    enriched: dict[str, dict] = {}
    from_list = [i for i in added if (i.get("description") or "").strip()]
    for item in from_list:
        enriched[item["external_id"]] = {"description": item["description"], "tags": []}
    if from_list:
        log.info("목록에 설명문이 있어 상세를 긁지 않는 항목: %d/%d건",
                 len(from_list), len(added))

    total = len(added)
    added = [i for i in added if i["external_id"] not in enriched]
    if not added:
        return _write(week, source_id, enriched, failures=0, total=total)

    fetch_detail = _detail_fetcher(source_id)
    if fetch_detail is None:
        # 상세를 긁지 않는 소스다. 실패로 세지 않는다 — 이건 사고가 아니라 성질이다.
        # 다만 남은 항목이 있다는 것은 기록한다. 스타벅스처럼 "목록이 다 준다"고
        # 믿었던 소스에서 이 줄이 보이면 그 전제가 깨졌다는 신호다.
        log.info("상세를 긁지 않는 소스다(sources.py의 detail=False). "
                 "설명문 없이 남는 항목 %d/%d건 — blurb는 null로 발행된다.",
                 len(added), total)
        return _write(week, source_id, enriched, failures=0, total=total)

    # ⚠️ 잘라서 일부만 긁지 않는다. 그러면 "왜 어떤 건 blurb가 있고 어떤 건 없나"가
    # 설명이 안 되는 발행물이 나간다. 조용히 절반만 하느니 시끄럽게 멈춘다(2.4).
    if len(added) > MAX_DETAIL_FETCHES:
        alert.raise_anomaly(
            f"[{source_id}] {week} 상세 조회 대상이 상한을 넘었다: "
            f"{len(added)}건 > {MAX_DETAIL_FETCHES}건",
            "신상이 이만큼 나오는 것은 diff 매칭이 깨졌다는 신호다(8장 판단표).\n"
            "상세를 긁지 않고 멈춘다 — 이 상태로 긁으면 버그가 소스 사이트를 두들긴다.\n"
            f"diff 결과를 먼저 확인할 것: {diff_path}")

    session = base.Session()
    failures = 0

    for index, item in enumerate(added, start=1):
        # 소스마다 상세 조회 키가 다르다(CU는 gd_idx, 오리온은 goodsno). 그런데 어느
        # 소스든 `external_id`가 그 키이므로(4장) 이것 하나로 통일한다. 키 이름을
        # 하드코딩하면 새 소스의 항목이 통째로 건너뛰어진다.
        key = item.get("external_id")
        if not key:
            log.warning("external_id가 없어 건너뛴다: %s", item["name"])
            continue
        try:
            detail = fetch_detail(session, key, week=week)
        except base.FetchError as exc:
            # 보강 실패는 발행을 막지 않는다. 다만 조용히 넘기지도 않는다.
            failures += 1
            log.error("상세 조회 실패 (%s / %s): %s", item["name"], key, exc)
            continue

        if detail["name"] and detail["name"] != item["name"]:
            # 목록과 상세의 이름이 다르면 키 매핑이 틀렸다는 뜻이다.
            log.error("이름 불일치 — 목록 %r vs 상세 %r (키=%s). 이 항목은 보강하지 않는다.",
                      item["name"], detail["name"], key)
            failures += 1
            continue

        enriched[item["external_id"]] = {
            "description": detail["description"],
            "tags": detail["tags"],
        }
        log.info("  [%d/%d] %s — 설명 %s / 태그 %d개", index, len(added), item["name"],
                 "있음" if detail["description"] else "없음", len(detail["tags"]))

    return _write(week, source_id, enriched, failures=failures, total=total)


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
