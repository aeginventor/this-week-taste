"""상세 조회 상한. 없으면 diff가 깨졌을 때 소스 사이트로 요청이 그대로 나간다."""

import json

import pytest

from pipeline import alert, diff, enrich


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(diff, "DIFF_DIR", tmp_path / "diffs")
    monkeypatch.setattr(enrich, "ENRICHED_DIR", tmp_path / "enriched")
    return tmp_path


def _write_diff(dirs, source_id, n):
    """설명문 없는 신상 n건. 전부 상세 조회 대상이 된다."""
    path = diff.DIFF_DIR / "2026-W35" / f"{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    added = [{"external_id": str(i), "name": f"제품{i}", "description": None}
             for i in range(n)]
    path.write_text(json.dumps({"added": added}, ensure_ascii=False), encoding="utf-8")


def test_상한을_넘으면_긁지_않고_멈춘다(dirs, monkeypatch):
    called = []
    monkeypatch.setattr(enrich, "_detail_fetcher",
                        lambda sid: lambda *a, **k: called.append(1))
    _write_diff(dirs, "cu", enrich.MAX_DETAIL_FETCHES + 1)

    with pytest.raises(alert.PipelineAnomaly):
        enrich.run("cu", "2026-W35")

    assert called == [], "상한을 넘었으면 요청이 한 건도 나가면 안 된다"


def test_상한과_같으면_전부_긁는다(dirs, monkeypatch):
    """경계값. 상한 '초과'에서만 멈춰야 한다."""
    fetched = []

    def fake_detail(session, key, *, week):
        fetched.append(key)
        return {"name": f"제품{key}", "description": "설명", "tags": ["태그"]}

    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: fake_detail)
    _write_diff(dirs, "cu", enrich.MAX_DETAIL_FETCHES)

    enrich.run("cu", "2026-W35")  # 예외 없이 통과해야 한다

    assert len(fetched) == enrich.MAX_DETAIL_FETCHES
    saved = json.loads(enrich.enriched_path("2026-W35", "cu").read_text())
    assert len(saved) == enrich.MAX_DETAIL_FETCHES


def test_상세를_안_긁는_소스는_상한과_무관하다(dirs, monkeypatch):
    """홈플러스처럼 detail=False인 소스는 요청 자체가 없으니 막을 이유가 없다."""
    monkeypatch.setattr(enrich, "_detail_fetcher", lambda sid: None)
    _write_diff(dirs, "homeplus", enrich.MAX_DETAIL_FETCHES + 100)

    enrich.run("homeplus", "2026-W35")
