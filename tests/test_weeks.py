import datetime as dt

import pytest

from pipeline import weeks


def test_week_of_ordinary_date():
    assert weeks.week_of(dt.date(2026, 8, 11)) == "2026-W33"


def test_iso_year_differs_from_calendar_year():
    """달력 연도를 쓰면 조용히 틀리는 경계. strftime('%Y-W%V')는 여기서 2025-W01을 준다."""
    assert weeks.week_of(dt.date(2025, 12, 29)) == "2026-W01"
    assert weeks.week_of(dt.date(2026, 1, 1)) == "2026-W01"


def test_year_with_53_weeks():
    assert weeks.week_of(dt.date(2026, 12, 28)) == "2026-W53"
    assert weeks.week_of(dt.date(2027, 1, 3)) == "2026-W53"
    assert weeks.week_of(dt.date(2027, 1, 4)) == "2027-W01"


def test_parse_week_roundtrip():
    for w in ["2026-W01", "2026-W33", "2026-W53"]:
        assert weeks.week_of(weeks.monday_of(w)) == w


@pytest.mark.parametrize("bad", ["2026-W", "2026W33", "26-W33", "2026-W00", "2026-W54", ""])
def test_parse_week_rejects_bad_format(bad):
    with pytest.raises(ValueError):
        weeks.parse_week(bad)


def test_parse_week_rejects_nonexistent_53rd_week():
    """2025년에는 53주차가 없다."""
    with pytest.raises(ValueError):
        weeks.parse_week("2025-W53")


def test_previous_week_crosses_year_boundary():
    assert weeks.previous_week("2026-W01") == "2025-W52"
    assert weeks.previous_week("2027-W01") == "2026-W53"
    assert weeks.previous_week("2026-W33") == "2026-W32"


def test_scraped_at_is_kst_iso8601():
    s = weeks.scraped_at()
    assert s.endswith("+09:00")
    assert dt.datetime.fromisoformat(s).utcoffset() == dt.timedelta(hours=9)
