"""Semantic Scholar search. Standard library only, so there is no extra dependency.

Every record here came from the API: the model never names a paper. Requests are paced, a refused
request is tried again after a wait, and each answered search is saved in .cache/scholar/.

A key is optional but matters: without one, searches share a pool with every other anonymous user and
are often turned away. A free key (semanticscholar.org/product/api) allows one request per second.
Put it in .env as SEMANTIC_SCHOLAR_API_KEY.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://api.semanticscholar.org/graph/v1"      # SEMANTIC_SCHOLAR_BASE_URL overrides it
FIELDS = "title,abstract,year,authors,venue,externalIds,citationCount,url"
PAUSE = 1.1                     # seconds between requests: a key allows one request per second
BACKOFF = (3, 8, 20, 40)        # waits after HTTP 429 or 5xx: the API sends no Retry-After
TIMEOUT = 30
KEY_HINT = ("Without a key, Semantic Scholar often turns searches away. Request a free key at "
            "semanticscholar.org/product/api and put SEMANTIC_SCHOLAR_API_KEY=... in .env.")
STOPWORDS = {"the", "and", "for", "with", "from", "into", "that", "this", "does", "are", "was", "were", "between",
             "among", "study", "analysis", "effect", "effects", "using", "based", "toward", "towards", "about"}
_last = 0.0                     # when the last request was sent


class SearchError(RuntimeError):
    """The search service could not be used. The message says what to do."""


def has_key() -> bool:
    return bool((os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or "").strip())


def _get(url: str) -> dict:
    """One paced GET. HTTP 429 and 5xx are both the service saying "not now": wait and try again."""
    global _last
    key = (os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or "").strip()
    headers = {"Accept": "application/json", "User-Agent": "paperkit (literature search for a manuscript)"}
    if key:
        headers["x-api-key"] = key
    for wait in (*BACKOFF, None):
        gap = PAUSE - (time.monotonic() - _last)
        if gap > 0:
            time.sleep(gap)
        _last = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:200]
            busy = exc.code == 429 or exc.code >= 500
            if busy and wait is not None:
                time.sleep(wait)
                continue
            if exc.code in (401, 403):
                raise SearchError("Semantic Scholar rejected the key: check SEMANTIC_SCHOLAR_API_KEY in .env") from None
            if busy:
                raise SearchError(f"Semantic Scholar is not answering (HTTP {exc.code}, {len(BACKOFF) + 1} tries). "
                                  + ("Try again later." if key else KEY_HINT)) from None
            raise SearchError(f"Semantic Scholar: HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            if wait is not None:
                time.sleep(min(wait, 5))
                continue
            reason = getattr(exc, "reason", exc)
            raise SearchError(f"cannot reach Semantic Scholar: {' '.join(str(reason).split())[:160]}") from None
    raise SearchError("no answer from Semantic Scholar")       # not reached


def paper(raw: dict) -> dict | None:
    """One API record in paperkit's shape, or None when it has no id or no title."""
    if not isinstance(raw, dict):
        return None
    title = " ".join(str(raw.get("title") or "").split())
    if not raw.get("paperId") or not title:
        return None
    ids = raw.get("externalIds") or {}
    doi = next((str(value).strip().lower() for name, value in ids.items() if str(name).lower() == "doi" and value), "")
    year = raw.get("year")
    return {
        "paper_id": str(raw["paperId"]), "title": title,
        "authors": [str(a["name"]).strip() for a in raw.get("authors") or [] if isinstance(a, dict) and a.get("name")],
        "year": year if isinstance(year, int) else None,
        "venue": " ".join(str(raw.get("venue") or "").split()),
        "doi": doi, "url": f"https://doi.org/{doi}" if doi else str(raw.get("url") or ""),
        "abstract": " ".join(str(raw.get("abstract") or "").split()),      # often missing, even for well-known papers
        "citations": int(raw.get("citationCount") or 0),
    }


def clean_query(query: str, words: int = 12) -> str:
    """A query the relevance search accepts: no quotes or operators, and no hyphens (they match nothing there)."""
    text = re.sub(r"[\"'“”‘’()\[\]{}:;,+|*~<>]", " ", unicodedata.normalize("NFKC", query)).replace("-", " ")
    return " ".join(text.split()[:words])


def search(query: str, limit: int = 5, cache_dir: Path | None = None, fresh: bool = False) -> list[dict]:
    """The papers the relevance search returns for a query, best match first."""
    query = clean_query(query)
    if not query:
        return []
    base = (os.environ.get("SEMANTIC_SCHOLAR_BASE_URL") or BASE_URL).rstrip("/")
    name = hashlib.sha256(json.dumps([query, limit, FIELDS]).encode("utf-8")).hexdigest()[:24]
    cache = Path(cache_dir) / f"{name}.json" if cache_dir else None
    if cache and cache.is_file() and not fresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    data = _get(f"{base}/paper/search?" + urllib.parse.urlencode({"query": query, "limit": limit, "fields": FIELDS}))
    rows = data.get("data") if isinstance(data, dict) else None
    papers = [found for found in map(paper, rows or []) if found]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(papers, ensure_ascii=False), encoding="utf-8")
    return papers


# ------------------------------------------------------------------ references

def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def cite_key(found: dict, taken) -> str:
    """A citation key such as smith2020sleep that is not in `taken`."""
    family = re.sub(r"[^a-z]", "", _ascii((found.get("authors") or ["anon"])[0].split()[-1]).lower()) or "anon"
    title = re.sub(r"[^\w\s]", " ", found.get("title", ""))           # a dash or a brace separates words
    word = next((w for w in re.findall(r"[a-z]+", _ascii(title).lower()) if len(w) > 3 and w not in STOPWORDS), "")
    base = f"{family}{found.get('year') or 'nd'}{word}"
    taken = set(taken)
    key, n = base, 0
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n)}" if n <= 26 else f"{base}{n}"
    return key


def bibtex(found: dict, key: str) -> str:
    """A BibTeX entry built from the API record."""
    def value(text: object) -> str:
        return re.sub(r"[{}]", "", " ".join(str(text).split()))

    fields = [("title", found.get("title", "")), ("author", " and ".join(found.get("authors") or [])),
              ("year", found.get("year") or ""), ("journal", found.get("venue", "")),
              ("doi", found.get("doi", "")), ("url", found.get("url", ""))]
    rows = [f"  {name} = {{{value(text)}}}," for name, text in fields if str(text).strip()]
    return "@article{" + key + ",\n" + "\n".join(rows) + "\n}\n"


def norm_doi(text: str) -> str:
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", str(text or "").strip().lower())


def title_key(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", str(text or "")).casefold() if ch.isalnum())


def library_key(bib: dict, found: dict) -> str:
    """The key under which a paper is already in refs/library.bib: matched by DOI, else by title. '' if it is not."""
    doi, title = norm_doi(found.get("doi", "")), title_key(found.get("title", ""))
    for key, fields in bib.items():
        if doi and norm_doi(fields.get("doi", "")) == doi:
            return key
    for key, fields in bib.items():
        if title and title_key(fields.get("title", "")) == title:
            return key
    return ""
