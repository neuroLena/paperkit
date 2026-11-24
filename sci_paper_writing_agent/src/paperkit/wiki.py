"""Source wiki: one page per citation key. The writer and the reviewer read these pages, not the PDFs."""
from __future__ import annotations

from pathlib import Path

from . import agents
from .schemas import Issue

REQUIRED = ["## Key findings", "## Quotes"]
SERVICE = {"index", "SCHEMA"}


def index(wiki_dir: Path) -> str:
    path = wiki_dir / "index.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def page(wiki_dir: Path, key: str) -> str:
    path = wiki_dir / f"{key}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def pages_for(wiki_dir: Path, keys) -> dict[str, str]:
    """Pages for a set of keys. A missing page is passed on explicitly so the reviewer sees it."""
    return {key: page(wiki_dir, key) or "(no wiki page for this source)" for key in sorted(set(keys))}


def ingest(wiki_dir: Path, key: str, source_text: str) -> Path:
    """The agent writes a page from the source text; code files it and updates the index."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    path = wiki_dir / f"{key}.md"
    path.write_text(agents.wiki_page(key, source_text).strip() + "\n", encoding="utf-8")
    idx = wiki_dir / "index.md"
    current = idx.read_text(encoding="utf-8") if idx.exists() else "# Wiki index\n\n"
    if f"[[{key}]]" not in current:
        idx.write_text(current.rstrip("\n") + f"\n- [[{key}]]:\n", encoding="utf-8")
    return path


def lint(wiki_dir: Path, bib_keys: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    listed = index(wiki_dir)
    for path in sorted(wiki_dir.glob("*.md")):
        key = path.stem
        if key in SERVICE:
            continue
        text = path.read_text(encoding="utf-8")
        for heading in REQUIRED:
            if heading not in text:
                issues.append(Issue(gate="wiki", message=f"{path.name}: missing '{heading}'"))
        if key not in bib_keys:
            issues.append(Issue(gate="wiki", severity="warning", message=f"{path.name}: no such key in library.bib"))
        if f"[[{key}]]" not in listed:
            issues.append(Issue(gate="wiki", severity="warning", message=f"{path.name}: not listed in index.md"))
    return issues
