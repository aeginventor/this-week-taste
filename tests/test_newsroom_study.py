import json

import pytest

from scripts.launch_claims import link_family, rules, validate, resolve_date, prepare
from scripts.newsroom_study import parse_article, parse_listing, replay, digest


HTML = '''<article class="post family-sckcompany" id="post-1">
<h2 class="post-title">연구용 가상 출시</h2><ul class="post-info"><span class="date">2026.08.20</span></ul>
<div class="post-info">AI 요약: 가짜 출시</div>
<div class="post-contents"><p>스타벅스가 8월 25일 ‘호지 라떼’를 출시한다.</p>
<p>호지차와 우유로 만든 음료다.</p></div></article><article class="item">다른 기사</article>'''


def document():
    return parse_article(HTML, "https://www.shinsegaegroupnewsroom.com/example/")


def claim():
    return {"product_name": "호지 라떼", "brand": "스타벅스", "kind": "new_launch", "product_type": "drink",
        "context": "starbucks_menu", "launch_date": "2026-08-25", "date_text": "8월 25일", "scope": "family",
        "features": ["호지차"], "evidence": [{"paragraph": 1, "quote": "8월 25일 ‘호지 라떼’를 출시한다."},
                                            {"paragraph": 2, "quote": "호지차와 우유"}]}


def item(**changes):
    return {"source_id": "starbucks", "external_id": "01", "name": "호지 라떼", "category_raw": "티",
            "description": "호지차와 우유의 음료", **changes}


def test_body_excludes_ai_summary_and_related_articles():
    d = document()
    assert d["published_on"] == "2026-08-20"
    assert len(d["paragraphs"]) == 2
    assert all("가짜" not in p["text"] for p in d["paragraphs"])


def test_missing_body_is_failure_not_zero_claims():
    with pytest.raises(ValueError):
        parse_article(HTML.replace("post-contents", "changed"), "url")


@pytest.mark.parametrize("change", [
    {"features": ["초콜릿"]}, {"date_text": "8월 20일"},
    {"product_name": "다른 라떼"}, {"evidence": [{"paragraph": 20, "quote": "출시"}]},
])
def test_ungrounded_llm_fields_are_rejected(change):
    c = {**claim(), **change}
    result = validate({"document_kind": "launch", "claims": [c]}, document())
    assert result["claims"] == []
    assert len(result["rejected"]) == 1


def test_family_support_does_not_claim_ice_variant_launch():
    result = link_family(claim(), [item(), item(name="아이스 호지 라떼", external_id="02")])
    assert all(x["state"] == "family_supported" for x in result)
    assert all(not x["variant_launch_verified"] for x in result)


@pytest.mark.parametrize("change,reason", [
    ({"description": "이름만 같은 제품"}, "description_not_corroborated"),
    ({"category_raw": "머그"}, "product_type_not_verified"),
])
def test_name_alone_cannot_link(change, reason):
    assert link_family(claim(), [item(**change)])[0]["reason"] == reason


def test_sales_context_and_promotion_do_not_promote():
    c = {**claim(), "context": "retail"}
    assert link_family(c, [item()])[0]["state"] == "held"
    c = {**claim(), "kind": "promotion"}
    assert link_family(c, [item()])[0]["reason"] == "not_explicit_launch"


def test_duplicate_name_ids_are_ambiguous():
    assert all(x["reason"] == "ambiguous_duplicate_catalog_name"
               for x in link_family(claim(), [item(), item(external_id="02")]))


def test_common_ingredient_cannot_establish_same_recipe():
    c = {**claim(), "features": ["우유"]}
    assert link_family(c, [item(description="다른 차와 우유")])[0]["state"] == "held"


def test_listing_chooses_article_not_category_and_rejects_empty_page():
    html = '<article class="item"><a href="/family/sckcompany/">분류</a><a href="/article/">기사</a><span class="date">2026.08.20</span></article>'
    rows = parse_listing(html, "https://www.shinsegaegroupnewsroom.com/family/sckcompany/")
    assert rows == [{"url": "https://www.shinsegaegroupnewsroom.com/article/", "published_on": "2026-08-20"}]
    with pytest.raises(ValueError, match="empty listing"):
        parse_listing("<html></html>", "url")


def test_evaluation_does_not_reward_holding_everything():
    from scripts.evaluate_launch_study import evaluate
    gold = {"author": "AI", "documents": [{"document_id": "a", "uncertain_names": [], "expected_events": [
        {"name": "호지 라떼", "kind": "new_launch", "date": "2026-08-25", "linkable": True, "allowed_family_ids": ["01"]}]}]}
    review = {"documents": [{"document_id": "a", "status": "ok", "claims": [{**claim(), "links": []}]}]}
    metrics = evaluate(review, gold)["metrics"]
    assert metrics["correct_events"] == 1
    assert metrics["useful_family_events"] == 0
    assert metrics["held_linkable_events"] == 1
    review["documents"][0]["claims"][0]["links"] = [{"external_id": "wrong", "state": "family_supported"}]
    assert evaluate(review, gold)["metrics"]["wrong_family_events"] == 1
    review["documents"][0]["status"] = "failed"
    review["documents"][0]["claims"] = []
    metrics = evaluate(review, gold)["metrics"]
    assert metrics["failed_documents"] == metrics["missed_sufficient_events"] == 1


def test_rule_baseline_does_not_copy_publication_date():
    d = document()
    d["paragraphs"][0]["text"] = "스타벅스가 ‘호지 라떼’를 출시한다."
    assert rules(d)["claims"][0]["launch_date"] is None


@pytest.mark.parametrize("text,published,expected", [
    ("오는 28일", "2026-08-27", "2026-08-28"),
    ("오는 2일", "2026-12-30", "2027-01-02"),
    ("8월 25일", "2026-08-20", "2026-08-25"),
    ("오는 31일", "2026-02-20", None),
    ("다음 시즌", "2026-08-20", None),
])
def test_body_date_resolution_is_narrow(text, published, expected):
    assert resolve_date(text, published) == expected


def test_wrong_calendar_month_is_rejected_even_when_quote_exists():
    c = {**claim(), "launch_date": "2026-09-25"}
    r = validate({"document_kind": "launch", "claims": [c]}, document())
    assert not r["claims"]
    assert r["rejected"][0]["reason"] == "launch date contradicts body date expression"


def test_calendar_preparation_is_audited_without_mutating_model_output():
    c = {**claim(), "launch_date": "2026-09-25", "features": ["호지차", "초콜릿"]}
    raw = {"document_kind": "launch", "claims": [c]}
    prepared, adjustments = prepare(raw, document())
    assert raw["claims"][0]["launch_date"] == "2026-09-25"
    assert prepared["claims"][0]["launch_date"] == "2026-08-25"
    assert prepared["claims"][0]["features"] == ["호지차"]
    assert len(adjustments) == 2
    assert len(validate(prepared, document())["claims"]) == 1
    raw["claims"][0]["date_text"] = "다음 시즌"
    prepared, _ = prepare(raw, document())
    assert prepared["claims"][0]["launch_date"] is None


def test_local_generation_failure_retains_raw_output_and_never_executes_tools(monkeypatch):
    import scripts.newsroom_study as study
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"done": True, "done_reason": "stop", "message": {"content": "bad json", "tool_calls": [{"function": {"name": "shell"}}]}}
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def post(self, url, json, **kwargs):
            assert url == "http://127.0.0.1:11435/api/chat"
            assert "tools" not in json
            return Response()
    monkeypatch.setattr(study, "local_session", Session)
    result = study.invoke_local(document())
    assert result["status"] == "failed"
    assert "never executed" in result["error"]
    assert result["envelope"]["message"]["content"] == "bad json"


def test_changed_document_and_failed_extraction(tmp_path):
    raw = HTML.encode()
    (tmp_path / "article.html").write_bytes(raw)
    doc = {**document(), "raw_file": "article.html", "raw_sha256": digest(raw), "split": "evaluation", "duplicate_of": None}
    inv = {"documents": [doc], "listing_pages": []}
    (tmp_path / "inventory.json").write_text(json.dumps(inv))
    run = tmp_path / "run"; run.mkdir()
    (run / "config.json").write_text(json.dumps({"inventory_sha256": digest((tmp_path / "inventory.json").read_bytes())}))
    (run / "post-1.json").write_text(json.dumps({"raw_sha256": digest(raw), "status": "failed", "error": "synthetic timeout"}))
    catalog = tmp_path / "catalog.json"; catalog.write_text(json.dumps([item()]))
    a = replay(tmp_path, "run", catalog)
    assert a == replay(tmp_path, "run", catalog)
    assert a["documents"][0]["discovery_fallback"] == "unchanged"
    assert a["documents"][0]["claims"] == []
    (tmp_path / "article.html").write_bytes(raw + b"changed")
    with pytest.raises(ValueError, match="document changed"):
        replay(tmp_path, "run", catalog)
