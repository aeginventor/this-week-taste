"""고정 기간 평가를 원시 모델·코드 처리·연결·검토량으로 나눠 집계한다."""
import argparse
import json
from pathlib import Path

from scripts.evaluate_launch_study import evaluate
from scripts.launch_claims import norm
from scripts.newsroom_study import digest, replay, save, verify_inventory


def dated_facts(documents, reference):
    """신규/복귀 유형이 불명확해도 본문의 출시 사실·일 단위 시점 누락은 별도로 센다."""
    by_id = {d["document_id"]: d for d in documents}
    result = {"expected": 0, "matched": 0, "missed": []}
    for gold in reference["documents"]:
        claims = by_id.get(gold["document_id"], {}).get("claims", [])
        for event in gold["expected_events"] + gold.get("dated_launch_unspecified", []):
            result["expected"] += 1
            found = any(norm(c["product_name"]) == norm(event["name"]) and c.get("launch_date") == event["date"]
                        and c.get("kind") in {"new_launch", "seasonal_return", "uncertain"} for c in claims)
            if found:
                result["matched"] += 1
            else:
                result["missed"].append({"document_id": gold["document_id"], "name": event["name"], "date": event["date"]})
    return result


def summarize(root, catalog):
    frozen = json.loads((root / "freeze.json").read_text())
    for filename, key in [("inventory.json", "inventory_sha256"), ("reference-frozen.json", "reference_sha256")]:
        if digest((root / filename).read_bytes()) != frozen[key]:
            raise ValueError(f"frozen input changed: {filename}")
    if digest(catalog.read_bytes()) != frozen["catalog_sha256"]:
        raise ValueError("catalog changed")
    for path, sha in frozen["files"].items():
        if digest(Path(path).read_bytes()) != sha:
            raise ValueError(f"frozen code changed: {path}")
    inventory = verify_inventory(root)
    reference = json.loads((root / "reference-frozen.json").read_text())
    gold = {d["document_id"]: d for d in reference["documents"]}
    report = {"coverage": {"listing_pages": len(inventory["listing_pages"]), "discovered_urls": inventory["discovered_urls"],
        "acquired_urls": len(inventory["documents"]), "failed_urls": inventory["failures"],
        "reused_bodies": sum(d.get("reused", False) for d in inventory["documents"]),
        "unique_bodies": sum(not d["duplicate_of"] for d in inventory["documents"]),
        "boundary_reached": inventory["boundary_reached"], "elapsed_seconds": inventory["elapsed_seconds"],
        "requests_excluding_robots": inventory["requests_excluding_robots"], "evaluation_documents": len(gold),
        "scope": "observed source listing only; omissions outside that listing and market coverage unknown"}, "methods": {}}
    for run in ["rules-evaluation-frozen", "qwen-evaluation-frozen"]:
        review = replay(root, run, catalog)
        save(root / f"{run}-review.json", review)
        raw_docs, seconds, tokens_in, tokens_out, raw_count, adjustments, rejected = [], 0, 0, 0, 0, 0, 0
        dates = {"correct_known_day": 0, "wrong_known_day": 0, "day_asserted_without_reference_support": 0,
                 "promotion_date_in_launch_field": 0, "missing_sufficient_day": 0}
        queue = {"documents_with_claims": 0, "claims": 0, "adjustments": 0, "rejected_claims": 0,
                 "supported_links": 0, "held_links": 0, "claims_without_catalog_candidate": 0}
        for d in review["documents"]:
            saved = json.loads((root / run / f"{d['document_id']}.json").read_text())
            claims = saved.get("parsed", {}).get("claims", [])
            seconds += saved.get("elapsed_seconds", 0)
            env = saved.get("envelope") or {}
            tokens_in += env.get("prompt_eval_count", 0); tokens_out += env.get("eval_count", 0)
            raw_count += len(claims)
            raw_docs.append({"document_id": d["document_id"], "status": saved["status"],
                             "claims": [{**c, "links": []} for c in claims]})
            expected = gold[d["document_id"]]
            known_dates = {norm(e["name"]): e.get("date") for e in expected["expected_events"] + expected.get("dated_launch_unspecified", [])}
            for c in claims:
                actual = c.get("launch_date")
                correct = known_dates.get(norm(c.get("product_name", "")))
                if c.get("kind") == "promotion":
                    dates["promotion_date_in_launch_field"] += actual is not None
                elif c.get("kind") in {"new_launch", "seasonal_return"}:
                    if correct:
                        dates["missing_sufficient_day" if actual is None else "correct_known_day" if actual == correct else "wrong_known_day"] += 1
                    elif actual:
                        dates["day_asserted_without_reference_support"] += 1
            adjustments += len(d["adjustments"]); rejected += len(d["rejected"])
            queue["documents_with_claims"] += bool(claims)
            queue["claims"] += len(claims)
            for c in d["claims"]:
                queue["claims_without_catalog_candidate"] += not c["links"]
                for link in c["links"]:
                    queue["supported_links" if link["state"] == "family_supported" else "held_links"] += 1
        queue.update(adjustments=adjustments, rejected_claims=rejected)
        report["methods"][run] = {"raw": evaluate({"documents": raw_docs}, reference),
            "after_code": evaluate(review, reference), "raw_date_audit": dates, "review_items": queue,
            "elapsed_seconds": seconds, "prompt_tokens": tokens_in, "output_tokens": tokens_out,
            "raw_claim_count": raw_count, "note": "queue counts overlap; not human minutes. Raw stage has no catalog linking."}
        report["methods"][run]["dated_facts_raw"] = dated_facts(raw_docs, reference)
        report["methods"][run]["dated_facts_after_code"] = dated_facts(review["documents"], reference)
        report["methods"][run]["raw"]["processing_audit"]["stage"] = "raw generated JSON, before evidence validation and normalization"
    save(root / "period-evaluation-with-facts.json", report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(summarize(a.root, a.catalog), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
