"""검토한 콘텐츠 후보의 상품 사실만 주간 발행에 연결한다 (ADR-0020).

수집기나 기사 추출기가 아니다. 입력은 비공개 candidates/<week>.json이며
본문·검토 메모는 공개 항목으로 복사하지 않는다. 카탈로그 diff도 계산하지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import re
from urllib.parse import urlparse

from pipeline import curate, paths, weeks


def candidate_path(week: str):
    weeks.parse_week(week)
    return paths.CANDIDATES_DIR / f"{week}.json"


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"콘텐츠 후보: {label}가 비어 있다")
    return value


def _url(value, label: str) -> str:
    value = _text(value, label)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
        raise ValueError(f"콘텐츠 후보: {label}가 공개 HTTP 주소가 아니다")
    return value


def load(week: str, catalog_items: list[dict]) -> tuple[list[dict], dict]:
    """포함 후보만 반환한다. 잘못된 검토 입력은 발행 전에 명시적으로 거부한다."""
    path = candidate_path(week)
    if not path.exists():
        return [], {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("week") != week or payload.get("version") != 1:
        raise ValueError("콘텐츠 후보의 주차 또는 버전이 다르다")
    reviewed_at = datetime.fromisoformat(_text(payload.get("reviewed_at"), "검토 시점"))
    if reviewed_at.tzinfo is None:
        raise ValueError("콘텐츠 검토 시점의 시간대가 없다")
    reviewed_date = reviewed_at.astimezone(weeks.KST).date()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("콘텐츠 후보 entries가 목록이 아니다")
    existing = {item["id"]: item for item in catalog_items}
    seen = set()
    result = []
    held = 0
    matched = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("콘텐츠 후보가 객체가 아니다")
        key = _text(entry.get("id"), "후보 ID")
        if key in seen:
            raise ValueError(f"콘텐츠 후보 ID 중복: {key}")
        seen.add(key)
        review = entry.get("review") or {}
        _text(review.get("reason"), "판단 이유")
        if review.get("decision") == "hold":
            held += 1
            continue
        if review.get("decision") != "include":
            raise ValueError(f"콘텐츠 후보 {key}: 포함·보류 판단이 없다")
        _text(review.get("history"), "과거 관측 대조")
        _text(review.get("reviewed_by"), "검토 주체")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"콘텐츠 후보 {key}: 근거가 없다")
        read_urls = set()
        for source in evidence:
            url = _url(source.get("url"), "근거 URL")
            _text(source.get("origin_group"), "원자료 묶음")
            _text(source.get("note"), "확인한 사실")
            if source.get("access") in {"body", "video", "product_page"}:
                read_urls.add(url)
        facts = entry.get("product") or {}
        if facts.get("source_url") not in read_urls:
            raise ValueError(f"콘텐츠 후보 {key}: 공개할 출처의 상품 내용을 읽지 않았다")
        for field in ("source_id", "external_id", "name", "brand", "channel", "source_name"):
            _text(facts.get(field), field)
        if facts["channel"] not in curate.CATEGORIES_BY_CHANNEL:
            raise ValueError(f"콘텐츠 후보 {key}: 모르는 판매 채널")
        phase = facts.get("release_status")
        if phase not in {"released", "upcoming"}:
            raise ValueError(f"콘텐츠 후보 {key}: 소개 묶음이 없다")
        price = facts.get("price")
        if price is not None and (type(price) is not int or price < 0):
            raise ValueError(f"콘텐츠 후보 {key}: 잘못된 가격")
        for field in ("category", "blurb", "image_url"):
            if facts.get(field) is not None and not isinstance(facts[field], str):
                raise ValueError(f"콘텐츠 후보 {key}: {field}는 문자열 또는 null이어야 한다")
        if facts.get("image_url"):
            _url(facts["image_url"], "이미지 URL")
            _text(review.get("image_basis"), "이미지 참조 근거")
        released = facts.get("release_date")
        if released is not None:
            if not isinstance(released, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", released):
                raise ValueError(f"콘텐츠 후보 {key}: 출시일 형식 오류")
            day = date.fromisoformat(released)
            _text(review.get("date_basis"), "출시일 근거")
            if phase == "upcoming" and day <= reviewed_date:
                raise ValueError(f"콘텐츠 후보 {key}: 검토 시점에 이미 지난 예정일")
            if phase == "released" and (day > reviewed_date or weeks.week_of(day) != week):
                raise ValueError(f"콘텐츠 후보 {key}: 이번 주 출시로 소개할 날짜가 아니다")
        tags = facts.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"콘텐츠 후보 {key}: 잘못된 태그")
        match_id = entry.get("catalog_id")
        if match_id:
            # 이름만으로 자동 병합하지 않는다. 검토자가 특정 카탈로그 항목을 지정한다.
            _text(review.get("match_basis"), "카탈로그 연결 근거")
            if match_id not in existing or existing[match_id]["source_id"] != facts["source_id"]:
                raise ValueError(f"콘텐츠 후보 {key}: 연결할 카탈로그 항목이 없다")
            item = dict(existing[match_id])
            item.update({k: facts[k] for k in ("source_url", "source_name", "release_status", "release_date") if k in facts})
            matched += 1
        else:
            item = {k: facts.get(k) for k in ("name", "brand", "channel", "price", "category", "blurb",
                                             "image_url", "source_url", "source_name", "source_id", "external_id")}
            item.update(id=f"{facts['source_id']}--{facts['external_id']}", week=week, first_seen=week,
                        last_seen=week, tags=tags, release_status=phase)
            if released is not None:
                item["release_date"] = released
        result.append(item)
    return result, {"reviewed_at": payload["reviewed_at"], "included": len(result),
                    "held": held, "catalog_matches": matched}
