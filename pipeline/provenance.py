"""중간 파일을 만든 입력이 지금도 같은지 검사한다 (ADR-0019).

지문은 내용 변경을 검출한다. 데이터의 사실성이나 과거 수집 과정은 증명하지 않는다.
경로 대신 저장소 안의 논리 이름만 기록한다. 다중 실행은 지원하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pipeline import paths, weeks

VERSION = 1


class InvalidEvidence(ValueError):
    """다시 생성하거나 입력을 복구해야 하는 중간 산출물."""


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def seal(payload: dict, inputs: dict) -> dict:
    body = {k: v for k, v in payload.items() if k != "proof"}
    proof = {"version": VERSION, "inputs": inputs}
    proof["sha256"] = digest({"body": body, "proof": proof})
    return {**body, "proof": proof}


def verify_seal(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise InvalidEvidence("객체 형식이 아니다")
    proof = payload.get("proof")
    if not isinstance(proof, dict) or proof.get("version") != VERSION:
        raise InvalidEvidence("입력 증명이 없다 — 중간 산출물을 재생해야 한다")
    if not isinstance(proof.get("inputs"), dict):
        raise InvalidEvidence("입력 증명 형식이 잘못됐다")
    if seal(payload, proof["inputs"])["proof"] != proof:
        raise InvalidEvidence("산출물 내용과 지문이 다르다")
    return proof["inputs"]


def _week_files(root: Path, source_id: str, week: str, *, raw: bool) -> dict:
    found = {}
    for directory in sorted(root.glob("????-W??")):
        weeks.parse_week(directory.name)
        if directory.name > week:
            continue
        files = (directory.joinpath(source_id).rglob("*") if raw else
                 [directory / f"{source_id}.json", directory / f"{source_id}.control.json"])
        for file in sorted(files):
            if file.is_file():
                found[str(file.relative_to(root))] = file_digest(file)
    return found


def observation_inputs(source_id: str, week: str) -> dict:
    from pipeline import snapshot
    weeks.parse_week(week)
    root = paths.REPO_ROOT
    code = list(root.joinpath("pipeline").glob("*.py")) + [
        root / "scrapers" / f"{source_id}.py", root / "scrapers/base.py",
        root / "sources/targets.yml", root / "requirements.txt",
    ]
    return {
        "snapshots": _week_files(snapshot.SNAPSHOT_DIR, source_id, week, raw=False),
        "raw": _week_files(paths.RAW_DIR, source_id, week, raw=True),
        "code": {str(p.relative_to(root)): file_digest(p) for p in sorted(code)},
    }


def check_observations(recorded: dict, current: dict, *, allow_new_raw: bool = False) -> None:
    expected = dict(current)
    if allow_new_raw:
        # 보강 단계는 raw에 새 상세 응답을 추가한다. 기존 응답의 교체는 허용하지 않는다.
        expected["raw"] = {key: current["raw"].get(key) for key in recorded.get("raw", {})}
    if recorded != expected:
        changed = [key for key in expected if recorded.get(key) != expected[key]]
        raise InvalidEvidence(f"입력이 달라졌다: {', '.join(changed)}")


def check_diff(result: dict, source_id: str, week: str) -> None:
    inputs = verify_seal(result)
    if result.get("week") != week or result.get("source_id") != source_id:
        raise InvalidEvidence("diff의 주차·소스가 다르다")
    check_observations(inputs, observation_inputs(source_id, week), allow_new_raw=True)


def publication_inputs(source_id: str, week: str, result: dict) -> dict:
    from pipeline import diff, enrich, publish
    previous = result.get("previous_week")
    return {
        "observations": observation_inputs(source_id, week),
        "diff": file_digest(diff.DIFF_DIR / week / f"{source_id}.json"),
        "enriched": file_digest(enrich.enriched_path(week, source_id)),
        "enriched_proof": file_digest(enrich.proof_path(week, source_id)),
        "previous_publication": file_digest(publish.week_path(previous)) if previous else None,
        "previous_report": file_digest(publish.WEEKS_DIR / f"{previous}.report.json") if previous else None,
    }


def check_part(payload: dict, source_id: str, week: str) -> None:
    from pipeline import diff, snapshot
    inputs = verify_seal(payload)
    if payload.get("week") != week or payload.get("source_id") != source_id:
        raise InvalidEvidence("부분 파일의 주차·소스가 다르다")
    items = payload.get("items")
    if (not isinstance(items, list) or not isinstance(payload.get("report"), dict)
            or any(not isinstance(i, dict) or i.get("source_id") != source_id for i in items)):
        raise InvalidEvidence("부분 파일의 항목·리포트 형식이 잘못됐다")
    result = json.loads((diff.DIFF_DIR / week / f"{source_id}.json").read_text())
    check_diff(result, source_id, week)
    current = snapshot.load_snapshot(week, source_id)
    if result.get("baseline") or not current or current.get("held_from"):
        raise InvalidEvidence("기준선 또는 이월본은 이번 주 발견을 발행하지 않는다")
    if publication_inputs(source_id, week, result) != inputs:
        raise InvalidEvidence("발행 입력이 달라졌다")
