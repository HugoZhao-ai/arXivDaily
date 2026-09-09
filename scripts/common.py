"""Shared, dependency-free data and matching helpers."""
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", value.replace("–", "-").replace("‑", "-")).strip()


def arxiv_id(value):
    value = re.sub(r"^https?://[^/]+/(abs|pdf|html)/", "", value)
    value = re.sub(r"(?:v\d+)?(?:\.pdf)?$", "", value)
    if not re.fullmatch(r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}", value):
        raise ValueError("Invalid arXiv ID")
    return value


def slug(value):
    return arxiv_id(value).replace("/", "--")


def term_matches(term, text):
    term = normalize(term)
    if term in {"quantiz", "quantis", "compress"}:
        return re.search(r"\b" + term, text) is not None
    if term in {"language model", "reasoning model", "transformer"}:
        return re.search(r"(?<!\w)" + re.escape(term) + r"s?(?!\w)", text) is not None
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) is not None


def classify(paper, config, verified=None):
    text = normalize(paper["title"] + " " + paper["abstract"])
    topics, reasons = [], []
    for topic in config["topics"]:
        hits = [[term for term in group if term_matches(term, text)] for group in topic["groups"]]
        if all(hits):
            topics.append(topic["id"])
            reasons.append({"type": "topic", "label": topic["name"], "evidence": ", ".join(group[0] for group in hits)})
    authors = {normalize(a) for a in paper["authors"]}
    researchers = []
    for researcher in config["researchers"]:
        if authors.intersection(normalize(a) for a in researcher["aliases"]):
            known = set(researcher.get("verified_arxiv_ids", [])) | set((verified or {}).get(researcher["id"], []))
            status = "verified" if paper["id"] in known else "name-match"
            researchers.append({"id": researcher["id"], "status": status})
            reasons.append({"type": "researcher", "label": researcher["name_zh"], "evidence": "作者名匹配；官网论文链接已核验" if status == "verified" else "作者名匹配，机构身份待核验"})
    paper.update(topics=topics, researchers=researchers, reasons=reasons)
    paper["related_only"] = bool(topics) and all(next(t for t in config["topics"] if t["id"] == key)["kind"] == "related" for key in topics)
    return bool(topics or researchers)


class HttpClient:
    """Single-connection API usage, bounded responses and exponential retries."""
    def __init__(self, delay=3.2, retries=3):
        self.delay = max(3.0, delay)
        self.retries = retries
        self.last_request = 0

    def get(self, url, limit=8_000_000):
        for attempt in range(self.retries):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = Request(url, headers={"User-Agent": "QuantResearchDaily/1.0 (personal academic paper tracker)"})
                with urlopen(request, timeout=45) as response:
                    body = response.read(limit + 1)
                    if len(body) > limit:
                        raise ValueError("Response exceeds size limit")
                    return body
            except (HTTPError, URLError, TimeoutError) as error:
                if isinstance(error, HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                    raise
                if attempt + 1 == self.retries:
                    raise
                print(f"Request retry {attempt + 1}/{self.retries - 1}: {type(error).__name__}", flush=True)
                time.sleep(min(45, 5 * 2 ** attempt))
