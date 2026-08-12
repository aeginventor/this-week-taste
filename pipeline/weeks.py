"""ISO 주차 계산. 프로젝트 안에서 날짜를 주차 문자열로 바꾸는 곳은 여기 하나뿐이다.

CLAUDE.md 4장: week(`YYYY-Www`)가 프로젝트 전체의 척추다. 다른 날짜 포맷을 섞지 않는다.

주의: ISO 주차의 연도는 달력 연도와 다를 수 있다.
    2025-12-29(월) → 2026-W01   (달력은 2025년인데 ISO 연도는 2026년)
    2026-12-28(월) → 2026-W53   (2026년에는 53주차가 있다)
`strftime('%Y-W%V')`를 쓰면 앞의 경우가 `2025-W01`이 되어 조용히 틀린다.
반드시 `isocalendar()`가 주는 연도를 쓸 것.
"""

from __future__ import annotations

import datetime as dt
import re

KST = dt.timezone(dt.timedelta(hours=9), name="KST")

WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def week_of(date: dt.date) -> str:
    """날짜 → `YYYY-Www`."""
    iso_year, iso_week, _ = date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


def current_week() -> str:
    """지금(KST) 기준 주차."""
    return week_of(now_kst().date())


def scraped_at() -> str:
    """스냅샷 항목의 `scraped_at`용 KST ISO8601 문자열."""
    return now_kst().replace(microsecond=0).isoformat()


def parse_week(week: str) -> tuple[int, int]:
    """`YYYY-Www` → (iso_year, iso_week). 형식이 틀리면 ValueError."""
    m = WEEK_RE.match(week)
    if not m:
        raise ValueError(f"주차 형식이 아니다: {week!r} (기대: YYYY-Www)")
    iso_year, iso_week = int(m.group(1)), int(m.group(2))
    if not 1 <= iso_week <= 53:
        raise ValueError(f"주차 범위를 벗어났다: {week!r}")
    # 53주차가 없는 해를 걸러낸다. date.fromisocalendar가 ValueError를 던진다.
    dt.date.fromisocalendar(iso_year, iso_week, 1)
    return iso_year, iso_week


def monday_of(week: str) -> dt.date:
    """주차 → 그 주 월요일 날짜."""
    iso_year, iso_week = parse_week(week)
    return dt.date.fromisocalendar(iso_year, iso_week, 1)


def shift(week: str, weeks: int) -> str:
    """주차를 앞뒤로 이동. `shift('2026-W01', -1)` → `2025-W52`."""
    return week_of(monday_of(week) + dt.timedelta(weeks=weeks))


def previous_week(week: str) -> str:
    return shift(week, -1)
