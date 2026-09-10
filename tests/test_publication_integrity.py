"""오래된 부분 파일·이월·중간 실패가 성공처럼 보이는 경계를 격리해 검증한다."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import alert, curate, diff, enrich, paths, provenance, publish, snapshot, weeks

WEEK = "2026-W36"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    for module, name, directory in [
        (paths, "RAW_DIR", "raw"), (snapshot, "SNAPSHOT_DIR", "snapshots"),
        (diff, "DIFF_DIR", "diffs"), (enrich, "ENRICHED_DIR", "enriched"),
        (publish, "PUBLISHED_DIR", "published"), (publish, "WEEKS_DIR", "weeks"),
    ]:
        monkeypatch.setattr(module, name, tmp_path / directory)
    monkeypatch.setattr(curate, "curate", lambda *a, **k: {})
    monkeypatch.setattr(alert, "notify", lambda *a, **k: None)
    return tmp_path


def entry(source, key):
    return {"source_id": source, "external_id": key, "name": key, "alt_ids": {},
            "price": 1000, "source_url": f"https://example.test/{source}/{key}",
            "category_raw": "간편식사", "description": None, "tags": []}


def write_snapshot(source, week, items, **extra):
    provenance.atomic_json(snapshot.snapshot_path(week, source), {
        "week": week, "source_id": source, "scraped_at": "2026-09-01T09:00:00+09:00",
        "count": len(items), "items": items, **extra,
    })


def successful(source="cu"):
    old, new = entry(source, "rice"), entry(source, "milk")
    write_snapshot(source, "2026-W35", [old])
    write_snapshot(source, WEEK, [old, new])
    raw = paths.RAW_DIR / WEEK / source / "list.json"
    provenance.atomic_json(raw, {"sample": "source response"})
    diff.run(source, WEEK)
    return publish.run(source, WEEK)


def read(path):
    return json.loads(path.read_text())


def test_same_week_success_survives_failed_rerun_with_observation_timestamp(isolated):
    part = successful()
    original = part.read_bytes()
    publish.merge(WEEK, failed_sources=["cu"])
    payload = read(publish.week_path(WEEK))
    assert [i["id"] for i in payload["items"]] == ["cu--milk"]
    assert payload["source_statuses"]["cu"] == {
        "status": "reused", "brand": "CU", "scraped_at": "2026-09-01T09:00:00+09:00",
        "generated_at": read(part)["generated_at"],
    }
    assert part.read_bytes() == original
    assert publish.load_week(WEEK)["generation_id"] == read(publish.WEEKS_DIR / f"{WEEK}.report.json")["generation_id"]


@pytest.mark.parametrize("changed", ["snapshot", "raw", "diff", "enriched", "part", "history", "missing_raw"])
def test_changed_evidence_excludes_one_source_and_preserves_other(isolated, changed):
    part = successful()
    successful("orion")
    files = {
        "snapshot": snapshot.snapshot_path(WEEK, "cu"),
        "raw": paths.RAW_DIR / WEEK / "cu/list.json",
        "diff": diff.DIFF_DIR / WEEK / "cu.json",
        "enriched": enrich.enriched_path(WEEK, "cu"),
        "part": part,
        "history": snapshot.snapshot_path("2026-W35", "cu"),
        "missing_raw": paths.RAW_DIR / WEEK / "cu/list.json",
    }
    if changed == "missing_raw":
        files[changed].unlink()
    else:
        provenance.atomic_json(files[changed], {"changed": True})
    publish.merge(WEEK, failed_sources=["cu"])
    result = read(publish.week_path(WEEK))
    assert result["sources"] == ["orion"]
    assert result["source_statuses"]["cu"]["status"] == "excluded"
    assert str(isolated) not in json.dumps(result)
    assert part.exists(), "검증 실패 파일도 조사 근거로 남긴다"


def test_new_baseline_cannot_resurrect_an_old_part(isolated):
    successful()
    publish.merge(WEEK)
    before = publish.week_path(WEEK).read_bytes()
    snapshot.snapshot_path("2026-W35", "cu").unlink()
    diff.run("cu", WEEK)
    assert publish.run("cu", WEEK) is None
    with pytest.raises(provenance.InvalidEvidence):
        publish.merge(WEEK)
    assert publish.week_path(WEEK).read_bytes() == before


def test_new_detail_raw_is_allowed_but_existing_raw_replacement_is_not(isolated):
    successful()
    provenance.atomic_json(paths.RAW_DIR / WEEK / "cu/detail_milk.json", {"description": "detail"})
    provenance.check_diff(read(diff.DIFF_DIR / WEEK / "cu.json"), "cu", WEEK)
    publish.run("cu", WEEK)
    publish.merge(WEEK)
    provenance.atomic_json(paths.RAW_DIR / WEEK / "cu/list.json", {"different": True})
    with pytest.raises(provenance.InvalidEvidence):
        publish.run("cu", WEEK)


def test_code_change_requires_regeneration(isolated, monkeypatch):
    successful()
    original = provenance.observation_inputs
    def changed(*args):
        inputs = original(*args)
        inputs["code"]["pipeline/diff.py"] = "changed"
        return inputs
    monkeypatch.setattr(provenance, "observation_inputs", changed)
    with pytest.raises(provenance.InvalidEvidence):
        publish.merge(WEEK)


def test_publish_detects_input_change_during_editor_call_and_preserves_success(isolated, monkeypatch):
    part = successful()
    before = part.read_bytes()
    def edit(*a, **k):
        provenance.atomic_json(snapshot.snapshot_path(WEEK, "cu"), {"changed": True})
        return {}
    monkeypatch.setattr(curate, "curate", edit)
    with pytest.raises(provenance.InvalidEvidence):
        publish.run("cu", WEEK)
    assert part.read_bytes() == before


def test_enriched_content_must_be_bound_to_current_diff(isolated):
    successful()
    path = enrich.enriched_path(WEEK, "cu")
    provenance.atomic_json(path, {"milk": {"description": "old detail", "tags": []}})
    assert enrich.load_enriched(WEEK, "cu") == {}, "옛 파일의 존재는 근거가 아니다"
    checksum = provenance.file_digest(diff.DIFF_DIR / WEEK / "cu.json")
    enrich._write(WEEK, "cu", {"milk": {"description": "verified detail", "tags": []}},
                  failures=0, total=1, diff_hash=checksum)
    assert enrich.load_enriched(WEEK, "cu")["milk"]["description"] == "verified detail"
    provenance.atomic_json(path, {"milk": {"description": "tampered", "tags": []}})
    assert enrich.load_enriched(WEEK, "cu") == {}


def test_held_chain_does_not_reset_four_week_lookback(isolated):
    old = entry("cu", "rice")
    write_snapshot("cu", "2026-W30", [old])
    for n in range(31, 37):
        write_snapshot("cu", f"2026-W{n}", [old], held_from="2026-W30")
    write_snapshot("cu", "2026-W37", [old, entry("cu", "milk")])
    result = read(diff.run("cu", "2026-W37"))
    assert result["baseline"] is True
    assert result["previous_week"] is None
    assert result["counts"]["added"] == 0
    assert snapshot._hold_previous("2026-W38", "cu") is True
    assert read(snapshot.snapshot_path("2026-W38", "cu"))["held_from"] == "2026-W37"


def test_gap_uses_real_observation_and_current_hold_never_publishes(isolated):
    old = entry("cu", "rice")
    write_snapshot("cu", "2026-W34", [old])
    write_snapshot("cu", "2026-W35", [old], held_from="2026-W34")
    write_snapshot("cu", WEEK, [old, entry("cu", "milk")])
    result = read(diff.run("cu", WEEK))
    assert result["gap_weeks"] == 2 and result["previous_week"] == "2026-W34"
    write_snapshot("cu", WEEK, [old], held_from="2026-W34")
    assert read(diff.run("cu", WEEK))["baseline"] is True
    assert publish.run("cu", WEEK) is None


def test_partial_json_write_failure_preserves_public_week_and_rerun_repairs_pair(isolated, monkeypatch):
    successful()
    publish.merge(WEEK)
    before = publish.week_path(WEEK).read_bytes()
    replace = provenance.os.replace
    def fail_week(src, dst):
        if Path(dst) == publish.week_path(WEEK):
            raise OSError("injected disk failure")
        return replace(src, dst)
    with monkeypatch.context() as m:
        m.setattr(provenance.os, "replace", fail_week)
        with pytest.raises(OSError):
            publish.merge(WEEK)
    assert publish.week_path(WEEK).read_bytes() == before
    with pytest.raises(provenance.InvalidEvidence):
        publish.load_week(WEEK)
    assert not list(publish.WEEKS_DIR.glob("*.tmp"))
    publish.merge(WEEK)
    assert publish.load_week(WEEK)["counts"]["total"] == 1


@pytest.mark.parametrize("kind", ["legacy", "wrong_week", "wrong_source", "invalid_item"])
def test_part_schema_and_legacy_are_not_silently_trusted(isolated, kind):
    part = successful()
    value = read(part)
    if kind == "legacy":
        value.pop("proof")
    else:
        if kind == "wrong_week":
            value["week"] = "2026-W35"
        elif kind == "wrong_source":
            value["source_id"] = "orion"
        else:
            value["items"][0].pop("source_url")
        value = provenance.seal(value, value["proof"]["inputs"])
    provenance.atomic_json(part, value)
    with pytest.raises(provenance.InvalidEvidence):
        publish.merge(WEEK)


def test_week_all_does_not_hide_merge_failure(tmp_path):
    shutil.copy(paths.REPO_ROOT / "Makefile", tmp_path / "Makefile")
    fake = tmp_path / "fake-python"
    fake.write_text('#!/bin/sh\ncase "$*" in *--merge*) exit 17;; esac\nexit 0\n')
    fake.chmod(0o755)
    result = subprocess.run(["make", "week-all", "ONLY=cu", f"PY={fake}", f"WEEK={WEEK}"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "✅ 완료" not in result.stdout
