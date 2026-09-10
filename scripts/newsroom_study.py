"""SCK 공식 발표 연구: 일회 수집 / 별도 추출 / 저장 출력 재현. 발행 기능 없음."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests

from scripts.launch_claims import PROMPT, link_family, rules, validate, prepare

HOST = "www.shinsegaegroupnewsroom.com"
START_URL = f"https://{HOST}/family/sckcompany/"
DEVELOPMENT_SLUG = "starbucks-launches-new-hojicha-glazed-tea-latte"
LOCAL_URL = "http://127.0.0.1:11435"
LOCAL_MODEL = "qwen3:8b"
LOCAL_OPTIONS = {"temperature": 0, "seed": 41, "num_ctx": 8192, "num_predict": 4096}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"refusing to replace existing artifact: {path.name}")
        return
    path.write_text(text)


def parse_article(html, url):
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.post.family-sckcompany")
    if article is None:
        raise ValueError("missing official SCK article")
    title, dt, body = article.select_one(".post-title"), article.select_one(".post-info .date"), article.select_one(".post-contents")
    if not title or not dt or not body:
        raise ValueError("missing title/date/body")
    published = datetime.strptime(dt.get_text(strip=True), "%Y.%m.%d").date().isoformat()
    paragraphs = []
    for dom_index, node in enumerate(body.find_all(["p", "h2", "h3", "li"]), 1):
        if node.find_parent(["p", "li"]):
            continue
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        paragraphs.append({"number": len(paragraphs) + 1, "dom_block_index": dom_index, "text": text})
    if not paragraphs:
        raise ValueError("empty body")
    article_id = article.get("id") or ""
    if not re.fullmatch(r"post-\d+", article_id):
        article_id = "doc-" + digest(url.encode())[:16]
    return {"document_id": article_id, "url": url,
            "title": title.get_text(" ", strip=True), "published_on": published,
            "source_id": "starbucks", "paragraphs": paragraphs,
            "body_sha256": digest(json.dumps([p["text"] for p in paragraphs], ensure_ascii=False).encode())}


def parse_listing(html, url):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for node in soup.select("article.item"):
        dt = node.select_one(".date")
        anchor = node.select_one("a[href]")
        # 기사 카드의 첫 링크가 분류이면 제목을 가진 다음 링크를 사용한다.
        for a in node.select("a[href]"):
            u = urljoin(url, a["href"])
            if urlsplit(u).hostname == HOST and not any(s in urlsplit(u).path for s in ["/category/", "/family/", "/tag/"]):
                anchor = a
                break
        if not dt or not anchor:
            raise ValueError("listing card lacks date/link")
        u = urljoin(url, anchor["href"])
        if urlsplit(u).hostname != HOST:
            raise ValueError("off-host article link")
        records.append({"url": u, "published_on": datetime.strptime(dt.get_text(strip=True), "%Y.%m.%d").date().isoformat()})
    if not records:
        raise ValueError("empty listing")
    return records


def collect(root, start, end, reuse_root=None):
    from scrapers.base import Session
    if (root / "inventory.json").exists():
        raise ValueError("collection already exists; use saved inputs, no implicit refresh")
    root.mkdir(parents=True, exist_ok=True)
    save(root / "collection-plan.json", {"start": start, "end": end, "max_pages": 5, "max_articles": 40,
                                        "reuse_root": str(reuse_root) if reuse_root else None})
    reusable = {d["url"]: d for d in verify_inventory(reuse_root)["documents"]} if reuse_root else {}
    class ResearchSession(Session):
        def _archive_robots(self, origin, response):
            raw = response.content
            (root / "robots.txt").write_bytes(raw)
            save(root / "robots-meta.json", {"url": origin + "/robots.txt", "sha256": digest(raw),
                 "status_code": response.status_code, "observed_at": datetime.now(timezone.utc).isoformat()})
    session = ResearchSession()
    if (root / "robots-meta.json").exists():
        # 동일한 일회 수집의 파서 수정/중단 복구는 받은 robots와 응답을 재사용한다.
        from urllib.robotparser import RobotFileParser
        meta = json.loads((root / "robots-meta.json").read_text())
        raw = (root / "robots.txt").read_bytes()
        if digest(raw) != meta["sha256"] or meta["status_code"] != 200:
            raise ValueError("saved robots cannot be verified")
        rp = RobotFileParser(); rp.parse(raw.decode().splitlines())
        session._robots[f"https://{HOST}"] = rp
        session._apply_limits(f"https://{HOST}", rp, raw.decode())

    def acquire(url, filename):
        path = root / filename
        meta_path = root / (filename + ".http.json")
        if path.exists():
            meta = json.loads(meta_path.read_text())
            if meta["url"] != url or meta["sha256"] != digest(path.read_bytes()):
                raise ValueError("saved response changed")
            return path.read_bytes(), meta
        if url in reusable:
            doc = reusable[url]
            raw = (reuse_root / doc["raw_file"]).read_bytes()
            meta = {"url": url, "sha256": digest(raw), "observed_at": doc["observed_at"], "reused": True}
        else:
            response = session.get(url, allow_redirects=False)
            raw = response.content
            meta = {"url": url, "sha256": digest(raw), "observed_at": datetime.now(timezone.utc).isoformat(),
                    "reused": False, "status_code": response.status_code}
        path.write_bytes(raw)
        save(meta_path, meta)
        if meta.get("status_code", 200) != 200:
            raise ValueError(f"HTTP {meta['status_code']}")
        return raw, meta
    begin = time.monotonic()
    fetched, urls, failures = [], {}, []
    boundary = False
    for page in range(1, 6):
        url = START_URL if page == 1 else urljoin(START_URL, f"page/{page}/")
        raw, meta = acquire(url, f"listing-{page}.html")
        path = root / f"listing-{page}.html"
        records = parse_listing(raw, url)
        fetched.append({"url": url, "file": path.name, "sha256": digest(raw), "records": len(records),
                        "observed_at": meta["observed_at"]})
        for row in records:
            if start <= row["published_on"] <= end:
                urls[row["url"]] = row
        if all(r["published_on"] < start for r in records):
            boundary = True
            break
    if len(urls) > 40:
        raise ValueError("article cap exceeded; collection incomplete")
    docs, bodies = [], {}
    for n, row in enumerate(sorted(urls.values(), key=lambda r: (r["published_on"], r["url"])), 1):
        try:
            filename = f"article-{n:02}.html"
            raw, meta = acquire(row["url"], filename)
            doc = parse_article(raw, row["url"])
            if doc["published_on"] != row["published_on"]:
                raise ValueError("listing/article date mismatch")
            doc.update(raw_file=filename, raw_sha256=digest(raw), observed_at=meta["observed_at"], reused=meta["reused"])
            body = doc["body_sha256"]
            doc["duplicate_of"] = bodies.get(body)
            bodies.setdefault(body, doc["document_id"])
            doc["split"] = "development" if doc["published_on"] >= "2026-09-01" or doc["published_on"] == "2026-08-27" or DEVELOPMENT_SLUG in row["url"] else "evaluation"
            docs.append(doc)
        except Exception as exc:
            failures.append({**row, "error": f"{type(exc).__name__}: {exc}"})
    # 기존 개발 기사의 같은 본문은 다른 URL에서도 평가에 유입시키지 않는다.
    dev_bodies = {d["body_sha256"] for d in docs if d["split"] == "development"}
    for doc in docs:
        if doc["body_sha256"] in dev_bodies:
            doc["split"] = "development"
    result = {"start": start, "end": end, "listing_pages": fetched, "discovered_urls": len(urls),
              "boundary_reached": boundary, "documents": docs, "failures": failures,
              "requests_excluding_robots": session.request_count, "elapsed_seconds": time.monotonic() - begin}
    save(root / "inventory.json", result)
    return result


def verify_inventory(root):
    inventory = json.loads((root / "inventory.json").read_text())
    for entry in inventory["listing_pages"]:
        if digest((root / entry["file"]).read_bytes()) != entry["sha256"]:
            raise ValueError("listing changed")
    for doc in inventory["documents"]:
        raw = (root / doc["raw_file"]).read_bytes()
        if digest(raw) != doc["raw_sha256"]:
            raise ValueError(f"document changed: {doc['document_id']}")
        current = parse_article(raw, doc["url"])
        for key in ["body_sha256", "paragraphs", "published_on", "title"]:
            if current[key] != doc[key]:
                raise ValueError(f"parsed document changed: {doc['document_id']}")
    return inventory


def invoke(document):
    payload = {k: document[k] for k in ["title", "published_on", "paragraphs"]}
    command = ["claude", "-p", "--model", "claude-haiku-4-5", "--output-format", "json",
               "--system-prompt", PROMPT, "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--setting-sources", "", "--settings", '{"disableAllHooks":true}',
               "--no-session-persistence", "--disable-slash-commands", "--no-chrome"]
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="launch-extract-") as cwd:
        response = subprocess.run(command, input=json.dumps(payload, ensure_ascii=False), text=True,
                                  capture_output=True, timeout=180, cwd=cwd)
    envelope = json.loads(response.stdout)
    if response.returncode or envelope.get("is_error"):
        return {"status": "failed", "error": str(envelope.get("result") or response.stderr)[:500],
                "envelope": envelope, "elapsed_seconds": time.monotonic() - start}
    text = envelope.get("result", "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return {"parsed": json.loads(text), "envelope": envelope, "elapsed_seconds": time.monotonic() - start}


def local_session():
    session = requests.Session()
    session.trust_env = False  # 본문을 환경변수의 외부 프록시로 전달하지 않는다.
    return session


def local_config():
    with local_session() as session:
        response = session.get(LOCAL_URL + "/api/tags", timeout=10)
        response.raise_for_status()
        model = next((m for m in response.json()["models"] if m["name"] == LOCAL_MODEL), None)
        if model is None:
            raise ValueError("local model missing; never pull implicitly")
        version = session.get(LOCAL_URL + "/api/version", timeout=10)
        version.raise_for_status()
    return {"url": LOCAL_URL, "model": LOCAL_MODEL, "digest": model["digest"],
            "ollama_version": version.json()["version"], "options": LOCAL_OPTIONS,
            "think": False, "format": "json", "tools": []}


def invoke_local(document):
    payload = {k: document[k] for k in ["title", "published_on", "paragraphs"]}
    request = {"model": LOCAL_MODEL, "stream": False, "think": False, "format": "json",
               "options": LOCAL_OPTIONS, "keep_alive": "5m", "messages": [
                   {"role": "system", "content": PROMPT},
                   {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    start = time.monotonic()
    with local_session() as session:
        response = session.post(LOCAL_URL + "/api/chat", json=request, timeout=(10, 300))
        response.raise_for_status()
        envelope = response.json()
    result = {"envelope": envelope, "elapsed_seconds": time.monotonic() - start,
              "request_sha256": digest(json.dumps(request, ensure_ascii=False, sort_keys=True).encode())}
    if not envelope.get("done") or envelope.get("done_reason") != "stop":
        return {**result, "status": "failed", "error": "incomplete generation"}
    if envelope.get("message", {}).get("tool_calls"):
        return {**result, "status": "failed", "error": "unexpected tool call; never executed"}
    try:
        result["parsed"] = json.loads(envelope["message"]["content"])
    except (ValueError, KeyError) as exc:
        result.update(status="failed", error=f"invalid generated JSON: {exc}")
    return result


def extract(root, run_name, engine, split, live=False):
    inventory = verify_inventory(root)
    run = root / run_name
    run.mkdir(exist_ok=True)
    config = {"engine": engine, "prompt_sha256": digest(PROMPT.encode()),
              "code_sha256": digest(Path(__file__).read_bytes() + Path(__file__).with_name("launch_claims.py").read_bytes()),
              "inventory_sha256": digest((root / "inventory.json").read_bytes()), "split": split}
    if engine == "ollama":
        if not live:
            raise ValueError("live local inference explicitly required")
        config["local"] = local_config()
    save(run / "config.json", config)
    for doc in inventory["documents"]:
        if doc["duplicate_of"] or (split != "all" and doc["split"] != split):
            continue
        output = run / f"{doc['document_id']}.json"
        if output.exists():
            continue
        result = {}
        start = time.monotonic()
        try:
            if engine in {"llm", "ollama"}:
                if not live:
                    raise ValueError("live LLM explicitly required for fresh outputs")
                result = invoke_local(doc) if engine == "ollama" else invoke(doc)
            else:
                t = time.monotonic()
                result = {"parsed": rules(doc), "elapsed_seconds": time.monotonic() - t, "envelope": None}
            result.update(document_id=doc["document_id"], raw_sha256=doc["raw_sha256"])
            if result.get("status") != "failed":
                result["status"] = "ok"
                normalized, result["adjustments"] = prepare(result["parsed"], doc)
                result["validated"] = validate(normalized, doc)
        except Exception as exc:
            result = {**result, "document_id": doc["document_id"], "raw_sha256": doc["raw_sha256"],
                      "elapsed_seconds": time.monotonic() - start,
                      "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        save(output, result)
        print(json.dumps({"document": doc["document_id"], "status": result["status"]}), flush=True)
        if result["status"] == "failed" and any(x in result.get("error", "").lower() for x in ["not logged in", "disabled claude subscription", "authentication"]):
            break  # 인증 불가면 다른 문서에 같은 실패 요청을 반복하지 않는다.


def replay(root, run_name, catalog_path):
    inventory = verify_inventory(root)
    config = json.loads((root / run_name / "config.json").read_text())
    if config["inventory_sha256"] != digest((root / "inventory.json").read_bytes()):
        raise ValueError("inventory changed since extraction")
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    if isinstance(catalog, dict):
        catalog = catalog["items"]
    rows = []
    for doc in inventory["documents"]:
        path = root / run_name / f"{doc['document_id']}.json"
        if doc["duplicate_of"] or not path.exists():
            continue
        saved = json.loads(path.read_text())
        if saved["raw_sha256"] != doc["raw_sha256"]:
            raise ValueError("extraction refers to different document")
        normalized, adjustments = prepare(saved.get("parsed"), doc)
        checked = validate(normalized, doc) if saved["status"] == "ok" else {"claims": [], "rejected": []}
        rows.append({"document_id": doc["document_id"], "split": doc["split"], "status": saved["status"],
            "document_kind": checked.get("document_kind"),
            "adjustments": adjustments,
            "url": doc["url"], "claims": [{**c, "links": link_family(c, catalog)} for c in checked["claims"]],
            "rejected": checked["rejected"], "discovery_fallback": "unchanged",
            "extraction_sha256": digest(path.read_bytes())})
    return {"catalog_sha256": digest(catalog_bytes), "config": config, "documents": rows,
            "replay_code_sha256": digest(Path(__file__).read_bytes() + Path(__file__).with_name("launch_claims.py").read_bytes()),
            "public_status_changed": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["collect", "extract", "replay"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--approved-once", action="store_true")
    p.add_argument("--reuse-root", type=Path)
    p.add_argument("--start", default="2026-08-01")
    p.add_argument("--end", default="2026-09-08")
    p.add_argument("--run", default="rules-v1")
    p.add_argument("--engine", choices=["rules", "llm", "ollama"], default="rules")
    p.add_argument("--split", choices=["development", "evaluation", "all"], default="development")
    p.add_argument("--live", action="store_true")
    p.add_argument("--catalog", type=Path)
    a = p.parse_args()
    if a.root.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        p.error("raw research inputs must be outside the public code repository")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", a.run):
        p.error("invalid run name")
    if a.action == "collect":
        if not a.approved_once:
            p.error("one-time source review approval is required")
        r = collect(a.root, a.start, a.end, a.reuse_root)
        print(json.dumps({k: v for k, v in r.items() if k != "documents"}, ensure_ascii=False, indent=2))
    elif a.action == "extract":
        extract(a.root, a.run, a.engine, a.split, a.live)
    else:
        if not a.catalog:
            p.error("--catalog required")
        print(json.dumps(replay(a.root, a.run, a.catalog), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
