"""LLM 편집 단계 (CLAUDE.md 6장).

역할은 **판단이지 창작이 아니다.** 이 단계가 하는 일은 두 가지뿐이다:
  1. 자체 카테고리 부여
  2. enrich가 가져온 공식 설명문을 40자 이내로 **요약** (창작이 아니라 압축)

하지 않는 일:
  - `name`을 건드리지 않는다. CU는 제품명을 12자에서 자르는데, 이를 "복원"시키면
    없는 정보를 지어내는 것이 된다. 출력의 name이 입력과 다르면 그 항목은 버린다.
  - 설명문이 없으면 `blurb`는 `null`이다. 이름만 보고 쓰게 하지 않는다.
  - 태그는 소스가 준 것을 그대로 쓴다(CU 상세 페이지가 준다). LLM에게 만들게 하지 않는다.

6장의 나머지 두 역할(신제품 vs 리뉴얼 구분, 중복 병합)은 v1 범위 밖이다.
CU는 바코드와 gdIdx 두 키로 diff에서 이미 동일성을 판정하므로 LLM이 다시 할 일이 없다.

**API 키가 없거나 실패하면 LLM 없이 원본 그대로 발행한다.** 편집 품질보다 발행이 우선이다.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

# CLAUDE.md 6장: Haiku 4.5로 시작. 품질이 부족하면 Sonnet 5로 승격.
MODEL = "claude-haiku-4-5"
MAX_BLURB_CHARS = 40
BATCH_SIZE = 20          # 한 요청에 담을 항목 수
MAX_ATTEMPTS = 2         # 최초 1회 + 재시도 1회 (6장)

SYSTEM_PROMPT = """\
너는 한국 편의점 신상품 데이터를 정리하는 편집자다.

각 항목에 대해 두 가지만 한다:
1. category: 아래 목록에서 하나를 고른다.
   도시락, 김밥, 삼각김밥, 샌드위치, 버거, 샐러드, 면류, 즉석조리, 디저트,
   과자, 아이스크림, 음료, 커피, 유제품, 주류, 안주, 기타
2. blurb: 주어진 description을 40자 이내 한 줄로 줄인다.

절대 규칙:
- description이 비어 있으면 blurb는 반드시 null이다. 이름만 보고 짐작해서 쓰지 마라.
- description에 없는 사실(맛 평가, 후기, 출시 배경, 재료 추측)을 절대 넣지 마라.
- name은 입력 그대로 돌려준다. 잘려 있어도 복원하지 마라. 그것이 원본이다.
- 설명이나 마크다운 없이 JSON만 반환한다."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "external_id": {"type": "string"},
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "blurb": {"type": ["string", "null"]},
                },
                "required": ["external_id", "name", "category", "blurb"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _client():
    """API 키가 없으면 None. 호출자는 LLM 없이 진행한다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY가 없다. LLM 없이 원본 그대로 발행한다 (6장).")
        return None
    import anthropic
    return anthropic.Anthropic()


def _payload(items: list[dict], enriched: dict) -> list[dict]:
    return [
        {
            "external_id": item["external_id"],
            "name": item["name"],
            "category_raw": item.get("category_raw"),
            "price": item.get("price"),
            "description": (enriched.get(item["external_id"]) or {}).get("description"),
        }
        for item in items
    ]


def _curate_batch(client, batch: list[dict], enriched: dict) -> dict[str, dict]:
    """한 배치를 편집한다. 실패하면 빈 dict을 돌려주고 호출자가 원본을 쓴다."""
    import anthropic

    request = json.dumps(_payload(batch, enriched), ensure_ascii=False, indent=2)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                messages=[{"role": "user", "content": request}],
            )
        except anthropic.RateLimitError as exc:
            log.warning("레이트리밋 (%d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue
        except anthropic.APIStatusError as exc:
            log.error("API 오류 %s: %s", exc.status_code, exc.message)
            break
        except anthropic.APIConnectionError as exc:
            log.warning("연결 실패 (%d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue

        if response.stop_reason == "refusal":
            log.error("모델이 요청을 거부했다. 이 배치는 원본 그대로 간다.")
            break

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("JSON 파싱 실패 (%d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue

        return {entry["external_id"]: entry for entry in parsed.get("items", [])}

    log.error("%d회 시도 후 실패. 이 배치 %d건은 LLM 없이 원본 그대로 발행한다.",
              MAX_ATTEMPTS, len(batch))
    return {}


def _apply(item: dict, edit: dict | None, enriched_entry: dict | None) -> dict:
    """LLM 결과를 항목에 반영한다. 검증에 걸리면 원본을 유지한다."""
    tags = list((enriched_entry or {}).get("tags") or [])
    description = (enriched_entry or {}).get("description")
    curated = {"category": item.get("category_raw"), "tags": tags, "blurb": None}

    if not edit:
        return curated

    # name은 LLM이 건드리는 필드가 아니다 (6장). 다르면 이 항목의 결과를 통째로 버린다.
    if edit.get("name") != item["name"]:
        log.error("LLM이 이름을 바꿨다: %r → %r. 이 항목은 원본을 쓴다.",
                  item["name"], edit.get("name"))
        return curated

    if edit.get("category"):
        curated["category"] = edit["category"]

    blurb = edit.get("blurb")
    if blurb and not description:
        # 근거가 없는데 설명을 지어냈다. 6장 위반이므로 버린다.
        log.error("설명문이 없는데 blurb가 생성됐다 (%s). 버린다.", item["name"])
    elif blurb and len(blurb) > MAX_BLURB_CHARS:
        log.warning("blurb가 %d자로 길다 (%s). 자른다.", len(blurb), item["name"])
        curated["blurb"] = blurb[:MAX_BLURB_CHARS]
    elif blurb:
        curated["blurb"] = blurb

    return curated


def curate(items: list[dict], enriched: dict) -> dict[str, dict]:
    """{external_id: {category, tags, blurb}}. 실패해도 예외를 던지지 않는다."""
    client = _client()
    edits: dict[str, dict] = {}

    if client and items:
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start:start + BATCH_SIZE]
            log.info("편집 중 %d~%d / %d", start + 1, start + len(batch), len(items))
            edits.update(_curate_batch(client, batch, enriched))

    result = {
        item["external_id"]: _apply(item, edits.get(item["external_id"]),
                                    enriched.get(item["external_id"]))
        for item in items
    }
    with_blurb = sum(1 for v in result.values() if v["blurb"])
    log.info("편집 완료: %d건 중 blurb %d건", len(result), with_blurb)
    return result
