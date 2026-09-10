"""스냅샷의 실제 주차·성공·이월·누락을 읽는다. 수집이나 파일 쓰기는 하지 않는다."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from pipeline import paths, sources, weeks


def inspect(root: Path, week: str, expected: list[str]) -> list[dict]:
    weeks.parse_week(week)
    result = []
    for source in expected:
        path = root / "snapshots" / week / f"{source}.json"
        row = {"source": source, "state": "missing", "count": 0}
        if path.exists():
            try:
                data = json.loads(path.read_text())
                stamp = datetime.fromisoformat(data["scraped_at"])
                valid = (data["week"] == week and data["source_id"] == source
                         and isinstance(data["items"], list) and len(data["items"]) > 0
                         and data.get("count") == len(data["items"]) and stamp.tzinfo is not None)
                if not valid:
                    row["state"] = "invalid"
                elif data.get("held_from"):
                    row.update(state="held", held_from=data["held_from"])
                elif weeks.week_of(stamp.astimezone(weeks.KST).date()) != week:
                    row["state"] = "wrong_observation_week"
                else:
                    row["state"] = "success"
                row.update(count=len(data.get("items", [])), scraped_at=data.get("scraped_at"))
            except (OSError, ValueError, KeyError, TypeError):
                row["state"] = "invalid"
        result.append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", default=weeks.current_week())
    parser.add_argument("--group", choices=list(sources.GROUPS))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    expected = sources.group(args.group) if args.group else sources.known()
    rows = inspect(paths.DATA_DIR, args.week, expected)
    if args.markdown:
        print(f"### {args.week} 소스별 수집 결과\n\n| 소스 | 상태 | 항목 수 | 수집 시점 |\n|---|---|---:|---|")
        for row in rows:
            print(f"| {row['source']} | {row['state']} | {row['count']} | {row.get('scraped_at', '—')} |")
    else:
        print(json.dumps({"week": args.week, "sources": rows}, ensure_ascii=False, indent=2))
    return 0 if rows and all(row["state"] == "success" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
