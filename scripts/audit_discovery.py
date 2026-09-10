"""저장된 관측으로 판별 전후를 비교한다. 네트워크·발행·파일 쓰기를 수행하지 않는다.

예: THIS_WEEK_TASTE_DATA_DIR=/비공개/데이터 .venv/bin/python -m scripts.audit_discovery
변경 전 diff.py 사본을 --before로 주면 같은 입력으로 실행한다. 결과는 stdout JSON이다.
수집한 입력으로 실제 출시 정확도를 측정하는 도구가 아니다.
"""

import argparse
import importlib.util
import json
from pathlib import Path

from pipeline import diff, discovery, paths, snapshot


def audit(before_diff=None):
    cases = []
    for path in sorted(paths.DIFF_DIR.glob("*/*.json")):
        stored = json.loads(path.read_text())
        week, source = path.parent.name, path.stem
        previous_week = stored.get("previous_week")
        if not previous_week:
            continue
        previous = snapshot.load_snapshot(previous_week, source)
        current = snapshot.load_snapshot(week, source)
        if previous is None or current is None:
            continue
        a, b = previous["items"], current["items"]
        after = diff.diff_items(a, b)
        reversed_after = diff.diff_items(a[::-1], b[::-1])
        assessed = discovery.assess(source, week, after["added"])
        record = {
            "week": week, "source_id": source, "previous_week": previous_week,
            "current_held_from": current.get("held_from"),
            "stored_counts": stored["counts"], "after_counts": after["counts"],
            "after_order_invariant": after == reversed_after,
            "eligible": len(assessed["items"]), "held": assessed["held"],
        }
        if before_diff:
            before = before_diff(a, b)
            reverse_before = before_diff(a[::-1], b[::-1])
            before_ids = {i["external_id"] for i in before["added"]}
            after_ids = {i["external_id"] for i in after["added"]}
            record.update({
                "before_counts": before["counts"],
                "before_added_order_difference": sorted(before_ids ^ {i["external_id"] for i in reverse_before["added"]}),
                "added_only_before": sorted(before_ids - after_ids),
                "added_only_after": sorted(after_ids - before_ids),
            })
        cases.append(record)
    return {"comparison": "same saved snapshots; no LLM or network", "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, help="변경 전 diff.py의 로컬 사본")
    args = parser.parse_args()
    before = None
    if args.before:
        spec = importlib.util.spec_from_file_location("before_diff", args.before)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = module.diff_items
    print(json.dumps(audit(before), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
