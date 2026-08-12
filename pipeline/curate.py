"""LLM 편집 단계 (CLAUDE.md 6장).

역할은 **판단이지 창작이 아니다.** 이 단계가 하는 일은 두 가지뿐이다:
  1. 자체 카테고리 부여
  2. enrich가 가져온 공식 설명문을 40자 이내로 **요약** (창작이 아니라 압축)

하지 않는 일:
  - `name`을 건드리지 않는다. CU는 제품명을 12자에서 자르는데, 이를 "복원"시키면
    없는 정보를 지어내는 것이 된다. 출력의 name이 입력과 다르면 그 항목은 버린다.
  - 설명문이 없으면 `blurb`는 `null`이다. 이름만 보고 쓰게 하지 않는다.
  - 태그는 소스가 준 것을 그대로 쓴다. LLM에게 만들게 하지 않는다. 소스가 안 주면 빈 목록이다.

6장의 나머지 두 역할(신제품 vs 리뉴얼 구분, 중복 병합)은 v1 범위 밖이다.
`diff.py`가 소스의 상품 키로 동일성을 이미 판정하므로 LLM이 다시 할 일이 없다.

**API 키가 없거나 실패하면 LLM 없이 원본 그대로 발행한다.** 편집 품질보다 발행이 우선이다.

## 두 가지 호출 경로

`THIS_WEEK_TASTE_LLM` 환경변수로 고른다.

    api (기본)  ANTHROPIC_API_KEY로 SDK 직접 호출. 자동화(GitHub Actions)는 이것만 된다
    cli         `claude -p`로 구독 인증을 쓴다. 로컬에서만 되고 구독 사용량을 소모한다
    off         LLM을 쓰지 않는다

cli는 **명시적으로 켜야 한다.** 자동으로 넘어가지 않는다 — 남의 지갑이 아니라
본인 구독 한도를 쓰는 일이라 조용히 일어나면 안 된다.

실측(2026-08-12, 20건 배치): api는 배치당 약 $0.0007, cli는 콜드 $0.05 / 웜 $0.007.
차이는 Claude Code가 자기 시스템 프롬프트 22K 토큰을 매 호출에 얹기 때문이다.
cli 경로는 `output_config`(스키마 강제)를 쓸 수 없어 응답이 마크다운 코드펜스에
감싸여 온다. 그래서 파싱 전에 펜스를 벗긴다.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

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


CLI_TIMEOUT = 180        # `claude -p` 한 번의 상한(초). 실측 8~10초


class _GiveUp(Exception):
    """재시도해도 소용없는 실패. 이 배치는 원본 그대로 간다."""


def _complete_api(client, user: str) -> str | None:
    """성공하면 응답 텍스트, 재시도할 만하면 None, 가망 없으면 _GiveUp."""
    import anthropic

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.RateLimitError as exc:
        log.warning("레이트리밋: %s", exc)
        return None
    except anthropic.APIConnectionError as exc:
        log.warning("연결 실패: %s", exc)
        return None
    except anthropic.APIStatusError as exc:
        raise _GiveUp(f"API 오류 {exc.status_code}: {exc.message}") from exc

    if response.stop_reason == "refusal":
        raise _GiveUp("모델이 요청을 거부했다")

    return next((b.text for b in response.content if b.type == "text"), "")


def _complete_cli(user: str) -> str | None:
    """`claude -p`로 구독 인증을 써서 호출한다. 로컬 전용."""
    command = [
        "claude", "-p", user,
        "--model", MODEL,
        "--output-format", "json",
        "--system-prompt", SYSTEM_PROMPT,
        "--allowedTools", "",       # 편집 작업에 도구가 필요 없다
    ]
    try:
        done = subprocess.run(command, capture_output=True, text=True,
                              timeout=CLI_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.warning("claude -p 가 %d초 안에 끝나지 않았다.", CLI_TIMEOUT)
        return None

    if done.returncode != 0:
        log.warning("claude -p 종료코드 %d: %s", done.returncode,
                    done.stderr.strip()[:200])
        return None

    try:
        envelope = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise _GiveUp(f"claude -p 출력이 JSON이 아니다: {exc}") from exc

    if envelope.get("is_error"):
        raise _GiveUp(f"claude -p 오류: {envelope.get('api_error_status')}")

    return _strip_fence(envelope.get("result", ""))


def _strip_fence(text: str) -> str:
    """```json ... ``` 코드펜스를 벗긴다.

    cli 경로는 스키마를 강제할 수 없어서, 프롬프트로 "JSON만"이라고 해도
    실측상 펜스가 붙어 온다. api 경로에는 영향이 없다(펜스가 없으면 그대로 통과).
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[-1]        # 첫 줄(```json)을 버린다
    return body.rsplit("```", 1)[0].strip()


def _backend():
    """(이름, complete) 또는 None. complete(user) -> str | None."""
    choice = os.environ.get("THIS_WEEK_TASTE_LLM", "api").strip().lower()

    if choice == "off":
        log.info("THIS_WEEK_TASTE_LLM=off. LLM 없이 원본 그대로 발행한다 (6장).")
        return None

    if choice == "cli":
        if not shutil.which("claude"):
            log.warning("claude 실행파일이 PATH에 없다. LLM 없이 발행한다 (6장).")
            return None
        log.info("claude -p 로 편집한다. 구독 사용량을 소모하며 로컬에서만 동작한다.")
        return "cli", _complete_cli

    if choice != "api":
        log.warning("THIS_WEEK_TASTE_LLM=%r 는 모르는 값이다. api로 취급한다.", choice)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY가 없다. LLM 없이 원본 그대로 발행한다 (6장).")
        return None

    import anthropic
    client = anthropic.Anthropic()
    return "api", lambda user: _complete_api(client, user)


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


def _entries(parsed: object) -> dict[str, dict] | None:
    """응답에서 {external_id: 항목}을 뽑는다. 모양이 틀리면 None.

    api 경로는 OUTPUT_SCHEMA가 `{"items": [...]}`를 강제하지만 cli 경로는 스키마를
    쓸 수 없다. 실측(2026-08-12)에서 모델이 맨 배열 `[...]`을 돌려줘 여기서 터졌다.
    **여기서 예외가 나가면 6장의 약속("실패하면 원본 그대로 발행")이 깨진다.**
    그래서 모르는 모양은 예외가 아니라 None으로 돌려보내 재시도/폴백에 태운다.
    """
    if isinstance(parsed, dict):
        parsed = parsed.get("items")
    if not isinstance(parsed, list):
        return None

    entries = {}
    for entry in parsed:
        if isinstance(entry, dict) and isinstance(entry.get("external_id"), str):
            entries[entry["external_id"]] = entry
    return entries


def _curate_batch(complete, batch: list[dict], enriched: dict) -> dict[str, dict]:
    """한 배치를 편집한다. 실패하면 빈 dict을 돌려주고 호출자가 원본을 쓴다."""
    request = json.dumps(_payload(batch, enriched), ensure_ascii=False, indent=2)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = complete(request)
        except _GiveUp as exc:
            log.error("%s. 이 배치는 원본 그대로 간다.", exc)
            break

        if text is None:
            log.warning("호출 실패 (%d/%d). 재시도한다.", attempt, MAX_ATTEMPTS)
            continue

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("JSON 파싱 실패 (%d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue

        entries = _entries(parsed)
        if entries is None:
            log.warning("응답 모양이 예상과 다르다 (%d/%d): %.120s",
                        attempt, MAX_ATTEMPTS, text)
            continue

        # 빈 결과를 성공으로 취급하면 조용히 전량이 원본으로 발행된다 (2.4).
        # 20건을 보냈는데 0건이 오는 것은 성공이 아니라 실패다.
        if not entries:
            log.warning("%d건을 보냈는데 쓸 수 있는 항목이 0건이다 (%d/%d).",
                        len(batch), attempt, MAX_ATTEMPTS)
            continue

        missing = {item["external_id"] for item in batch} - set(entries)
        if missing:
            log.warning("응답에서 %d건이 빠졌다. 이 항목들은 원본을 쓴다: %s",
                        len(missing), sorted(missing)[:5])

        return entries

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
    backend = _backend()
    edits: dict[str, dict] = {}

    if backend and items:
        name, complete = backend
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start:start + BATCH_SIZE]
            log.info("편집 중 [%s] %d~%d / %d",
                     name, start + 1, start + len(batch), len(items))
            try:
                edits.update(_curate_batch(complete, batch, enriched))
            except Exception:
                # 6장: 편집 품질보다 발행이 우선이다. 여기서 예외가 위로 나가면
                # 그 주의 발행 전체가 죽는다. 삼키지 않고 스택까지 남기되(2.4),
                # 남은 배치는 계속 돌린다.
                log.exception("배치 %d~%d 편집이 예기치 않게 실패했다. 원본을 쓴다.",
                              start + 1, start + len(batch))

    result = {
        item["external_id"]: _apply(item, edits.get(item["external_id"]),
                                    enriched.get(item["external_id"]))
        for item in items
    }
    with_blurb = sum(1 for v in result.values() if v["blurb"])
    log.info("편집 완료: %d건 중 blurb %d건", len(result), with_blurb)
    return result
