"""분류 목록 예행 — 스냅샷 표본을 실제 LLM에 돌려 `curate.py`의 목록 품질을 잰다.

**발행하지 않는다. 파일도 쓰지 않는다.** 스냅샷을 읽고 결과를 stdout에 찍는 것이 전부다.

## 왜 있는가

`add-source` 스킬 7절은 새 채널이면 분류 목록을 **실제 카탈로그를 보고** 만들라고
하는데, 만든 목록이 쓸 만한지 **확인하는 방법**은 적혀 있지 않았다. 2026-08-26에
dessert·restaurant 목록을 손으로 확인하면서 이 스크립트가 나왔다.

다시 필요해지는 때는 예측 가능하다:

  - 새 채널이 생겨 `CATEGORIES_BY_CHANNEL`에 목록을 추가할 때
  - 기존 목록을 고칠 때 (한 칸에 쏠리거나 `기타`가 늘었을 때)
  - `SYSTEM_PROMPT_TEMPLATE`를 건드릴 때 — 6장이 경고하는 자리다.
    지시의 *자리*가 품질을 바꿔서 blurb가 93 → 72건으로 떨어진 적이 있다

## 무엇을 보는가

⚠️ **분포는 품질이 아니다.** 2026-08-26에 던킨의 `블렌디드/빙수` 4/12를 보고
"도넛집인데 왜?" 했는데, 이름을 보니 비타슬러시·망고쿨라타·컵빙수라 전부 맞았다.
반대로 `기타` 1건은 모델 탓이 아니라 이름만으로는 사람도 모르는 것이었다.
**숫자만 보면 원인을 반대로 짚는다.** 그래서 `--names`가 기본값이다.

## 표본을 그냥 뽑지 마라

목록을 만든 뒤에 붙은 소스가 있으면 그쪽에 가중치를 둔다. restaurant 목록은
소스 6곳을 보고 만들었는데 그 뒤 버거킹·피자헛이 붙었고, 예행에서 40건 중 18건을
그 둘로 채웠기 때문에 새 소스가 목록에 맞는지 알 수 있었다.

## 쓰는 법

    THIS_WEEK_TASTE_DATA_DIR=<비공개 저장소> THIS_WEEK_TASTE_LLM=cli \\
      python -m scripts.curate_dryrun --week 2026-W35 --channel restaurant

    # 특정 소스에 가중치를 준다 (목록 제작 이후 붙은 소스)
    ... --channel restaurant --weight burgerking=12 --weight pizzahut=6

⚠️ `cli` 경로는 구독 사용량을 쓴다. 표본을 키우기 전에 한 번 생각할 것.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import curate, paths, sources, weeks

log = logging.getLogger(__name__)

DEFAULT_SAMPLE = 40


def sources_in(channel: str) -> list[str]:
    return sorted(s for s in sources.known()
                  if sources.meta(s)["channel"] == channel)


def load_snapshot(week: str, source_id: str) -> list[dict]:
    path = paths.SNAPSHOT_DIR / week / f"{source_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def build_sample(week: str, channel: str, total: int, weights: dict[str, int],
                 seed: int) -> tuple[list[dict], dict[str, str]]:
    """소스별로 나눠 뽑는다. `weights`에 있는 소스는 그 건수를 먼저 가져간다.

    시드를 받는 이유: **같은 표본을 LLM 없이 재현할 수 있어야 한다.** 분포를 보고
    의심스러운 칸이 나왔을 때 이름을 다시 뽑아 보려고 매번 돌리면 사용량만 든다.
    """
    rng = random.Random(seed)
    pools = {s: load_snapshot(week, s) for s in sources_in(channel)}
    pools = {s: items for s, items in pools.items() if items}
    if not pools:
        raise SystemExit(f"{week}에 {channel} 채널 스냅샷이 없다: {paths.SNAPSHOT_DIR / week}")

    unknown = [s for s in weights if s not in pools]
    if unknown:
        raise SystemExit(f"{channel} 채널에 없거나 스냅샷이 없는 소스: {unknown}")

    plan = {s: min(n, len(pools[s])) for s, n in weights.items()}
    remaining = total - sum(plan.values())
    rest = [s for s in pools if s not in plan]
    if remaining > 0 and rest:
        # 남은 자리는 카탈로그 크기에 비례해서 나눈다. 작은 소스도 최소 1건은 받는다.
        sizes = {s: len(pools[s]) for s in rest}
        pool_total = sum(sizes.values())
        for source_id in rest:
            plan[source_id] = max(1, round(remaining * sizes[source_id] / pool_total))

    items: list[dict] = []
    origin: dict[str, str] = {}
    for source_id, n in plan.items():
        for item in rng.sample(pools[source_id], min(n, len(pools[source_id]))):
            origin[item["external_id"]] = source_id
            items.append(item)
    return items, origin


def report(channel: str, items: list[dict], origin: dict[str, str],
           result: dict[str, dict], enriched: dict, *, show_names: bool) -> None:
    allowed = set(curate.CATEGORIES_BY_CHANNEL[channel])
    by_name = {i["external_id"]: i["name"] for i in items}
    raw = {i["external_id"]: i.get("category_raw") for i in items}
    dist = collections.Counter(v["category"] for v in result.values())

    # ⚠️ **LLM이 안 돌았는데 목록이 깨진 것으로 읽으면 안 된다.**
    # 편집이 실패하면 `curate.py`가 `category_raw`로 폴백하고, 그러면 소스의 원본
    # 분류가 통째로 "목록 밖"으로 잡힌다. 발행이 성공하므로 조용한 실패다 (6장).
    edited = sum(1 for k, v in result.items() if v["category"] != raw[k])
    if not edited:
        print("\n" + "!" * 72)
        print("!! LLM이 한 건도 편집하지 않았다. 아래 '목록 밖'은 분류 목록의 문제가")
        print("!! 아니라 소스의 category_raw가 그대로 나온 것이다.")
        print("!! THIS_WEEK_TASTE_LLM 값과 위 로그를 확인할 것.")
        print("!" * 72)
    outside = {by_name[k]: v["category"] for k, v in result.items()
               if v["category"] not in allowed}
    mangled = [(by_name[k], v.get("name")) for k, v in result.items()
               if v.get("name") and v["name"] != by_name[k]]
    blurbs = sum(1 for v in result.values() if v["blurb"])
    out_of_scope = [by_name[k] for k, v in result.items() if v.get("out_of_scope")]
    total = len(items) or 1

    print(f"\n[분류 분포]  쓰인 칸 {len(dist)}/{len(allowed)}")
    for cat, n in dist.most_common():
        mark = "  ← 목록 밖!" if cat not in allowed else ""
        print(f"  {cat:<16} {n:3}  {'#' * n}{mark}")

    top = dist.most_common(1)[0]
    print(f"\n  편집됨        {edited}/{len(items)}"
          f"  (0이면 위 경고를 볼 것)")
    print(f"  기타          {dist.get('기타', 0)}/{len(items)}"
          f" = {dist.get('기타', 0) / total * 100:.0f}%")
    print(f"  목록 밖       {len(outside)}건 {outside or ''}")
    print(f"  최대 쏠림     {top[0]} {top[1]}건 = {top[1] / total * 100:.0f}%")
    # name이 입력과 다르면 publish가 그 항목의 편집을 통째로 버린다 (6장).
    print(f"  name 변조     {len(mangled)}건 {mangled[:3] or ''}")
    print(f"  blurb         {blurbs}/{len(enriched)} (설명문 있는 것 기준)")
    print(f"  범위 밖 판정   {len(out_of_scope)}건 {out_of_scope[:5] or ''}")

    print("\n[소스별]")
    per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for external_id, edit in result.items():
        per[origin[external_id]][edit["category"]] += 1
    for source_id in sorted(per):
        print(f"  {source_id:<16} {dict(per[source_id])}")

    if show_names:
        # ⚠️ 여기가 이 스크립트의 핵심이다. 위의 숫자만 보면 원인을 반대로 짚는다.
        print("\n[항목별]  ⚠️ 분포가 아니라 여기를 봐야 오분류가 보인다")
        rows = sorted(result.items(), key=lambda kv: (origin[kv[0]], kv[1]["category"]))
        for external_id, edit in rows:
            flag = "" if edit["category"] in allowed else " ←목록밖"
            blurb = f"  “{edit['blurb']}”" if edit["blurb"] else ""
            print(f"  {origin[external_id]:<14} {edit['category']:<14}"
                  f" {by_name[external_id][:32]:<34}{flag}{blurb}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="분류 목록 예행 (발행하지 않는다)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="⚠️ THIS_WEEK_TASTE_LLM=cli 는 구독 사용량을 쓴다.")
    parser.add_argument("--channel", required=True,
                        choices=sorted(curate.CATEGORIES_BY_CHANNEL),
                        help="분류 목록을 확인할 채널")
    parser.add_argument("--week", help="스냅샷 주차. 생략하면 이번 주")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                        help=f"표본 크기 (기본 {DEFAULT_SAMPLE})")
    parser.add_argument("--weight", action="append", default=[], metavar="소스=건수",
                        help="특정 소스에 가중치. 목록 제작 이후 붙은 소스에 쓴다. 반복 지정 가능")
    parser.add_argument("--seed", type=int, default=20260826,
                        help="표본 시드. 같은 값이면 같은 표본이 나온다")
    parser.add_argument("--no-names", action="store_true",
                        help="항목별 목록을 감춘다. **권하지 않는다** — 모듈 docstring 참조")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    week = args.week or weeks.current_week()
    weeks.parse_week(week)

    weights = {}
    for spec in args.weight:
        source_id, _, count = spec.partition("=")
        if not count.isdigit():
            raise SystemExit(f"--weight 형식은 `소스=건수`다: {spec!r}")
        weights[source_id] = int(count)

    items, origin = build_sample(week, args.channel, args.sample, weights, args.seed)

    # enrich가 채웠을 자리를 스냅샷의 description으로 대신한다. 목록이 설명문을 주는
    # 소스만 채워지는데, 그것이 실제 모습이다 — 상세에서 오는 소스는 여기서 비어 있다.
    # ⚠️ 그래서 `detail: True`인 소스만 있는 채널은 blurb 품질을 여기서 잴 수 없다.
    enriched = {i["external_id"]: {"description": i["description"]}
                for i in items if i.get("description")}

    print(f"\n{'=' * 72}\n{args.channel}  {week}  표본 {len(items)}건 "
          f"(설명문 있는 것 {len(enriched)}건)  seed={args.seed}\n{'=' * 72}")
    result = curate.curate(items, enriched, channel=args.channel)
    report(args.channel, items, origin, result, enriched, show_names=not args.no_names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
