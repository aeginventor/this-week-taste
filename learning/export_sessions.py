#!/usr/bin/env python3
"""Claude Code 세션 기록(JSONL)을 읽을 수 있는 마크다운으로 바꾼다.

Claude Code는 세션마다 전문을 `~/.claude/projects/<프로젝트>/<uuid>.jsonl`에 남긴다.
사람이 읽을 형태가 아니라서(한 줄에 JSON 하나, 도구 결과가 통째로 박혀 있다)
`learning/raw/`에 마크다운으로 옮겨둔다. raw/ 는 커밋하지 않는다.

    python learning/export_sessions.py

도구 결과는 길어서 앞부분만 남긴다. 전문이 필요하면 원본 JSONL을 보면 된다.
"""
from __future__ import annotations

import json
import pathlib
import sys

PROJECT = "-Users-sankim-dev-this-week-taste"
SOURCE = pathlib.Path.home() / ".claude" / "projects" / PROJECT
TARGET = pathlib.Path(__file__).resolve().parent / "raw"

TOOL_RESULT_CHARS = 600   # 도구 결과를 이만큼만 남긴다
THINKING_CHARS = 1500

# `claude -p`(헤드리스) 호출도 세션으로 기록된다. curate 검증처럼 파이프라인이
# 프로그램적으로 부른 것까지 남기면 실제 작업 기록이 묻힌다. 사람이 여러 번
# 주고받은 세션만 남긴다.
MIN_USER_TURNS = 3


def _blocks(content) -> list[tuple[str, str]]:
    """content를 (종류, 텍스트) 목록으로 편다."""
    if isinstance(content, str):
        return [("text", content)]
    if not isinstance(content, list):
        return []

    out = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            out.append(("text", block.get("text", "")))
        elif kind == "thinking":
            out.append(("thinking", block.get("thinking", "")))
        elif kind == "tool_use":
            args = json.dumps(block.get("input", {}), ensure_ascii=False)
            out.append(("tool_use", f"{block.get('name')}({args})"))
        elif kind == "tool_result":
            body = block.get("content")
            if isinstance(body, list):
                body = "".join(b.get("text", "") for b in body
                               if isinstance(b, dict) and b.get("type") == "text")
            out.append(("tool_result", str(body or "")))
    return out


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… (총 {len(text):,}자, 이하 생략)"


def _records(path: pathlib.Path):
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue


def user_turns(path: pathlib.Path) -> int:
    """사람이 실제로 입력한 턴 수. 도구 결과만 담긴 user 레코드는 세지 않는다."""
    count = 0
    for record in _records(path):
        if record.get("type") != "user":
            continue
        blocks = _blocks((record.get("message") or {}).get("content"))
        if any(kind == "text" and text.strip() for kind, text in blocks):
            count += 1
    return count


def convert(path: pathlib.Path) -> str:
    lines = [f"# 세션 {path.stem[:8]}", ""]
    for record in _records(path):
        role = record.get("type")
        if role not in ("user", "assistant"):
            continue

        message = record.get("message") or {}
        for kind, text in _blocks(message.get("content")):
            if not text.strip():
                continue
            if kind == "text":
                lines += [f"## {'나' if role == 'user' else 'Claude'}", "", text.strip(), ""]
            elif kind == "thinking":
                lines += ["> **생각**", "> ", "> " + _clip(text, THINKING_CHARS)
                          .replace("\n", "\n> "), ""]
            elif kind == "tool_use":
                lines += ["```", f"▶ {_clip(text, 400)}", "```", ""]
            elif kind == "tool_result":
                lines += ["```", _clip(text, TOOL_RESULT_CHARS), "```", ""]
    return "\n".join(lines)


def main() -> int:
    if not SOURCE.is_dir():
        print(f"세션 기록이 없다: {SOURCE}", file=sys.stderr)
        return 1

    TARGET.mkdir(parents=True, exist_ok=True)
    for stale in TARGET.glob("*.md"):
        stale.unlink()

    found = sorted(SOURCE.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not found:
        print(f"JSONL이 없다: {SOURCE}", file=sys.stderr)
        return 1

    kept, skipped = 0, 0
    for path in found:
        turns = user_turns(path)
        if turns < MIN_USER_TURNS:
            skipped += 1
            continue
        kept += 1
        out = TARGET / f"{kept:02d}-{path.stem[:8]}.md"
        out.write_text(convert(path), encoding="utf-8")
        print(f"{out.name:<16} {turns:>3}턴  ← {path.stat().st_size // 1024:>5}KB")

    print(f"\n{kept}개 저장, {skipped}개 건너뜀(헤드리스 호출) → {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
