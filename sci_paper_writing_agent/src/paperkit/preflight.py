"""Input checklist: what the pipeline needs before a model is called, and whether it is there yet.

Nothing here asks questions. The start screen and the CLI both read this list,
and `plan` and `run` refuse to start while a required item is missing.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import agents, zotero
from .schemas import PaperSpec

MIN_WORDS = 30   # below this, a Methods or Results file counts as not filled in

# Lines the scaffold writes into the input files. They do not count as content.
TEMPLATE_LINES = {
    "paste the full methods section here, as it appears in the manuscript.",
    "paste the full results section here: text, tables and figure captions.",
    "three to five points the paper must get across. one per line.",
    "known limitations and assumptions: design, sample, missing data, unmeasured factors,",
    "and which model assumptions were tested and which were not.",
    "your notes for the introduction: what is known, what is not known, and what this study set out to do.",
}
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s+|$)")
DEFAULT_TITLE = "Working title"


@dataclass
class Check:
    key: str            # stable name: "methods", "facts", ...
    path: str           # where the input lives, relative to the project
    label: str
    level: str          # "required" | "recommended" | "optional"
    ok: bool
    detail: str         # what was found
    hint: str = ""      # what to put there


def content_lines(path: Path) -> list[str]:
    """Lines that carry content: no headings, no scaffold placeholders, no empty bullets."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = BULLET.sub("", line).strip()
        if text and not text.startswith("#") and text.lower() not in TEMPLATE_LINES:
            out.append(text)
    return out


def read_facts_csv(path: Path) -> list[dict]:
    """Rows of a facts CSV. Raises ValueError if the id, text and source columns are not all there."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"id", "text", "source"} <= set(reader.fieldnames or []):
            raise ValueError("needs the columns id, text, source")
        return [{k: (row.get(k) or "").strip() for k in ("id", "text", "source")} for row in reader]


def _text_check(root: Path, key: str, rel: str, label: str, hint: str) -> Check:
    path = root / rel
    if not path.is_file():
        return Check(key, rel, label, "required", False, "file is missing", hint)
    words = sum(len(line.split()) for line in content_lines(path))
    if words == 0:
        return Check(key, rel, label, "required", False, "still the placeholder text", hint)
    if words < MIN_WORDS:
        return Check(key, rel, label, "required", False, f"only {words} words", hint)
    return Check(key, rel, label, "required", True, f"{words} words", hint)


def _list_check(root: Path, key: str, rel: str, label: str, noun: str, hint: str) -> Check:
    path = root / rel
    if not path.is_file():
        return Check(key, rel, label, "required", False, "file is missing", hint)
    count = len(content_lines(path))
    return Check(key, rel, label, "required", count > 0, f"{count} {noun}(s)" if count else "nothing listed yet", hint)


def _has_section(root: Path, sec_id: str) -> bool:
    try:
        raw = yaml.safe_load((root / "paper.yaml").read_text(encoding="utf-8")) or {}
        return any(isinstance(sec, dict) and sec.get("id") == sec_id for sec in raw.get("sections", []))
    except Exception:
        return False


def _spec_checks(root: Path) -> list[Check]:
    hint = "title, study design, and each section with its required headings and word limit"
    path = root / "paper.yaml"
    if not path.is_file():
        return [Check("spec", "paper.yaml", "Paper specification", "required", False, "file is missing", hint)]
    try:
        spec = PaperSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception as exc:   # YAML syntax or schema error: report it, do not crash the checklist
        reason = " ".join(str(exc).split())[:70]
        return [Check("spec", "paper.yaml", "Paper specification", "required", False, f"not valid: {reason}", hint)]
    names = ", ".join(sec.id for sec in spec.sections)
    checks = [Check("spec", "paper.yaml", "Paper specification", "required", bool(spec.sections),
                    f"{spec.design}; sections: {names}" if spec.sections else "no sections defined", hint)]
    titled = bool(spec.title.strip()) and spec.title.strip() != DEFAULT_TITLE
    checks.append(Check("title", "paper.yaml", "Paper title", "recommended", titled,
                        spec.title if titled else "still the default title", "the real title of the paper"))
    return checks


def _facts_check(root: Path) -> Check:
    hint = "one row per number the text may use: id (F1, F2...), text as it should print, source"
    rel, path = "inputs/facts.csv", root / "inputs" / "facts.csv"
    if not path.is_file():
        return Check("facts", rel, "Facts registry", "required", False, "file is missing", hint)
    try:
        rows = read_facts_csv(path)
    except (ValueError, csv.Error, UnicodeDecodeError) as exc:
        return Check("facts", rel, "Facts registry", "required", False, f"not readable: {exc}", hint)
    examples = [r for r in rows if "EXAMPLE" in r["text"]]
    real = [r for r in rows if r not in examples]
    if not real:
        return Check("facts", rel, "Facts registry", "required", False,
                     "only the example rows" if examples else "no facts yet", hint)
    if examples:
        return Check("facts", rel, "Facts registry", "required", False,
                     f"{len(real)} fact(s), but {len(examples)} example row(s) are still there", hint)
    expected = {r["id"]: {"text": r["text"], "source": r["source"]} for r in real}
    built = root / "facts" / "facts.json"
    try:
        current = json.loads(built.read_text(encoding="utf-8")) if built.is_file() else {}
    except ValueError:
        current = None
    if current != expected:
        return Check("facts", rel, "Facts registry", "required", False,
                     f"{len(real)} fact(s), but facts/facts.json is out of date: run `paperkit facts`", hint)
    return Check("facts", rel, "Facts registry", "required", True, f"{len(real)} fact(s)", hint)


def _key_check(root: Path) -> Check:
    """A key for every provider the planner, writer and reviewer are routed to."""
    try:
        agents.configure(root)
        providers = sorted({agents.route(kind)[0] for kind in agents.PIPELINE_AGENTS})
    except (ValueError, OSError) as exc:
        reason = " ".join(str(exc).split())[:70]
        return Check("api_key", "config/models.yaml", "API key", "recommended", False,
                     f"model configuration is not valid: {reason}", "a valid config/models.yaml")
    lacking = [p for p in providers if not agents.has_key(p)]
    names = " and ".join(agents.PROVIDERS[p][0] for p in providers)
    detail = (f"no key for {', '.join(lacking)}: needed for plan and run, not for a dry run" if lacking
              else f"set ({', '.join(providers)})")
    return Check("api_key", ".env", "API key", "recommended", not lacking, detail,
                 f"{names} in the environment or in .env")


def _count(folder: Path, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns for _ in folder.glob(pattern)) if folder.is_dir() else 0


def check_inputs(root: str | Path) -> list[Check]:
    root = Path(root)
    checks = _spec_checks(root)
    checks += [
        _text_check(root, "methods", "inputs/methods.md", "Methods section",
                    "the full Methods section, as in the manuscript"),
        _text_check(root, "results", "inputs/results.md", "Results section",
                    "the full Results section: text, tables, figure captions"),
        _list_check(root, "key_messages", "inputs/key_messages.md", "Key messages", "message",
                    "three to five points the paper must get across, one per line"),
        _list_check(root, "limitations", "inputs/limitations.md", "Limitations", "item",
                    "known limitations and untested assumptions, one per line"),
        _facts_check(root),
    ]
    if _has_section(root, "introduction"):
        checks.insert(len(checks) - 1, _text_check(
            root, "introduction", "inputs/introduction.md", "Introduction notes",
            "background, knowledge gap and aim, in your own words (needs the introduction section in paper.yaml)"))
    entries = len(zotero.load_bib(root / "refs" / "library.bib"))
    checks.append(Check("bib", "refs/library.bib", "Reference library", "recommended", entries > 0,
                        f"{entries} reference(s)" if entries else "no references: nothing can be cited",
                        "Better BibTeX auto-export from Zotero, or a copy of a .bib file"))
    checks.append(_key_check(root))
    pages = [p for p in (root / "wiki").glob("*.md") if p.stem not in {"index", "SCHEMA"}] if (root / "wiki").is_dir() else []
    checks.append(Check("wiki", "wiki/", "Source pages", "optional", bool(pages),
                        f"{len(pages)} page(s)" if pages else "none: the reviewer cannot check citations",
                        "one page per cited source, named <citation key>.md"))
    if (root / ".papers").is_dir():
        pdfs = _count(root / ".papers", ("*.pdf", "*.PDF"))
        checks.append(Check("papers", ".papers/", "Source PDFs", "optional", pdfs > 0,
                            f"{pdfs} PDF(s)" if pdfs else "none", "the papers you cite, for building source pages"))
    if (root / "inputs" / "tables").is_dir():
        tables = _count(root / "inputs" / "tables", ("*.csv", "*.tsv"))
        checks.append(Check("tables", "inputs/tables/", "Result tables", "optional", tables > 0,
                            f"{tables} table file(s)" if tables else "none",
                            "CSV or TSV result tables, described in manifest.yaml"))
    return checks


def missing(checks: list[Check], level: str = "required") -> list[Check]:
    return [c for c in checks if c.level == level and not c.ok]


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def tag(check: Check) -> tuple[str, str]:
    """Status word and its ANSI colour code."""
    if check.ok:
        return "[ok]", "32"
    return {"required": ("[missing]", "31"), "recommended": ("[to do]", "33")}.get(check.level, ("[--]", "2"))


def line(check: Check, color: bool = False) -> str:
    word, code = tag(check)
    status = f"\033[{code}m{word:<10}\033[0m" if color else f"{word:<10}"
    return f"  {status}{check.path:<26}{check.label:<21}{check.detail}"


def render(checks: list[Check], color: bool = False) -> str:
    required = [c for c in checks if c.level == "required"]
    ready = sum(c.ok for c in required)
    rows = ["Inputs"] + [line(c, color) for c in checks]
    rows.append(f"Required inputs ready: {ready} of {len(required)}")
    return "\n".join(rows)
