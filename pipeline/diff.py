"""지난주 대비 차집합 계산 (CLAUDE.md 2.1).

소스의 '신상품' 라벨이나 '최신순' 정렬을 쓰지 않는다. 전체 카탈로그 스냅샷 두 개를
비교해서 판정한다. 이 파일에는 소스의 신상 라벨이 들어올 수 없다 —
`snapshot.py`가 `<source_id>.control.json`으로 분리해 두었다.

## 같은 제품인지 어떻게 아는가

계층으로 판정한다. 위쪽일수록 신뢰도가 높고, 아래로 내려갈수록 근거가 약해진다.

    L1  소스 간 대조 키 일치           바코드처럼 여러 소스에 같은 값이 오는 키
    L2  소스 내부 키 일치              소스가 준 나머지 alt_ids, 그리고 external_id
    L3  (정규화 이름, 가격) 완전 일치   키가 전부 바뀌었거나 소스가 키를 안 줄 때
    L4  정규화 이름 유사도 ≥ 0.85      **자동 판정하지 않는다**

키 이름은 소스마다 다르므로 여기에 적지 않는다(CU는 barcode·gd_idx, 오리온은 goodsno,
스타벅스는 product_cd). 어떤 이름이 오든 `_keys()`가 순서를 정한다.

L1~L3에서 매칭되면 그것은 **같은 제품**이다. 이름이나 가격이 달라졌으면 `changed`이지
`added` + `removed`가 아니다. 이름이 한 글자 바뀐 제품이 "단종 1건 + 신상 1건"으로
발행되는 것을 막는 것이 이 계층의 존재 이유다.

L4는 근거가 약해서 **자동으로 병합하지도, 갈라놓지도 않는다.** `review`로 빼서 사람이나
LLM이 보게 한다. 조용히 틀리느니 시끄럽게 미룬다 (2.4).

매칭은 엄격한 1:1이다. 한 번 매칭된 지난주 항목은 소비되어 다시 쓰이지 않는다.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import alert, normalize, paths, snapshot, weeks

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


# 소스 간 대조가 가능한 키. 여러 소스에 같은 제품이 있어도 이 값은 같으므로 가장 믿을 만하다.
CROSS_SOURCE_KEYS = ("barcode",)


def _keys(item: dict) -> list[tuple[str, str]]:
    """이 항목이 가진 매칭 키를 신뢰 순으로 돌려준다.

    소스마다 주는 키가 다르다 — CU는 barcode와 gd_idx, 오리온은 goodsno뿐이다.
    그래서 키 이름을 하드코딩하지 않고 `alt_ids`에 있는 것을 전부 쓴다.
    순서는 소스 간 대조가 되는 키 → 소스 내부 키(이름순) → `external_id` 순이다.

    `external_id`를 마지막에 넣는 이유: `alt_ids`가 비어 있는 소스에서도 매칭이
    되어야 하는데, `external_id`는 소스 카탈로그에서 유일함이 보장된다(4장).
    CU처럼 `external_id`가 `alt_ids`의 값과 같은 소스에서는 앞 계층에서 이미
    매칭되므로 이 항목까지 내려오지 않는다.
    """
    alt = {k: v for k, v in (item.get("alt_ids") or {}).items() if v}
    ordered = [k for k in CROSS_SOURCE_KEYS if k in alt]
    ordered += [k for k in sorted(alt) if k not in CROSS_SOURCE_KEYS]

    found = [(name, str(alt[name])) for name in ordered]
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
    # 지난주 항목을 인덱스 위치로 식별한다(같은 이름·가격이 여럿일 수 있으므로).
    unmatched_previous = set(range(len(previous_items)))
    index: dict[tuple[str, str], list[int]] = {}
    for position, item in enumerate(previous_items):
        for key in _keys(item):
            index.setdefault(key, []).append(position)
        index.setdefault(("name_price", repr(_name_price_key(item))), []).append(position)

    def take(key: tuple[str, str]) -> int | None:
        for position in index.get(key, []):
            if position in unmatched_previous:
                unmatched_previous.discard(position)
                return position
        return None

    matched: list[tuple[dict, dict, str]] = []   # (현재, 지난주, 판정계층)
    conflicts: list[dict] = []
    unmatched_current: list[dict] = []

    for item in current_items:
        position = None
        layer = ""
        for key_name, value in _keys(item):
            position = take((key_name, value))
            if position is not None:
                layer = key_name
                break
        if position is None:
            position = take(("name_price", repr(_name_price_key(item))))
            layer = "name_price" if position is not None else ""

        if position is None:
            unmatched_current.append(item)
            continue

        previous = previous_items[position]
        matched.append((item, previous, layer))

        # 한 키로는 이어졌는데 다른 키가 어긋나면 조용히 넘기지 않는다.
        for key_name, value in _keys(item):
            other = (previous.get("alt_ids") or {}).get(key_name)
            if other and other != value:
                conflicts.append({
                    "matched_by": layer,
                    "conflicting_key": key_name,
                    "previous": other,
                    "current": value,
                    "name": item["name"],
                })

    review = _pair_by_similarity(unmatched_current, previous_items, unmatched_previous)
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
        log.warning("L4 유사도 비교를 건너뛴다: 후보 쌍이 %d개로 너무 많다 "
                    "(현재 %d × 지난주 %d). 상위 계층 매칭이 대량으로 실패했다는 뜻이다.",
                    pair_count, len(unmatched_current), len(unmatched_previous))
        return []

    candidates = []
    for item in unmatched_current:
        current_name = normalize.normalize_name(item["name"])
        for position in unmatched_previous:
            previous = previous_items[position]
            if previous.get("category_raw") != item.get("category_raw"):
                continue  # 카테고리가 다르면 같은 제품으로 보지 않는다
            score = normalize.similarity(current_name,
                                         normalize.normalize_name(previous["name"]))
            if score >= SIMILARITY_THRESHOLD:
                candidates.append((score, item, position))

    # 점수가 높은 쌍부터 1:1로 짝짓는다.
    candidates.sort(key=lambda c: c[0], reverse=True)
    used_current: set[int] = set()
    review = []
    for score, item, position in candidates:
        if id(item) in used_current or position not in unmatched_previous:
            continue
        used_current.add(id(item))
        unmatched_previous.discard(position)
        review.append({
            "current": item,
            "previous": previous_items[position],
            "similarity": round(score, 4),
            "fields": _changed_fields(item, previous_items[position]),
        })
    return review


def _gap(previous_week: str, week: str) -> int:
    """두 주차가 몇 주 떨어져 있는가. 연도 경계를 넘어도 맞아야 해서 날짜로 센다."""
    delta = weeks.monday_of(week) - weeks.monday_of(previous_week)
    return delta.days // 7


# 되짚기는 snapshot.py가 갖는다. 검증·이월·diff가 서로 다른 주차를 보면
# "무엇과 비교했는가"가 어긋나므로 한 곳에서만 정한다.
MAX_LOOKBACK_WEEKS = snapshot.MAX_LOOKBACK_WEEKS

def run(source_id: str, week: str | None = None) -> Path:
    week = week or weeks.current_week()

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
    if previous is None:
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
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

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
