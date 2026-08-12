"""발행용 최종 산출물 생성 → `data/weeks/<week>.json` (CLAUDE.md 4장).

사이트가 읽는 파일은 이것 하나다.

## id는 한 번 정해지면 바뀌지 않는다

    <source_id>--<external_id>

`external_id`는 소스 카탈로그에서 유일한 키다(4장). 어떤 키를 쓸지는 소스별로 다르고
`scrapers/`가 정한다 — 이 파일은 그것이 무엇인지 몰라도 된다.

`first_seen` 주차에 확정하고 이후 절대 바꾸지 않는다. 나중에 더 좋은 키를 알게 돼도
지난주 발행본의 id를 그대로 이월한다. id가 바뀌면 아카이브 URL이 깨지고, diff가 같은 제품을
"단종 1건 + 신상 1건"으로 오탐한다. 실제로 CU에서 주키를 바꾼 적이 있다([ADR-0001]).

[ADR-0001]: ../docs/adr/0001-product-id.md

## 단종 항목은 이월로만 실릴 수 있다

`status: discontinued`인 항목은 이번 주 스냅샷에 없다. 지난주 발행본에서 가져오는 것이
유일한 경로다.

## 첫 주는 발행하지 않는다

지난주 스냅샷이 없으면 diff가 성립하지 않는다. 기준선만 만들고 끝낸다.
5,100건을 전부 신상으로 발행하는 일은 어떤 경우에도 없다.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from pipeline import alert, curate, diff, enrich, snapshot, weeks

log = logging.getLogger(__name__)

WEEKS_DIR = Path(__file__).resolve().parent.parent / "data" / "weeks"
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")

BRANDS = {
    "cu": {"brand": "CU", "channel": "convenience"},
    "orion": {"brand": "오리온", "channel": "fmcg"},
    "starbucks": {"brand": "스타벅스", "channel": "cafe"},
}
REQUIRED_FIELDS = ("id", "week", "brand", "channel", "name", "source_url",
                   "first_seen", "last_seen", "status")


def week_path(week: str) -> Path:
    return WEEKS_DIR / f"{week}.json"


def load_week(week: str) -> dict | None:
    path = week_path(week)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def make_id(source_id: str, external_id: str) -> str:
    return f"{source_id}--{external_id}"


def _publish_item(item: dict, *, week: str, source_id: str, curated: dict,
                  previous: dict | None) -> dict:
    meta = BRANDS[source_id]
    edit = curated.get(item["external_id"]) or {}
    return {
        # id와 first_seen은 지난주 발행본이 있으면 그것을 이월한다.
        "id": (previous or {}).get("id") or make_id(source_id, item["external_id"]),
        "week": week,
        "brand": meta["brand"],
        "channel": meta["channel"],
        "name": item["name"],
        "price": item.get("price"),
        "category": edit.get("category") or item.get("category_raw"),
        "tags": edit.get("tags") or [],
        "blurb": edit.get("blurb"),
        "image_url": item.get("image_url"),
        "source_url": item.get("source_url"),
        "external_id": item["external_id"],
        "alt_ids": item.get("alt_ids") or {},
        "first_seen": (previous or {}).get("first_seen") or week,
        "last_seen": week,
        "status": "active",
    }


def _validate(items: list[dict], week: str) -> None:
    problems = []
    if not WEEK_RE.match(week):
        problems.append(f"주차 형식이 아니다: {week!r}")

    ids = [i["id"] for i in items]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        problems.append(f"id 중복: {sorted(duplicates)[:10]}")

    for item in items:
        missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
        if missing:
            problems.append(f"{item.get('name', '?')}: 필수 필드 누락 {missing}")
        if item["week"] != week:
            problems.append(f"{item['id']}: week가 {item['week']} (기대 {week})")

    if problems:
        alert.raise_anomaly(f"[{week}] 발행 스키마 검증 실패",
                            "\n".join(problems[:20]))


def run(source_id: str, week: str | None = None) -> Path | None:
    week = week or weeks.current_week()
    weeks.parse_week(week)  # 형식 검증

    diff_path = diff.DIFF_DIR / week / f"{source_id}.json"
    if not diff_path.exists():
        raise FileNotFoundError(
            f"diff 결과가 없다: {diff_path}\n먼저 `python -m pipeline.diff`를 돌릴 것.")
    result = json.loads(diff_path.read_text(encoding="utf-8"))

    if result.get("baseline"):
        log.warning("%s는 기준선(baseline)이라 발행하지 않는다. 다음 주부터 diff가 의미를 갖는다.",
                    week)
        return None

    enriched = enrich.load_enriched(week, source_id)
    added = result["added"]
    curated = curate.curate(added, enriched)

    previous_week = weeks.previous_week(week)
    previous_publication = load_week(previous_week) or {"items": []}
    previous_by_external = {
        i["external_id"]: i for i in previous_publication["items"] if i.get("external_id")
    }

    items = [
        _publish_item(item, week=week, source_id=source_id, curated=curated,
                      previous=previous_by_external.get(item["external_id"]))
        for item in added
    ]

    # 단종 후보는 지난주 발행본에서 이월한다. 이번 주 스냅샷에는 없기 때문이다.
    discontinued = 0
    for removed in result["removed"]:
        previous = previous_by_external.get(removed["external_id"])
        if not previous:
            continue  # 지난주에 발행되지 않았던 항목(신상으로 잡힌 적이 없음)
        items.append({**previous, "week": week, "last_seen": previous_week,
                      "status": "discontinued"})
        discontinued += 1

    _validate(items, week)

    payload = {
        "week": week,
        "generated_at": weeks.scraped_at(),
        "counts": {
            "total": len(items),
            "active": len(items) - discontinued,
            "discontinued": discontinued,
            "with_blurb": sum(1 for i in items if i.get("blurb")),
        },
        "items": items,
    }
    path = week_path(week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_report(week, source_id, result, items)
    log.info("발행: %s — 신상 %d / 단종 %d / blurb %d",
             path, payload["counts"]["active"], discontinued, payload["counts"]["with_blurb"])
    return path


def _monotonic_key(source_id: str) -> str | None:
    """단조 증가하는 정수 키를 주는 소스만 지표 3을 계산할 수 있다.

    CU의 `gd_idx`는 자동 증가라 "신상은 지난주 최댓값보다 크다"가 성립한다.
    오리온의 `goodsno`도 정수지만 목록이 오름차순이 아니라 확인이 더 필요하고,
    스타벅스의 `product_cd`는 13자리 상품코드라 증가 순서가 아니다.
    확인되지 않은 소스는 넣지 않는다 — 틀린 지표는 없는 지표보다 나쁘다.
    """
    return {"cu": "gd_idx"}.get(source_id)


def _write_report(week: str, source_id: str, result: dict, items: list[dict]) -> None:
    """2주 검증용 지표 (계획 5절). **added 건수가 아니라 오탐 비율을 본다.**

    소스의 NEW 라벨은 판정에 쓰지 않지만(2.1) 검증 지표로는 쓴다. 라벨과의 교집합이
    작으면 오탐을, NEW인데 added에 없으면 누락을 의심한다.
    """
    control = {}
    control_path = snapshot.control_path(week, source_id)
    if control_path.exists():
        control = json.loads(control_path.read_text(encoding="utf-8"))

    added = result["added"]
    labelled_new = {k for k, v in control.items() if (v.get("labels") or {}).get("new")}
    added_ids = {i["external_id"] for i in added}

    # 지표 3은 **단조 증가하는 정수 키를 주는 소스에만** 성립한다. CU의 gd_idx가 그렇다.
    # 그런 키가 없는 소스에서 이 지표를 그대로 계산하면 previous_max가 0이 되어
    # 전량이 "등록 순서를 거스름"으로 보고된다 — 없는 오탐을 만들어낸다.
    previous = snapshot.load_snapshot(weeks.previous_week(week), source_id)
    monotonic_key = _monotonic_key(source_id)
    if monotonic_key:
        previous_max_gd = max(
            (int(i["alt_ids"][monotonic_key]) for i in (previous or {}).get("items", [])
             if str((i.get("alt_ids") or {}).get(monotonic_key, "")).isdigit()), default=0)
        above_previous_max = sum(
            1 for i in added
            if str((i.get("alt_ids") or {}).get(monotonic_key, "")).isdigit()
            and int(i["alt_ids"][monotonic_key]) > previous_max_gd)

    report = {
        "week": week,
        "source_id": source_id,
        "diff_counts": result["counts"],
        # 지표 1: added 절대 건수. 수천이면 매칭이 깨진 것이다.
        "added": len(added),
        # 지표 2: 소스 NEW 라벨과의 교차 검증 (대조군)
        "source_new_label": {
            "labelled_total": len(labelled_new),
            "labelled_and_added": len(labelled_new & added_ids),
            "labelled_not_added": len(labelled_new - added_ids),
            "added_not_labelled": len(added_ids - labelled_new),
        },
    }
    # 지표 3: 단조 증가 키. 목록이 오름차순이면 신상은 지난주 최댓값보다 커야 한다.
    # 그런 키가 없는 소스에서는 아예 싣지 않는다 — 빈 값을 실으면 0을 오탐으로 읽는다.
    if monotonic_key:
        report["monotonic_id"] = {
            "key": monotonic_key,
            "previous_max": previous_max_gd,
            "added_above_previous_max": above_previous_max,
            "added_below_previous_max": len(added) - above_previous_max,
        }
    report["published"] = {"total": len(items),
                           "with_blurb": sum(1 for i in items if i.get("blurb"))}

    path = WEEKS_DIR / f"{week}.report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("검증 지표: %s", path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="발행용 산출물 생성")
    parser.add_argument("--source", default="cu")
    parser.add_argument("--week", help="생략하면 이번 주")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.source, args.week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
