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

from pipeline import alert, curate, diff, enrich, snapshot, sources, weeks

log = logging.getLogger(__name__)

# ⚠️ 발행물만은 **저장소 안에 남는다.** paths.py 로 옮기지 말 것.
# 요약 + 원문 링크라 공개해도 되는 형태이고(7장), 웹 빌드가 저장소 상대 경로
# (process.cwd()/../data/weeks)로 읽으므로 옮기면 사이트가 깨진다 (ADR-0010).
WEEKS_DIR = Path(__file__).resolve().parent.parent / "data" / "weeks"
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")

# 소스별 부분 산출물. `run()`이 소스마다 여기에 쓰고 `merge()`가 하나로 합친다.
# 한 파일에 소스마다 덮어쓰면 마지막 소스만 남는다 — 발행 단계에서 2.3의 격리가 깨진다.
# 재생성되는 중간물이라 커밋하지 않는다.
PUBLISHED_DIR = Path(__file__).resolve().parent.parent / "data" / "published"

REQUIRED_FIELDS = ("id", "week", "source_id", "brand", "channel", "name", "source_url",
                   "first_seen", "last_seen", "status")


def part_path(week: str, source_id: str) -> Path:
    """소스별 부분 산출물. `merge()`의 입력이다."""
    return PUBLISHED_DIR / week / f"{source_id}.json"


def week_path(week: str) -> Path:
    return WEEKS_DIR / f"{week}.json"


def load_week(week: str) -> dict | None:
    path = week_path(week)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def make_id(source_id: str, external_id: str) -> str:
    return f"{source_id}--{external_id}"


def _publish_item(item: dict, *, week: str, source_id: str, curated: dict,
                  previous: dict | None) -> dict:
    meta = sources.meta(source_id)
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
        # 어느 소스에서 왔는가. 한 주차 파일에 소스가 여럿 들어가므로 필요하다 —
        # external_id는 소스 안에서만 유일하고 소스끼리는 겹칠 수 있다
        # (CU의 gd_idx와 오리온의 goodsno가 둘 다 숫자다).
        "source_id": source_id,
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
    # 자체 분류 목록은 채널마다 다르다 (curate.CATEGORIES_BY_CHANNEL).
    curated = curate.curate(added, enriched, channel=sources.meta(source_id)["channel"])

    # ⚠️ 지난주를 여기서 다시 계산하지 않는다. diff가 실제로 무엇과 비교했는지는
    # diff만 안다 — 한 주 건너뛰었으면 previous_week가 2주 전일 수 있다.
    # 따로 계산하면 diff는 W33과 비교했는데 publish는 W34를 찾는 어긋남이 생긴다.
    previous_week = result["previous_week"]
    previous_publication = (load_week(previous_week) if previous_week else None) or {"items": []}
    # ⚠️ **반드시 소스로 좁힌다.** external_id는 소스 안에서만 유일하다.
    # 좁히지 않으면 오리온 제품이 CU 제품의 id와 first_seen을 물려받는다 —
    # 예외 없이 조용히 틀리고, 그러면 아카이브 URL이 깨진다(ADR-0001).
    previous_by_external = {
        i["external_id"]: i for i in previous_publication["items"]
        if i.get("external_id") and i.get("source_id") == source_id
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
        "source_id": source_id,
        "generated_at": weeks.scraped_at(),
        "counts": _counts(items, discontinued),
        # 지표는 소스 단위로만 계산된다. merge()가 by_source로 모은다.
        "report": _source_report(week, source_id, result, items),
        "items": items,
    }
    path = part_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("발행(부분): %s — 신상 %d / 단종 %d / blurb %d",
             path, payload["counts"]["active"], discontinued,
             payload["counts"]["with_blurb"])
    return path


def _counts(items: list[dict], discontinued: int) -> dict:
    return {
        "total": len(items),
        "active": len(items) - discontinued,
        "discontinued": discontinued,
        "with_blurb": sum(1 for i in items if i.get("blurb")),
    }


def merge(week: str) -> Path | None:
    """소스별 부분 산출물을 사이트가 읽는 파일 하나로 합친다.

    **한 소스가 실패해도 나머지로 합친다** (2.3). 여기서 멈추면 크롤러 하나가 깨졌을 때
    그 주 전체가 발행되지 않는다.

    id 중복 검사는 여기서 한 번 더 돈다. 소스별로는 유일해도 합치면 겹칠 수 있고,
    겹치는 순간 아카이브 URL이 어느 제품을 가리키는지 알 수 없게 된다.
    """
    weeks.parse_week(week)
    part_dir = PUBLISHED_DIR / week
    parts = sorted(part_dir.glob("*.json")) if part_dir.exists() else []
    if not parts:
        log.warning("%s에 합칠 부분 산출물이 없다: %s", week, part_dir)
        return None

    items: list[dict] = []
    by_source: dict[str, dict] = {}
    discontinued = 0
    for part in parts:
        payload = json.loads(part.read_text(encoding="utf-8"))
        items.extend(payload["items"])
        discontinued += payload["counts"]["discontinued"]
        by_source[payload["source_id"]] = payload["report"]

    _validate(items, week)

    merged = {
        "week": week,
        "generated_at": weeks.scraped_at(),
        "sources": sorted(by_source),
        "counts": _counts(items, discontinued),
        "items": items,
    }
    path = week_path(week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "week": week,
        "generated_at": merged["generated_at"],
        "sources": merged["sources"],
        "totals": merged["counts"],
        "by_source": by_source,
    }
    (WEEKS_DIR / f"{week}.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("병합: %s — 소스 %d개 / 신상 %d / 단종 %d",
             path, len(by_source), merged["counts"]["active"], discontinued)
    return path


def _monotonic_key(source_id: str) -> str | None:
    """단조 증가하는 정수 키를 주는 소스만 지표 3을 계산할 수 있다.

    어느 소스가 그런 키를 주는지는 `pipeline/sources.py`의 표에 있다.
    확인되지 않은 소스는 넣지 않는다 — 틀린 지표는 없는 지표보다 나쁘다.
    """
    return sources.monotonic_key(source_id)


def _provenance(current: dict | None, previous_week: str | None,
                previous: dict | None) -> dict:
    """이 발행이 근거로 삼은 스냅샷이 무엇인가 (ADR-0011).

    수집은 봇이, 발행은 사람이 따로 돌린다. 같은 주차를 다시 수집하면 발행물이 본
    카탈로그가 **조용히 교체된다.** 그 시각을 여기 남겨야 나중에 어긋났다는 것을 알 수 있다.
    실제로 2026-W35가 그랬다 — 14:24에 발행하고 15:30에 다시 수집됐다.
    """
    provenance = {
        "scraped_at": (current or {}).get("scraped_at"),
        "count": (current or {}).get("count"),
        "previous_week": previous_week,
        "previous_scraped_at": (previous or {}).get("scraped_at"),
    }
    # 이월본일 때만 싣는다. 해당 없는 자리에 빈 값을 실으면 나중에 의미 있는 값으로
    # 오독된다 — `monotonic_id`를 조건부로 싣는 것과 같은 이유다 (7장).
    held_from = (current or {}).get("held_from")
    if held_from:
        provenance["held_from"] = held_from
    return provenance


def _source_report(week: str, source_id: str, result: dict, items: list[dict]) -> dict:
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
    # 지난주는 diff 결과가 알려준다(run()과 같은 이유).
    previous_week = result.get("previous_week")
    previous = snapshot.load_snapshot(previous_week, source_id) if previous_week else None
    current = snapshot.load_snapshot(week, source_id)
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
        # 몇 주치가 한 번에 잡혔는가. 1이 정상. 이걸 모르면 added 건수를 잘못 읽는다.
        "gap_weeks": result.get("gap_weeks", 1),
        "compared_with": result.get("previous_week"),
        # 무엇을 보고 발행했는가. 지표가 아니라 근거다.
        "snapshot": _provenance(current, previous_week, previous),
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
    # 파일로 쓰지 않는다. merge()가 by_source로 모아서 한 번에 쓴다 —
    # 소스마다 쓰면 <week>.report.json을 서로 덮어써 마지막 소스 것만 남는다.
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="발행용 산출물 생성")
    parser.add_argument("--source", default="cu")
    parser.add_argument("--week", help="생략하면 이번 주")
    parser.add_argument("--merge", action="store_true",
                        help="소스별 부분 산출물을 사이트가 읽는 파일 하나로 합친다. "
                             "소스별 실행이 전부 끝난 뒤 한 번 부른다")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.merge:
        merge(args.week or weeks.current_week())
    else:
        run(args.source, args.week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
