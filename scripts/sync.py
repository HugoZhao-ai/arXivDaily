"""Fetch independent topic / author streams with checkpointed overlap windows."""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from common import ROOT, HttpClient, arxiv_id, classify, now, read_json, write_json

NS = {"a": "http://www.w3.org/2005/Atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}


def parse_feed(raw):
    root = ET.fromstring(raw)
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("Unexpected arXiv response")
    papers = []
    for entry in root.findall("a:entry", NS):
        def value(key):
            return " ".join((entry.findtext("a:" + key, "", NS)).split())
        if "/errors" in value("id"):
            raise ValueError("arXiv returned a query error")
        identifier = arxiv_id(value("id"))
        updated = value("updated")
        published = value("published")
        datetime.fromisoformat(updated.replace("Z", "+00:00"))
        datetime.fromisoformat(published.replace("Z", "+00:00"))
        papers.append({"id": identifier, "title": value("title"), "abstract": value("summary"),
                       "authors": [" ".join(a.findtext("a:name", "", NS).split()) for a in entry.findall("a:author", NS)],
                       "published": published, "updated": updated,
                       "version": int(re.search(r"v(\d+)$", value("id")).group(1)) if re.search(r"v(\d+)$", value("id")) else 1,
                       "categories": [c.attrib["term"] for c in entry.findall("a:category", NS)],
                       "url": "https://arxiv.org/abs/" + identifier,
                       "pdf_url": "https://arxiv.org/pdf/" + identifier})
    total = root.findtext("o:totalResults", None, NS)
    if total is None:
        raise ValueError("Missing arXiv pagination metadata")
    return papers, int(total)


def fetch_stream(client, query, since, until, settings):
    query = f"({query}) AND lastUpdatedDate:[{since:%Y%m%d%H%M} TO {until:%Y%m%d%H%M}]"
    gathered = []
    page_size = settings["page_size"]
    for page in range(settings["max_pages"]):
        url = "https://export.arxiv.org/api/query?" + urlencode({"search_query": query, "start": page * page_size,
                "max_results": page_size, "sortBy": "lastUpdatedDate", "sortOrder": "ascending"})
        records, total = parse_feed(client.get(url))
        gathered.extend(records)
        if len(gathered) >= total:
            return gathered
        if not records:
            raise RuntimeError("Empty page before end of arXiv results; checkpoint not advanced")
    raise RuntimeError(f"Stream exceeds {settings['max_pages']} pages; increase sync.max_pages. Checkpoint not advanced")


def merge(existing, incoming):
    previous = existing.get(incoming["id"], {})
    if previous and incoming["updated"] < previous["updated"]:
        return
    if previous.get("updated") != incoming["updated"]:
        previous = {k: v for k, v in previous.items() if k not in {"summary", "image", "image_checked", "image_retry_after"}}
    existing[incoming["id"]] = {**previous, **incoming, "first_seen": previous.get("first_seen", now())}


def run(seed_only=False, backfill_days=None):
    config = read_json(ROOT / "config.json")
    settings = config["sync"]
    state = read_json(ROOT / "data/state.json", {"streams": {}})
    database = read_json(ROOT / "data/papers.json", {"papers": []})
    existing = {p["id"]: p for p in database["papers"]}
    client = HttpClient(settings["delay_seconds"])
    verified = read_json(ROOT / "data/researchers.json", {})
    warnings, failures = [], []
    for researcher in config["researchers"]:
        try:
            html = client.get(researcher["homepage"]).decode("utf-8")
            # Only direct arXiv links are evidence of identity, never a coauthor guess.
            ids = re.findall(r"https?://(?:www\.)?arxiv.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", html)
            verified[researcher["id"]] = sorted(set(verified.get(researcher["id"], [])) | set(ids))
        except Exception as error:
            warnings.append(f"Researcher homepage unavailable: {researcher['id']} ({type(error).__name__})")
    write_json(ROOT / "data/researchers.json", verified)
    seed_missing = [pid for pid in config.get("seed_ids", []) if pid not in existing]
    if seed_missing:
        try:
            papers, _ = parse_feed(client.get("https://export.arxiv.org/api/query?" + urlencode({"id_list": ",".join(seed_missing), "max_results": len(seed_missing)})))
            for paper in papers:
                paper["seed"] = True
                merge(existing, paper)
        except Exception as error:
            failures.append(f"seed: {type(error).__name__}: {error}")
    started = datetime.now(timezone.utc)
    if not seed_only:
        streams = [("topic:" + t["id"], t["query"]) for t in config["topics"]]
        streams += [("researcher:" + r["id"], r["query"]) for r in config["researchers"]]
        for key, query in streams:
            # A changed query gets a fresh initial window; one failed stream never moves another's cursor.
            checkpoint = state.setdefault("streams", {}).get(key, {})
            last = checkpoint.get("last_success") if checkpoint.get("query") == query else None
            since = datetime.fromisoformat(last) - timedelta(days=settings["overlap_days"]) if last else started - timedelta(days=settings["initial_days"])
            if backfill_days is not None:
                since = started - timedelta(days=backfill_days)
            print(f"Fetching {key} since {since.date()}", flush=True)
            try:
                records = fetch_stream(client, query, since, started, settings)
                for record in records:
                    merge(existing, record)
                state["streams"][key] = {"query": query, "last_success": started.isoformat(timespec="seconds"), "fetched": len(records)}
                print(f"  {len(records)} records", flush=True)
            except Exception as error:
                failures.append(f"{key}: {type(error).__name__}: {error}")
    papers = []
    for paper in existing.values():
        if classify(paper, config, verified):
            papers.append(paper)
    papers.sort(key=lambda p: (p["published"], p["id"]), reverse=True)
    write_json(ROOT / "data/papers.json", {"schema_version": 1, "papers": papers})
    if not failures and not seed_only:
        state["last_success"] = now()
    state["last_run"] = {"at": now(), "status": "partial" if failures else "seed" if seed_only else "ok", "errors": failures, "warnings": warnings, "paper_count": len(papers)}
    write_json(ROOT / "data/state.json", state)
    for message in failures + warnings:
        print(message, file=sys.stderr)
    print(f"Stored {len(papers)} matching papers", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-only", action="store_true", help="Fetch configured foundational papers only")
    parser.add_argument("--backfill-days", type=int, help="Re-scan a longer historical window without deleting the archive")
    args = parser.parse_args()
    if args.backfill_days is not None and args.backfill_days < 1:
        parser.error("--backfill-days must be positive")
    sys.exit(run(args.seed_only, args.backfill_days))
