"""지난주 대비 차집합 계산 (CLAUDE.md 2.1).

소스의 '신상품' 라벨이나 '최신순' 정렬을 쓰지 않는다. 전체 카탈로그 스냅샷 두 개를
비교해서 판정한다. 이 파일에는 소스의 신상 라벨이 들어올 수 없다 —
`snapshot.py`가 `<source_id>.control.json`으로 분리해 두었다.

## 같은 카탈로그 항목을 어떻게 연결하는가

계층으로 판정한다. 위쪽일수록 신뢰도가 높고, 아래로 내려갈수록 근거가 약해진다.

    L1  카탈로그 항목 키 일치          external_id를 전체 입력에서 먼저 매칭
    L2  유일한 보조 키 연결            양쪽에서 하나로 정해질 때만 매칭
    L3  (정규화 이름, 알려진 가격)     양쪽에서 하나로 정해질 때만 매칭
    L4  정규화 이름 유사도 ≥ 0.85      **자동 판정하지 않는다**

키 이름은 소스마다 다르므로 여기에 적지 않는다(CU는 barcode·gd_idx, 오리온은 goodsno,
스타벅스는 product_cd). 보조 키 이름과 값은 동적으로 읽는다.

L1~L3에서 연결된 카탈로그 항목의 이름이나 가격이 달라졌으면 `changed`이지
`added` + `removed`가 아니다. 이름이 한 글자 바뀐 제품이 "단종 1건 + 신상 1건"으로
발행되는 것을 막는 것이 이 계층의 존재 이유다.

L4는 근거가 약해서 **자동으로 병합하지도, 갈라놓지도 않는다.** `review`로 빼서 사람이나
추가 근거로 검증하게 한다. 현재 자동 해소 경로는 없다.

확정 매칭은 엄격한 1:1이다. review의 candidates는 가능한 연결을 모두 보존한다.
이 단계는 출시 여부를 판별하지 않는다 (ADR-0018).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import provenance, alert, normalize, paths, snapshot, weeks

log = logging.getLogger(__name__)

DIFF_DIR = paths.DIFF_DIR

# 이름이 짧아서 문턱을 낮게 잡아야 한다. CU는 제품명을 12자에서 자르므로,
# n자 이름에서 한 글자만 바뀌어도 유사도가 1 - 1/n 까지 떨어진다:
#     12자 → 0.917    10자 → 0.900    8자 → 0.875    7자 → 0.857
# 0.92로 두면 "한 글자 바뀐 12자 이름"조차 후보에 들지 못한다(실측 0.9167).
# 0.85면 7자 이상 이름의 한 글자 변경까지 잡고, 두 글자 변경(12자 기준 0.833)은 뺀다.
SIMILARITY_THRESHOLD = 0.85
# L4는 짝짓기가 O(n×m)이라 폭발할 수 있다. 이 규모를 넘으면 계산하지 않고 알린다.
L4_PAIR_LIMIT = 2_000_000

# 되짚기는 snapshot.py가 갖는다. 검증·이월·diff가 서로 다른 주차를 보면
# "무엇과 비교했는가"가 어긋나므로 한 곳에서만 정한다.
MAX_LOOKBACK_WEEKS = snapshot.MAX_LOOKBACK_WEEKS

# 값이 달라졌을 때 `changed`로 기록할 필드
TRACKED_FIELDS = ("name", "price", "image_url", "category_raw")


def _keys(item: dict) -> list[tuple[str, str]]:
    """키를 문자열로 통일한다. 정렬은 재현용이며 매칭 우선순위가 아니다.

    external_id의 전체 매칭은 diff_items가 먼저 수행한다. 보조 키는 특정 키를
    먼저 소비하지 않고 연결 후보를 모두 만든 뒤 유일성을 검사한다.
    """
    alt = {k: v for k, v in (item.get("alt_ids") or {}).items() if v}
    found = [(name, str(alt[name])) for name in sorted(alt)]
    if item.get("external_id"):
        found.append(("external_id", str(item["external_id"])))
    return found


def _name_price_key(item: dict) -> tuple[str, object]:
    return (normalize.normalize_name(item["name"]), item.get("price"))


def _changed_fields(current: dict, previous: dict) -> dict:
    return {
        field: {"from": previous.get(field), "to": current.get(field)}
        for field in TRACKED_FIELDS
        if current.get(field) != previous.get(field)
    }


def diff_items(previous_items: list[dict], current_items: list[dict]) -> dict:
    """스냅샷 항목 두 묶음을 비교한다. 파일 입출력 없이 순수 계산만 한다."""
    # 카탈로그 항목을 먼저 고정한다. 새 등록이 기존 항목의 바코드를 먼저 소비하면
    # 같은 입력도 순서에 따라 옛 번호가 added가 된다 (ADR-0018, W36 CU 실측).
    order = lambda item: (str(item.get("source_id", "")), str(item["external_id"]))
    previous_items = sorted(previous_items, key=order)
    current_items = sorted(current_items, key=order)
    for label, items in (("previous", previous_items), ("current", current_items)):
        keys = [order(item) for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{label}: duplicate external_id")
    unmatched_previous = set(range(len(previous_items)))
    unmatched_current_positions = set(range(len(current_items)))
    matched = []
    conflicts = []
    ambiguous = []

    def match(ci, pi, layer):
        current, previous = current_items[ci], previous_items[pi]
        unmatched_current_positions.remove(ci)
        unmatched_previous.remove(pi)
        matched.append((current, previous, layer))
        for key_name, value in _keys(current):
            other = (previous.get("alt_ids") or {}).get(key_name)
            if other and str(other) != value:
                conflicts.append({"matched_by": layer, "conflicting_key": key_name,
                                  "previous": other, "current": value,
                                  "name": current["name"]})

    primary = {order(item): pi for pi, item in enumerate(previous_items)}
    for ci, item in enumerate(current_items):
        pi = primary.get(order(item))
        if pi is not None:
            match(ci, pi, "external_id")

    def stage(keys_for, default_layer):
        index = {}
        for pi in sorted(unmatched_previous):
            for key in keys_for(previous_items[pi]):
                index.setdefault(key, set()).add(pi)
        edges, layers, reverse = {}, {}, {}
        for ci in sorted(unmatched_current_positions):
            for key in keys_for(current_items[ci]):
                for pi in sorted(index.get(key, ())):
                    edges.setdefault(ci, set()).add(pi)
                    layers.setdefault((ci, pi), key[1] if default_layer is None else default_layer)
                    reverse.setdefault(pi, set()).add(ci)
        # 양쪽에서 유일한 연결만 확정한다. 모호한 키를 더 약한 근거로 추측하지 않는다.
        for ci, positions in sorted(edges.items()):
            if len(positions) == 1 and len(reverse[next(iter(positions))]) == 1:
                pi = next(iter(positions))
                match(ci, pi, layers[ci, pi])
            else:
                candidates = [previous_items[pi] for pi in sorted(positions)]
                ambiguous.append({"current": current_items[ci], "previous": candidates[0],
                                  "candidates": candidates, "reason": "ambiguous_" + (default_layer or "keys"),
                                  "fields": _changed_fields(current_items[ci], candidates[0])})
                unmatched_current_positions.discard(ci)
        for pair in ambiguous:
            for candidate in pair["candidates"]:
                unmatched_previous.discard(primary[order(candidate)])

    def alias_keys(item):
        return [(str(item.get("source_id", "")), key, value)
                for key, value in _keys(item) if key != "external_id"]

    def name_price_keys(item):
        # 가격 미상끼리는 일치 근거가 아니다. 이름뿐이면 L4에서 보류한다.
        return ([(str(item.get("source_id", "")), "name_price", repr(_name_price_key(item)))]
                if item.get("price") is not None else [])

    stage(alias_keys, None)
    stage(name_price_keys, "name_price")
    unmatched_current = [current_items[ci] for ci in sorted(unmatched_current_positions)]

    review = ambiguous + _pair_by_similarity(unmatched_current, previous_items, unmatched_previous)
    reviewed_current = {id(pair["current"]) for pair in review}

    added = [item for item in unmatched_current if id(item) not in reviewed_current]
    removed = [previous_items[position] for position in sorted(unmatched_previous)]

    changed = [
        {"item": current, "previous": previous, "matched_by": layer,
         "fields": _changed_fields(current, previous)}
        for current, previous, layer in matched
        if _changed_fields(current, previous)
    ]

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "review": review,
        "conflicts": conflicts,
        "counts": {
            "previous": len(previous_items),
            "current": len(current_items),
            "matched": len(matched),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "review": len(review),
            "conflicts": len(conflicts),
        },
    }


def _pair_by_similarity(unmatched_current: list[dict], previous_items: list[dict],
                        unmatched_previous: set[int]) -> list[dict]:
    """L4. 확신할 수 없는 쌍을 찾아 `review`로 뺀다. added/removed에 넣지 않는다."""
    if not unmatched_current or not unmatched_previous:
        return []

    pair_count = len(unmatched_current) * len(unmatched_previous)
    if pair_count > L4_PAIR_LIMIT:
        raise alert.PipelineAnomaly(
            f"L4 비교 한도 초과: {pair_count}쌍. 검증하지 않은 후보를 added로 발행하지 않는다.")

    candidates = []
    for item in unmatched_current:
        current_name = normalize.normalize_name(item["name"])
        for position in unmatched_previous:
            previous = previous_items[position]
            if previous.get("source_id") != item.get("source_id"):
                continue
            if previous.get("category_raw") != item.get("category_raw"):
                continue  # 카테고리가 다르면 같은 제품으로 보지 않는다
            score = normalize.similarity(current_name,
                                         normalize.normalize_name(previous["name"]))
            if score >= SIMILARITY_THRESHOLD:
                candidates.append((score, item, position))

    # 한 옛 항목에 비슷한 새 항목이 여럿이면 모두 보류한다. 첫 항목이 옛 항목을
    # 소비하고 나머지가 added가 되던 경로를 막는다. 자동 매칭과 보류는 다르다.
    candidates.sort(key=lambda c: (-c[0], str(c[1]["external_id"]), c[2]))
    by_current = {}
    for score, item, position in candidates:
        by_current.setdefault(id(item), []).append((score, item, position))
    review = []
    for pairs in by_current.values():
        score, item, position = pairs[0]
        for _, _, pi in pairs:
            unmatched_previous.discard(pi)
        review.append({
            "current": item,
            "previous": previous_items[position],
            "candidates": [previous_items[pi] for _, _, pi in pairs],
            "reason": "similar_name",
            "similarity": round(score, 4),
            "fields": _changed_fields(item, previous_items[position]),
        })
    return sorted(review, key=lambda pair: str(pair["current"]["external_id"]))


def _gap(previous_week: str, week: str) -> int:
    """두 주차가 몇 주 떨어져 있는가. 연도 경계를 넘어도 맞아야 해서 날짜로 센다."""
    delta = weeks.monday_of(week) - weeks.monday_of(previous_week)
    return delta.days // 7


# 되짚기는 snapshot.py가 갖는다. 검증·이월·diff가 서로 다른 주차를 보면
# "무엇과 비교했는가"가 어긋나므로 한 곳에서만 정한다.
MAX_LOOKBACK_WEEKS = snapshot.MAX_LOOKBACK_WEEKS

def run(source_id: str, week: str | None = None) -> Path:
    week = week or weeks.current_week()

    inputs = provenance.observation_inputs(source_id, week)
    current = snapshot.load_snapshot(week, source_id)
    if current is None:
        raise FileNotFoundError(
            f"이번 주 스냅샷이 없다: {snapshot.snapshot_path(week, source_id)}\n"
            "먼저 `python -m pipeline.snapshot`을 돌릴 것.")

    previous_week, previous = snapshot.previous_available(source_id, week)
    if previous is not None and previous_week != weeks.previous_week(week):
        log.warning("%s의 직전 주 스냅샷이 없어 %s와 비교한다. "
                    "이번 주 신상이 아니라 여러 주치가 한 번에 잡힌다.",
                    source_id, previous_week)
    if previous is None or current.get("held_from"):
        # 첫 주는 발행하지 않는다. 전량을 신상으로 내보내는 일은 어떤 경우에도 하지 않는다.
        log.warning("%s 이전 %d주 안에 스냅샷이 없다. %s는 기준선(baseline)으로만 쓰고 "
                    "발행하지 않는다.", source_id, MAX_LOOKBACK_WEEKS, week)
        result = {"added": [], "removed": [], "changed": [], "review": [], "conflicts": [],
                  "counts": {"previous": 0, "current": current["count"], "matched": 0,
                             "added": 0, "removed": 0, "changed": 0, "review": 0,
                             "conflicts": 0},
                  "baseline": True}
    else:
        result = diff_items(previous["items"], current["items"])
        result["baseline"] = False

    # gap_weeks: 몇 주치가 한 번에 잡혔는가. 1이 정상이다.
    # 이것 없이 added 건수만 보면 2주치를 한 주치인 척 읽게 된다.
    gap = 0 if previous_week is None else _gap(previous_week, week)
    result = {"source_id": source_id, "week": week, "previous_week": previous_week,
              "gap_weeks": gap, **result}

    path = DIFF_DIR / week / f"{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    provenance.check_observations(inputs, provenance.observation_inputs(source_id, week))
    provenance.atomic_json(path, provenance.seal(result, inputs))

    counts = result["counts"]
    log.info("diff %s %s → %s: 신상 %d / 단종후보 %d / 변경 %d / 보류 %d (매칭 %d, 키충돌 %d)",
             source_id, previous_week, week, counts["added"], counts["removed"],
             counts["changed"], counts["review"], counts["matched"], counts["conflicts"])
    if result["conflicts"]:
        alert.notify(
            f"[{source_id}] {week} 키 충돌 {len(result['conflicts'])}건",
            "한 키로는 같은 제품인데 다른 키가 어긋난다. 소스가 상품 코드를 재발급했을 수 있다.\n"
            + json.dumps(result["conflicts"][:20], ensure_ascii=False, indent=2))
    log.info("저장: %s", path)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="지난주 대비 차집합")
    parser.add_argument("--source", default="cu")
    parser.add_argument("--week", help="생략하면 이번 주")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.source, args.week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
