"""격리된 공식 문서 사본과 저장 카탈로그의 작은 표본을 비교한다.

네트워크·발행·파일 쓰기를 수행하지 않는다. 문서 샘플은 실시간 API 응답이 아니다.
출시 해석은 학습 기록의 AI 검토이며 이 스크립트가 자동 판정하지 않는다.
"""

import argparse
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

from pipeline import diff


CASES = {
    "cu": ["28123", "28108"],
    "starbucks": ["9200000007161", "9200000002259", "9200000007164", "9200000007181"],
    "pizzahut": ["RPPZ2238"],
    "kyochon": ["40367"],
}


def compare(data_dir, documents):
    inputs = {}

    def read(path):
        content = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(content).hexdigest()
        return content.decode()

    def sample(name, first_header):
        soup = BeautifulSoup(read(documents / f"{name}.html"), "html.parser")
        for table in soup.find_all("table"):
            rows = [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                    for row in table.find_all("tr")]
            if rows and rows[0][0] == first_header:
                return rows[1:]
        raise ValueError(f"{name}: expected document sample table missing")

    barcode_rows = sample("C005", "품목보고(신고)번호")
    report_rows = sample("I1250", "인허가번호")
    cases = []
    for source, ids in CASES.items():
        snapshots = {
            week: json.loads(read(data_dir / "snapshots" / week / f"{source}.json"))
            for week in ["2026-W35", "2026-W36"]
        }
        before, after = [snapshots[w]["items"] for w in snapshots]
        result = diff.diff_items(before, after)
        added = {x["external_id"] for x in result["added"]}
        old_ids = {x["external_id"] for x in before}
        for external_id in ids:
            item = next(x for x in after if x["external_id"] == external_id)
            barcode = item.get("alt_ids", {}).get("barcode")
            cases.append({
                "source_id": source, "external_id": external_id, "name": item["name"],
                "barcode": barcode, "source_url": item.get("source_url"),
                "present_w35": external_id in old_ids, "current_diff_added": external_id in added,
                "same_barcode_name_price_in_w35": [x["external_id"] for x in before
                    if barcode and x.get("alt_ids", {}).get("barcode") == barcode
                    and x["name"] == item["name"] and x["price"] == item["price"]],
                "c005_document_sample_matches": [r[0] for r in barcode_rows if barcode and r[-1] == barcode],
                "api_live_lookup": "not_performed",
            })

    by_report = {}
    for row in barcode_rows:
        by_report.setdefault(row[0], set()).add(row[-1])
    specifications = {}
    for name in ["haccp", "foodqr-api"]:
        spec = json.loads(read(documents / f"{name}-spec.json"))
        specifications[name] = {
            "host": spec["host"],
            "request_fields": {path: [p["name"] for p in op.get("parameters", [])]
                               for path, op in spec["paths"].items()},
        }
    # A failed/mismatched input must not silently become a reassuring empty result.
    if not barcode_rows or not report_rows or len(cases) != 8:
        raise ValueError("incomplete experiment inputs")
    return {
        "checked_on": "2026-09-09", "selection": "purposive counterexamples; not random or representative",
        "method": "offline document samples + saved W35/W36; no API calls, LLM, or publication",
        "cases": cases,
        "document_samples": {
            "C005_rows": len(barcode_rows), "I1250_rows": len(report_rows),
            "report_to_multiple_barcodes": {k: sorted(v) for k, v in by_report.items() if len(v) > 1},
            "warning": "sample misses do not establish absence from the full API",
        },
        "specifications": specifications, "inputs_sha256": inputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.data_dir, args.documents), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
