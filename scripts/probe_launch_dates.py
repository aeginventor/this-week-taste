"""동결된 추출기의 날짜 경계 진단. 합성 사례를 실제 발표 평가와 합치지 않는다."""
import argparse
import json
from pathlib import Path

from scripts.launch_claims import PROMPT, norm, prepare, validate
from scripts.newsroom_study import digest, invoke_local, local_config, save


def compare(claims, expected):
    rows = []
    for e in expected:
        candidates = [c for c in claims if norm(c.get("product_name", "")) == norm(e["name"])]
        rows.append({"name": e["name"], "expected_kind": e["kind"], "expected_date": e["date"],
                     "observed": [{"kind": c.get("kind"), "date": c.get("launch_date")} for c in candidates],
                     "exact": len(candidates) == 1 and candidates[0].get("kind") == e["kind"]
                     and candidates[0].get("launch_date") == e["date"]})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    if a.root.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        p.error("outputs must stay outside the public repository")
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/launch_date_boundaries.json"
    cases = json.loads(fixture.read_text())
    save(a.root / "freeze.json", {"fixture_sha256": digest(fixture.read_bytes()),
         "prompt_sha256": digest(PROMPT.encode()), "local": local_config(),
         "claims_code_sha256": digest(Path(__file__).with_name("launch_claims.py").read_bytes()),
         "origin": cases["origin"]})
    outcomes = []
    for doc in cases["documents"]:
        path = a.root / (doc["document_id"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            if not a.live:
                p.error("--live required for new model outputs")
            result = invoke_local(doc)
            if result.get("status") != "failed":
                normalized, result["adjustments"] = prepare(result["parsed"], doc)
                result["validated"] = validate(normalized, doc)
            save(path, result)
        rows = {"document_id": doc["document_id"], "raw": compare(result.get("parsed", {}).get("claims", []), doc["expected"]),
                "after_code": compare(result.get("validated", {}).get("claims", []), doc["expected"]),
                "adjustments": result.get("adjustments", []), "elapsed_seconds": result["elapsed_seconds"]}
        outcomes.append(rows)
        print(json.dumps({"document": doc["document_id"], "raw_correct": sum(x["exact"] for x in rows["raw"]),
                          "after_code_correct": sum(x["exact"] for x in rows["after_code"])}), flush=True)
    save(a.root / "evaluation.json", {"origin": cases["origin"], "outcomes": outcomes})


if __name__ == "__main__":
    main()
