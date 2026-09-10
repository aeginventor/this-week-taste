"""발표의 의미를 잘못 해석해도 예외가 나지 않는 경계를 검증한다."""

import hashlib

import pytest

from scripts.link_launch_evidence import link, verified_documents


def item(name="티 라떼", external_id="01", source_id="cafe"):
    return {"source_id": source_id, "external_id": external_id, "name": name}


def claim(**overrides):
    return {"claim_id": "c1", "document_id": "d1", "source_id": "cafe",
            "product_name": "티 라떼", "event_kind": "new_launch", "occurred_on": "2026-08-28",
            "date_basis": "explicit_body", "catalog_context": "brand_catalog", **overrides}


def test_exact_name_is_only_a_candidate_not_confirmed_sku():
    r = link([item()], [claim()])[0]
    assert r["evidence_links"][0]["state"] == "candidate"
    assert not r["publication_authorized"]
    assert r["external_id"] == "01"


@pytest.mark.parametrize("overrides,reason", [
    ({"event_kind": "mention"}, "not_an_explicit_launch_event"),
    ({"date_basis": "publication_only"}, "launch_date_not_established"),
    ({"occurred_on": None}, "launch_date_not_established"),
    ({"catalog_context": "cinema_menu"}, "different_sales_context"),
])
def test_non_launch_dates_and_context_cannot_be_promoted(overrides, reason):
    r = link([item()], [claim(**overrides)])[0]
    assert not r["has_candidate"]
    assert r["evidence_links"][0]["reason"] == reason


def test_ice_variant_is_held():
    r = link([item("아이스 티 라떼")], [claim()])[0]
    assert r["evidence_links"][0]["reason"] == "variant_not_explicitly_identified"


def test_relaunch_kind_survives_without_deciding_display_policy():
    r = link([item()], [claim(event_kind="seasonal_return")])[0]["evidence_links"][0]
    assert r["event_kind"] == "seasonal_return"
    assert r["seasonal_display_policy"] == "undecided"


def test_same_name_in_other_brand_does_not_link():
    assert link([item(source_id="other")], [claim()])[0]["evidence_links"] == []


def test_multiple_exact_names_are_held_and_order_does_not_matter():
    items = [item(external_id="01"), item(external_id="02")]
    r = link(items, [claim()])
    assert all(x["evidence_links"][0]["reason"] == "multiple_catalog_candidates" for x in r)
    assert r == link(items[::-1], [claim()])


def test_changed_source_copy_fails_loudly(tmp_path):
    path = tmp_path / "article.html"
    path.write_bytes(b"original")
    manifest = {"documents": [{"document_id": "d1", "local_file": path.name,
                 "sha256": hashlib.sha256(b"original").hexdigest(), "url": "https://example.org/",
                 "published_on": "2026-08-27", "observed_on": "2026-09-09"}], "claims": [claim()]}
    assert verified_documents(manifest, tmp_path)[0]["document_id"] == "d1"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="document changed"):
        verified_documents(manifest, tmp_path)
