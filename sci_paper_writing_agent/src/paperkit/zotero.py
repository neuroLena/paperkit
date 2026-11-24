"""Read-only reference library.

The agent never creates references; it picks keys. Keys have one source: refs/library.bib,
which Zotero keeps up to date through Better BibTeX auto-export.
"""
from __future__ import annotations

import re
from pathlib import Path

ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.S)
FIELD = re.compile(r"^\s*(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.M | re.S)
SKIP = {"comment", "string", "preamble"}


def load_bib(path: Path) -> dict[str, dict[str, str]]:
    """Simple .bib parser: key -> fields. Enough for searching and for checking keys."""
    if not path.exists():
        return {}
    bib: dict[str, dict[str, str]] = {}
    for kind, key, body in ENTRY.findall(path.read_text(encoding="utf-8")):
        if kind.lower() in SKIP:
            continue
        bib[key] = {name.lower(): " ".join(re.sub(r"[{}]", "", value).split()) for name, value in FIELD.findall(body)}
    return bib


def _year(fields: dict[str, str]) -> str:
    return fields.get("year") or fields.get("date", "")[:4]


def library_listing(bib: dict[str, dict[str, str]]) -> str:
    """Listing for the planner: one line per source."""
    return "\n".join(f"- {key}: {f.get('title', '')} ({_year(f)})" for key, f in sorted(bib.items()))


def search_bib(bib: dict[str, dict[str, str]], query: str, limit: int = 10) -> list[dict[str, str]]:
    """Word search across key, title, authors, abstract and keywords."""
    words = query.lower().split()
    hits = []
    for key, f in bib.items():
        hay = " ".join([key, f.get("title", ""), f.get("author", ""), f.get("abstract", ""), f.get("keywords", "")]).lower()
        score = sum(word in hay for word in words)
        if score:
            hits.append((score, key, f))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return [{"key": key, "title": f.get("title", ""), "year": _year(f), "abstract": f.get("abstract", "")[:500]}
            for _, key, f in hits[:limit]]


def search_zotero(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Stub: search a running Zotero through its local API.

    Needs `pip install pyzotero`, Zotero open, and the local API enabled in Zotero's settings.
    Untested. Check that the key it returns matches the key in library.bib.
    """
    from pyzotero import zotero

    zot = zotero.Zotero(library_id="0", library_type="user", local=True)
    out = []
    for item in zot.items(q=query, limit=limit):
        data = item.get("data", {})
        pinned = re.search(r"Citation Key:\s*(\S+)", data.get("extra", ""))
        key = data.get("citationKey") or (pinned.group(1) if pinned else "")
        out.append({"key": key, "title": data.get("title", ""), "year": data.get("date", "")[:4],
                    "abstract": data.get("abstractNote", "")[:500]})
    return out
