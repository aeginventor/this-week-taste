"""전체 카탈로그 수집 → `data/snapshots/<week>/<source_id>.json` (CLAUDE.md 2.1, 2.4).

이 단계의 일은 두 가지다.
  1. 스크래퍼가 준 항목을 스냅샷 파일로 저장한다
  2. **결과를 믿어도 되는지 판정한다.** 못 믿겠으면 저장하지 않고 지난주를 유지한다

`_` 로 시작하는 키는 스냅샷에 저장하지 않고 `<source_id>.control.json`으로 분리한다.
소스의 신상 라벨(`_labels.new`)이 여기 들어간다. 판정 경로(diff)에서 물리적으로 떼어 놓아
2.1("소스의 신상 라벨을 신뢰하지 않는다")이 실수로도 깨지지 않게 하려는 것이다.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from pipeline import alert, paths, sources, weeks

log = logging.getLogger(__name__)

# 경로는 paths.py 한 곳에서 온다. 저장소 밖을 가리킬 수 있다(공개 범위, ADR-0011).
DATA_DIR = paths.DATA_DIR
SNAPSHOT_DIR = paths.SNAPSHOT_DIR

# 이상 판정 기준 (2.4)
DROP_THRESHOLD = 0.30   # 직전 주의 30% 미만으로 줄면 = 70% 이상 감소
SPIKE_THRESHOLD = 3.00  # 직전 주의 300%를 넘으면 = 200% 이상 증가

# 첫 수집: 정찰 실측치 ±10%. 스크래퍼가 제대로 도는지 검증하는 용도라 빡빡하게 잡는다.
#
# 실측치 자체는 **각 스크래퍼의 `BOOTSTRAP_COUNTS`에 있다.** 여기 모아두지 않는 이유는
# 그것이 소스의 *내용*이라 7장이 말하는 누수이기 때문이다. 카테고리 코드는 소스마다
# 다른 어휘이고(`10` / `0101` / `W0000171` / `200095`), 이 파일은 모든 소스가 쓴다.
#
# 이 값은 **첫 수집 때만 쓴다.** 카탈로그는 계속 변하므로 고정값을 매주 기준으로 쓰면
# 언젠가 반드시 오탐이 난다. 실제로 CU는 2026-W33 수집에서 이미 어긋나기 시작했다
# (간편식사 204/208, 과자류 1146/1154). 직전 주 스냅샷이 있으면 그쪽이 언제나 기준이다.
BOOTSTRAP_TOLERANCE = 0.10


def snapshot_path(week: str, source_id: str) -> Path:
    return SNAPSHOT_DIR / week / f"{source_id}.json"


def control_path(week: str, source_id: str) -> Path:
    return SNAPSHOT_DIR / week / f"{source_id}.control.json"


def load_snapshot(week: str, source_id: str) -> dict | None:
    path = snapshot_path(week, source_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _split_control(items: list[dict]) -> tuple[list[dict], dict]:
    """`_` 접두 키를 항목에서 떼어내 대조군 파일용 dict로 옮긴다."""
    clean: list[dict] = []
    control: dict[str, dict] = {}
    for item in items:
        private = {k: v for k, v in item.items() if k.startswith("_")}
        clean.append({k: v for k, v in item.items() if not k.startswith("_")})
        if private:
            control[item["external_id"]] = {k.lstrip("_"): v for k, v in private.items()}
    return clean, control


def _category_counts(source_id: str, items: list[dict]) -> dict[str, int]:
    """카테고리 코드별 건수. category_raw는 사람이 읽는 이름이라 코드로 되돌린다."""
    module = _scraper_for(source_id)
    name_to_code = {name: code for code, name in module.CATEGORIES.items()}
    counts: dict[str, int] = {}
    for item in items:
        code = name_to_code.get(item.get("category_raw"))
        if code:
            counts[code] = counts.get(code, 0) + 1
    return counts


def _check_category_counts(source_id: str, week: str, items: list[dict]) -> list[str]:
    """카테고리별 건수 검증. 한 카테고리가 통째로 비는 것을 잡는 것이 목적이다.

    기준은 두 가지이고, **직전 주가 있으면 언제나 그쪽이 우선한다**:

      첫 수집   정찰 실측치 ±10%     — 스크래퍼가 제대로 도는지 검증
      그 이후   직전 주의 30%~300%   — 구조가 깨졌는지 검증

    정찰 실측치를 계속 기준으로 쓰면 안 된다. 카탈로그는 정상적으로 변하므로
    시간이 지나면 반드시 ±10%를 벗어나고, 그때 조용히 발행이 멈춘다.
    """
    module = _scraper_for(source_id)
    actual = _category_counts(source_id, items)

    previous = load_snapshot(weeks.previous_week(week), source_id)
    if previous:
        baseline = _category_counts(source_id, previous["items"])
        label, low_ratio, high_ratio = "직전 주", DROP_THRESHOLD, SPIKE_THRESHOLD
    else:
        baseline = getattr(module, "BOOTSTRAP_COUNTS", {})
        label = "정찰 실측"
        low_ratio, high_ratio = 1 - BOOTSTRAP_TOLERANCE, 1 + BOOTSTRAP_TOLERANCE

    problems = []
    for code, want in baseline.items():
        got = actual.get(code, 0)
        if want == 0:
            continue
        ok = want * low_ratio <= got <= want * high_ratio
        log.info("  %s%s(%s): %d건 (%s %d)", "OK " if ok else "!! ",
                 module.CATEGORIES[code], code, got, label, want)
        if not ok:
            problems.append(f"{module.CATEGORIES[code]}({code}): {got}건 — "
                            f"{label} {want}건 대비 {(got / want - 1) * 100:+.0f}%")

    # 기준에 없던 카테고리가 새로 생긴 경우도 알린다(소스가 개편됐다는 신호).
    for code in sorted(set(actual) - set(baseline)):
        log.warning("  ?? %s(%s): %d건 — %s 기준에 없던 카테고리",
                    module.CATEGORIES[code], code, actual[code], label)
    return problems


def _check_volume(source_id: str, week: str, count: int) -> None:
    """0건 / 급감 / 급증 판정 (2.4). 이상이면 예외를 던진다."""
    if count == 0:
        alert.raise_anomaly(
            f"[{source_id}] {week} 수집 결과가 0건",
            "크롤러가 항목을 하나도 가져오지 못했다. 지난주 스냅샷을 유지한다.",
        )

    previous = load_snapshot(weeks.previous_week(week), source_id)
    if not previous:
        log.info("직전 주 스냅샷이 없어 증감 판정을 건너뛴다 (첫 수집)")
        return

    before = previous["count"]
    if before == 0:
        return
    ratio = count / before
    log.info("직전 주 대비: %d → %d건 (%.0f%%)", before, count, ratio * 100)

    if ratio < DROP_THRESHOLD:
        alert.raise_anomaly(
            f"[{source_id}] {week} 수집 건수 급감",
            f"직전 주 {before}건 → 이번 주 {count}건 ({(ratio - 1) * 100:+.0f}%).\n"
            "지난주 스냅샷을 유지한다. 소스 구조 변경 여부를 확인할 것.",
        )
    if ratio > SPIKE_THRESHOLD:
        alert.raise_anomaly(
            f"[{source_id}] {week} 수집 건수 급증",
            f"직전 주 {before}건 → 이번 주 {count}건 ({(ratio - 1) * 100:+.0f}%).\n"
            "목록의 성격이 바뀌었을 수 있다(카테고리 개편 등). 지난주 스냅샷을 유지한다.",
        )


def _scraper_for(source_id: str):
    return sources.scraper(source_id)


def _hold_previous(week: str, source_id: str) -> bool:
    """이상 상황일 때 지난주 스냅샷을 이번 주로 이월한다 (2.4)."""
    previous = load_snapshot(weeks.previous_week(week), source_id)
    if not previous:
        log.error("이월할 지난주 스냅샷도 없다. %s %s는 이번 주 데이터가 없다.", source_id, week)
        return False

    previous["week"] = week
    previous["held_from"] = previous.get("held_from") or weeks.previous_week(week)
    path = snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

    src_control = control_path(weeks.previous_week(week), source_id)
    if src_control.exists():
        shutil.copyfile(src_control, control_path(week, source_id))
    log.warning("지난주(%s) 스냅샷을 %s로 이월했다. 이번 주 diff는 변화 없음으로 나온다.",
                previous["held_from"], week)
    return True


def take(source_id: str, week: str | None = None) -> Path:
    """한 소스의 스냅샷을 뜬다. 이상 상황이면 alert.PipelineAnomaly를 던진다."""
    week = week or weeks.current_week()
    module = _scraper_for(source_id)

    log.info("== %s %s 스냅샷 ==", source_id, week)
    items = module.fetch(week=week)

    problems = _check_category_counts(source_id, week, items)
    if problems:
        alert.raise_anomaly(
            f"[{source_id}] {week} 카테고리별 건수가 정찰 실측치와 어긋난다",
            "\n".join(problems)
            + f"\n\n정찰 실측치는 scrapers/{source_id}.py의 BOOTSTRAP_COUNTS에 있다.",
        )

    _check_volume(source_id, week, len(items))

    clean, control = _split_control(items)
    duplicates = len(clean) - len({i["external_id"] for i in clean})
    if duplicates:
        alert.raise_anomaly(
            f"[{source_id}] {week} external_id 중복 {duplicates}건",
            "같은 키를 가진 항목이 둘 이상이다. diff의 1:1 매칭 전제가 깨진다.",
        )

    payload = {
        "source_id": source_id,
        "week": week,
        "scraped_at": clean[0]["scraped_at"] if clean else weeks.scraped_at(),
        "count": len(clean),
        "items": clean,
    }
    path = snapshot_path(week, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    control_path(week, source_id).write_text(
        json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("저장: %s (%d건)", path, len(clean))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="전체 카탈로그 스냅샷")
    parser.add_argument("--source", default="cu")
    parser.add_argument("--week", help="생략하면 이번 주")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        take(args.source, args.week)
    except alert.PipelineAnomaly:
        # 이미 로그와 Issue로 알렸다. 지난주를 이월하고 실패로 끝낸다 (2.4).
        _hold_previous(args.week or weeks.current_week(), args.source)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
