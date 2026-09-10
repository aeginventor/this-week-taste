"""파일이 있다는 이유로 옛 관측·이월·잘못된 주차를 성공으로 세지 않는다."""
import json
from scripts.collection_status import inspect


def test_status_distinguishes_missing_held_and_wrong_week(tmp_path):
    folder = tmp_path / "snapshots/2026-W37"
    folder.mkdir(parents=True)
    for source, extra in [("good", {}), ("held", {"held_from": "2026-W35"}),
                          ("old", {"scraped_at": "2026-08-24T10:00:00+09:00"}),
                          ("wrong", {"week": "2026-W36"}), ("count", {"count": 2})]:
        (folder / f"{source}.json").write_text(json.dumps({
            "week": "2026-W37", "source_id": source, "scraped_at": "2026-09-07T10:00:00+09:00",
            "count": 1, "items": [{"name": "테스트"}], **extra}))
    rows = inspect(tmp_path, "2026-W37", ["good", "held", "old", "wrong", "count", "missing"])
    assert [row["state"] for row in rows] == ["success", "held", "wrong_observation_week", "invalid", "invalid", "missing"]
