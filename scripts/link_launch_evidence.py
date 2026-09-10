"""검토한 출시 주장과 카탈로그를 연결하는 오프라인 연구 도구.

주장을 추출하거나 진실성을 인증하지 않는다. 정확한 이름도 연결 후보로만 반환한다.
네트워크·LLM·발행·파일 쓰기 없이 stdout에 비교 결과를 출력한다.
"""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import unicodedata


def normalized(name):
    return " ".join(unicodedata.normalize("NFKC", name).split())


def link(items, claims):
    """제품·사건·날짜를 각각 검사하며 공개 출시 상태를 만들지 않는다."""
    if len({c["claim_id"] for c in claims}) != len(claims):
        raise ValueError("duplicate claim_id")
    keys = [(i["source_id"], i["external_id"]) for i in items]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate catalog identity")
    for claim in claims:
        if claim["event_kind"] not in {"new_launch", "seasonal_return", "mention"}:
            raise ValueError("unknown event kind")
        if claim["date_basis"] not in {"explicit_body", "publication_only", "unknown"}:
            raise ValueError("unknown date basis")
        if claim.get("occurred_on"):
            date.fromisoformat(claim["occurred_on"])
    results = []
    for item in sorted(items, key=lambda i: (i["source_id"], i["external_id"])):
        matches = []
        for claim in sorted(claims, key=lambda c: c["claim_id"]):
            if claim["source_id"] != item["source_id"]:
                continue
            name, claim_name = normalized(item["name"]), normalized(claim["product_name"])
            if not name or not claim_name:
                raise ValueError("empty product name")
            exact = name == claim_name
            if not exact and claim_name not in name and name not in claim_name:
                continue
            same_name = [i for i in items if i["source_id"] == item["source_id"]
                         and normalized(i["name"]) == claim_name]
            if claim["catalog_context"] != "brand_catalog":
                state, reason = "held", "different_sales_context"
            elif claim["event_kind"] == "mention":
                state, reason = "held", "not_an_explicit_launch_event"
            elif not claim.get("occurred_on") or claim["date_basis"] != "explicit_body":
                state, reason = "held", "launch_date_not_established"
            elif not exact:
                state, reason = "held", "variant_not_explicitly_identified"
            elif len(same_name) != 1:
                state, reason = "held", "multiple_catalog_candidates"
            else:
                state, reason = "candidate", "exact_name_without_official_catalog_key"
            matches.append({
                "claim_id": claim["claim_id"], "document_id": claim["document_id"],
                "state": state, "reason": reason, "event_kind": claim["event_kind"],
                "occurred_on": claim.get("occurred_on"), "date_basis": claim["date_basis"],
                "seasonal_display_policy": "undecided" if claim["event_kind"] == "seasonal_return" else None,
            })
        results.append({
            "source_id": item["source_id"], "external_id": item["external_id"],
            "name": item["name"], "source_url": item.get("source_url"),
            "evidence_links": matches, "has_candidate": any(m["state"] == "candidate" for m in matches),
            "publication_authorized": False,
        })
    return results


def verified_documents(manifest, directory):
    result = []
    ids = set()
    for doc in manifest["documents"]:
        if doc["document_id"] in ids:
            raise ValueError("duplicate document_id")
        ids.add(doc["document_id"])
        path = directory / doc["local_file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != doc["sha256"]:
            raise ValueError(f"document changed: {doc['document_id']}")
        result.append({k: doc[k] for k in ["document_id", "url", "sha256", "published_on", "observed_on"]})
    if any(c["document_id"] not in ids for c in manifest["claims"]):
        raise ValueError("claim references missing document")
    return sorted(result, key=lambda d: d["document_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--selection", type=Path, help="전체 입력에서 출력할 source_id/external_id 목록")
    args = parser.parse_args()
    catalog_bytes, evidence_bytes = args.catalog.read_bytes(), args.evidence.read_bytes()
    manifest = json.loads(evidence_bytes)
    documents = verified_documents(manifest, args.evidence.parent)
    catalog = json.loads(catalog_bytes)
    linked = link(catalog, manifest["claims"])
    input_hashes = {"catalog": hashlib.sha256(catalog_bytes).hexdigest(),
                    "evidence": hashlib.sha256(evidence_bytes).hexdigest()}
    if args.selection:
        selection_bytes = args.selection.read_bytes()
        selected = {(i["source_id"], i["external_id"]) for i in json.loads(selection_bytes)}
        available = {(i["source_id"], i["external_id"]) for i in catalog}
        if not selected or not selected <= available:
            raise ValueError("selection is empty or missing from catalog")
        linked = [i for i in linked if (i["source_id"], i["external_id"]) in selected]
        input_hashes["selection"] = hashlib.sha256(selection_bytes).hexdigest()
    result = {
        "mode": "offline_research_not_publication", "claims_reviewed_by": manifest["reviewed_by"],
        "limitations": "manual claims; hashes check saved input integrity, not source truth or SKU identity",
        "inputs_sha256": input_hashes, "catalog_context_count": len(catalog),
        "documents": documents,
        "items": linked,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
