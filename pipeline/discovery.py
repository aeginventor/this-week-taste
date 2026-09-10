"""목록의 added를 과거 관측과 대조한다. 출시를 추정하지 않는다 (ADR-0018).

카탈로그 항목의 동일성과 제품의 신규성은 별개다. 원본 ID는 보존하고, 기존 제품과
강하게 겹치는 후보는 근거를 남겨 보류한다. 이 결과를 단종/재입고 확정으로 쓰지 않는다.
"""

from __future__ import annotations

import json
from pipeline import normalize, snapshot, weeks


def _product_key(item: dict) -> tuple | None:
    barcode = (item.get("alt_ids") or {}).get("barcode")
    price = item.get("price")
    if not barcode or price is None:
        return None
    return (item.get("source_id"), str(barcode),
            normalize.normalize_name(item["name"]), price)


def classify(added: list[dict], history: list[dict]) -> dict:
    """history: [{week, items}]. 외부 입력의 순서와 무관하게 후보와 보류 근거를 준다."""
    ids, products = {}, {}
    for observation in sorted(history, key=lambda x: x["week"]):
        for item in sorted(observation["items"], key=lambda i: str(i["external_id"])):
            evidence = {"week": observation["week"], "external_id": item["external_id"]}
            ids.setdefault((item.get("source_id"), str(item["external_id"])), evidence)
            key = _product_key(item)
            if key is not None:
                products.setdefault(key, evidence)

    accepted, held = [], []
    batch_products = {}
    for item in sorted(added, key=lambda i: (str(i.get("source_id", "")), str(i["external_id"]))):
        key = _product_key(item)
        evidence = ids.get((item.get("source_id"), str(item["external_id"])))
        reason = "previously_observed_entry"
        if evidence is None and key is not None:
            evidence = products.get(key)
            reason = "previously_observed_product"
        if evidence is None and key is not None and key in batch_products:
            evidence = {"external_id": batch_products[key]}
            reason = "duplicate_in_batch"
        if evidence is not None:
            held.append({"external_id": item["external_id"], "name": item["name"],
                         "reason": reason, "evidence": evidence})
        else:
            accepted.append(item)
            if key is not None:
                batch_products[key] = item["external_id"]
    return {"items": accepted, "held": held}


def history_for(source_id: str, week: str) -> list[dict]:
    """과거의 성공 관측만 읽는다. 보관된 양성 관측은 4주가 지나도 과거 존재의 증거다.

    diff의 부재 비교 기간(최대 4주)과 다르다. 현재/미래 스냅샷과 이월 파일은 제외한다.
    파일이 손상되면 예외로 실패한다. 이력을 못 읽은 상태를 '처음 봄'으로 만들지 않는다.
    """
    weeks.parse_week(week)
    history = []
    for path in sorted(snapshot.SNAPSHOT_DIR.glob(f"*/{source_id}.json")):
        observed_week = path.parent.name
        weeks.parse_week(observed_week)
        if observed_week >= week:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("source_id") != source_id or payload.get("week") != observed_week:
            raise ValueError(f"스냅샷 경로와 메타데이터가 다르다: {path}")
        if not payload.get("held_from"):
            history.append({"week": observed_week, "items": payload["items"]})
    return history


def assess(source_id: str, week: str, added: list[dict]) -> dict:
    history = history_for(source_id, week)
    result = classify(added, history)
    result["history_weeks"] = [entry["week"] for entry in history]
    return result
