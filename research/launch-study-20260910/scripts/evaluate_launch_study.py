"""지문으로 고정한 AI 정답 후보와 자동 출력을 대조한다. 사람 검수로 표현하지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.launch_claims import norm


def evaluate(review, reference):
    metrics = {k: 0 for k in ["documents", "failed_documents", "expected_events", "correct_events",
        "wrong_extractions", "missed_sufficient_events", "insufficient_evidence_predictions",
        "useful_family_events", "wrong_family_events", "held_linkable_events", "catalog_unavailable_events"]}
    cases = []
    by_id = {d["document_id"]: d for d in review["documents"]}
    for gold in reference["documents"]:
        metrics["documents"] += 1
        actual = by_id.get(gold["document_id"])
        metrics["expected_events"] += len(gold["expected_events"])
        found = set()
        if not actual or actual["status"] != "ok":
            metrics["failed_documents"] += 1
        for c in actual.get("claims", []) if actual else []:
            if c["kind"] not in {"new_launch", "seasonal_return"}:
                continue
            matches = [i for i, e in enumerate(gold["expected_events"]) if norm(e["name"]) == norm(c["product_name"])]
            expected = gold["expected_events"][matches[0]] if len(matches) == 1 else None
            supported = [x["external_id"] for x in c["links"] if x["state"] == "family_supported"]
            sufficient = expected and c["kind"] == expected["kind"] and c["launch_date"] == expected["date"]
            if sufficient and matches[0] not in found:
                found.add(matches[0]); metrics["correct_events"] += 1
                allowed = set(expected["allowed_family_ids"])
                if supported and not set(supported) <= allowed:
                    metrics["wrong_family_events"] += 1; outcome = "wrong_product_link"
                elif supported:
                    metrics["useful_family_events"] += 1; outcome = "useful_family_link"
                elif expected["linkable"]:
                    metrics["held_linkable_events"] += 1; outcome = "held_despite_sufficient_link_evidence"
                else:
                    metrics["catalog_unavailable_events"] += 1; outcome = "catalog_link_not_established"
            elif norm(c["product_name"]) in {norm(x) for x in gold["uncertain_names"]}:
                metrics["insufficient_evidence_predictions"] += 1; outcome = "source_evidence_insufficient"
                if supported:
                    metrics["wrong_family_events"] += 1
            else:
                metrics["wrong_extractions"] += 1; outcome = "wrong_or_duplicate_extraction"
                if supported:
                    metrics["wrong_family_events"] += 1
            cases.append({"document_id": gold["document_id"], "name": c["product_name"], "outcome": outcome,
                          "kind": c["kind"], "date": c["launch_date"], "linked_ids": supported})
        for i, e in enumerate(gold["expected_events"]):
            if i not in found:
                metrics["missed_sufficient_events"] += 1
                cases.append({"document_id": gold["document_id"], "name": e["name"], "outcome": "missed_sufficient_event"})
    selected = [by_id[g["document_id"]] for g in reference["documents"] if g["document_id"] in by_id]
    adjustments = [a for d in selected for a in d.get("adjustments", [])]
    return {"reference_author": reference["author"], "independent_human_review": False,
            "metrics": metrics, "cases": cases,
            "reference_uncertain_products": sum(len(d["uncertain_names"]) for d in reference["documents"]),
            "processing_audit": {
                "stage": "after deterministic preparation and evidence validation; not raw model accuracy",
                "calendar_adjustments": sum(a["field"] == "launch_date" for a in adjustments),
                "feature_adjustments": sum(a["field"] == "features" for a in adjustments),
                "rejected_claims": sum(len(d.get("rejected", [])) for d in selected),
            },
            "scope": "fixed source documents, not market coverage; matching against AI reference candidates"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--reference-sha256", required=True)
    a = p.parse_args()
    raw = a.reference.read_bytes()
    if hashlib.sha256(raw).hexdigest() != a.reference_sha256:
        p.error("reference changed since freeze")
    print(json.dumps(evaluate(json.loads(a.review.read_text()), json.loads(raw)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
