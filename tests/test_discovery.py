"""실제 CU 중복 등록 사례의 구조와, 그 반대인 신제품 누락 경계를 지킨다."""

import copy
import itertools
import json

import pytest

from pipeline import alert, curate, diff, discovery, enrich, publish, snapshot


def entry(code, name="옥수수 케이크", barcode="8800000000001", price=2000, source="cu"):
    return {"source_id": source, "external_id": code, "alt_ids": {"barcode": barcode},
            "name": name, "price": price, "category_raw": "과자류",
            "source_url": f"https://example.com/items/{code}", "image_url": None,
            "scraped_at": "2026-08-31T10:00:00+09:00"}


def test_new_registration_cannot_consume_existing_catalog_entry():
    old = entry("old")
    new = entry("new")
    previous = [old, entry("stable", name="우유", barcode="8800000000002")]
    current = previous + [new]
    for before in itertools.permutations(previous):
        for after in itertools.permutations(current):
            result = diff.diff_items(list(before), list(after))
            assert [i["external_id"] for i in result["added"]] == ["new"]
            assert result["conflicts"] == []
            assessed = discovery.classify(result["added"], [{"week": "2026-W35", "items": previous}])
            assert assessed["items"] == []
            assert assessed["held"][0]["reason"] == "previously_observed_product"
            assert assessed["held"][0]["evidence"]["external_id"] == "old"


def test_ambiguous_aliases_are_all_held_instead_of_consumed_in_order():
    previous = [entry("old1"), entry("old2")]
    current = [entry("new1"), entry("new2")]
    for before in itertools.permutations(previous):
        for after in itertools.permutations(current):
            result = diff.diff_items(list(before), list(after))
            assert result["added"] == result["removed"] == []
            assert result["counts"]["matched"] == 0
            assert len(result["review"]) == 2
            assert all(len(p["candidates"]) == 2 for p in result["review"])


def test_missing_prices_and_equal_names_are_not_an_automatic_match():
    previous = [entry("old", barcode=None, price=None)]
    current = [entry("new", barcode=None, price=None)]
    result = diff.diff_items(previous, current)
    assert result["counts"]["matched"] == 0
    assert len(result["review"]) == 1


def test_all_similar_variants_are_held_when_only_one_old_candidate_exists():
    previous = [entry("old", barcode=None, price=None)]
    current = [entry("new1", barcode=None, price=None), entry("new2", barcode=None, price=None)]
    result = diff.diff_items(previous, current)
    assert result["added"] == result["removed"] == []
    assert len(result["review"]) == 2


def test_comparison_limit_does_not_turn_unchecked_pairs_into_discoveries(monkeypatch):
    monkeypatch.setattr(diff, "L4_PAIR_LIMIT", 0)
    with pytest.raises(alert.PipelineAnomaly, match="L4 비교 한도"):
        diff.diff_items([entry("old", barcode=None)], [entry("new", barcode=None, price=2100)])


@pytest.mark.parametrize("change", [
    {"name": "옥수수 케이크 2입"}, {"price": 2500}, {"price": None},
    {"alt_ids": {"barcode": "8800000000002"}}, {"alt_ids": {}}, {"source_id": "orion"},
])
def test_a_weak_or_conflicting_product_key_does_not_silently_remove_a_candidate(change):
    old, new = entry("old"), {**entry("new"), **change}
    result = discovery.classify([new], [{"week": "2026-W35", "items": [old]}])
    assert result["items"] == [new]
    assert result["held"] == []


def test_same_source_entry_reappearing_after_a_gap_is_not_first_discovery():
    old = entry("old", barcode=None)
    result = discovery.classify([old], [{"week": "2026-W20", "items": [old]}])
    assert result["items"] == []
    assert result["held"][0]["reason"] == "previously_observed_entry"
    assert result["held"][0]["evidence"]["week"] == "2026-W20"


def test_duplicate_batch_is_deterministic_and_does_not_mutate_inputs():
    items = [entry("b"), entry("a")]
    saved = copy.deepcopy(items)
    normal = discovery.classify(items, [])
    assert discovery.classify(items[::-1], []) == normal
    assert [i["external_id"] for i in normal["items"]] == ["a"]
    assert normal["held"][0]["reason"] == "duplicate_in_batch"
    assert items == saved


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(diff, "DIFF_DIR", tmp_path / "diffs")
    monkeypatch.setattr(enrich, "ENRICHED_DIR", tmp_path / "enriched")
    monkeypatch.setattr(publish, "PUBLISHED_DIR", tmp_path / "parts")
    monkeypatch.setattr(publish, "WEEKS_DIR", tmp_path / "weeks")
    monkeypatch.setenv("THIS_WEEK_TASTE_LLM", "off")
    monkeypatch.setattr(alert, "notify", lambda *args: None)
    return tmp_path


def save_snapshot(week, items, **extra):
    write_json(snapshot.snapshot_path(week, "cu"),
               {"week": week, "source_id": "cu", "count": len(items), "items": items, **extra})


def test_history_excludes_copied_and_future_observations_but_keeps_old_positive_evidence(isolated):
    save_snapshot("2026-W20", [entry("old")])
    save_snapshot("2026-W35", [entry("held")], held_from="2026-W20")
    save_snapshot("2026-W36", [entry("current")])
    save_snapshot("2026-W37", [entry("future")])
    history = discovery.history_for("cu", "2026-W36")
    assert [h["week"] for h in history] == ["2026-W20"]


def test_unreadable_history_does_not_mean_first_observation(isolated):
    path = snapshot.snapshot_path("2026-W35", "cu")
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    with pytest.raises(json.JSONDecodeError):
        discovery.assess("cu", "2026-W36", [entry("new")])


def test_publish_holds_known_product_even_when_llm_is_off_and_keeps_other_ids(isolated):
    old, repeat = entry("old"), entry("repeat")
    new = entry("new", name="딸기 우유", barcode="8800000000002")
    save_snapshot("2026-W35", [old])
    save_snapshot("2026-W36", [old, repeat, new])
    diff.run("cu", "2026-W36")
    part = publish.run("cu", "2026-W36")
    before = json.loads(part.read_text())
    assert [i["id"] for i in before["items"]] == ["cu--new"]
    assert before["items"][0]["source_url"] == new["source_url"]
    assert before["items"][0]["launch_status"] == "unverified"
    assert before["report"]["discovery"]["held"][0]["external_id"] == "repeat"
    publish.merge("2026-W36")
    publish.run("cu", "2026-W36")
    after = json.loads(part.read_text())
    assert after["items"] == before["items"]
    assert after["report"] == before["report"]


def test_editor_cannot_promote_an_item_to_launch_confirmed():
    item = entry("new")
    result = publish._publish_item(item, week="2026-W36", source_id="cu", previous=None,
        enriched={}, curated={"new": {"launch_status": "confirmed"}})
    assert result["launch_status"] == "unverified"
