"""Writing guides -> writing rules.

PDF, .md or .txt files in .writing_guides/ (general/, journal/, reporting/) become rules for the writer and reviewer.
The model proposes; code verifies; a person approves:
- each guide is read page by page and sent to the `rules` agent a few pages at a time;
- a proposed rule is kept only if its quote is really in those pages (the same letters and digits in the same
  order), and its page is worked out here, never by the model;
- kept rules go to rules/candidates.json with approved set to false. Only approved rules, which are copied to
  rules/active_rules.json, ever reach the writer, the reviewer and the gate;
- every answered part is saved in .cache/guides/, so a run that failed half way continues where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .. import agents
from ..ingestion_schemas import WritingRule

GUIDES = ".writing_guides"
SUFFIXES = (".pdf", ".md", ".txt")
CATEGORIES = ("structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting",
              "scientific_reasoning")
PRIORITIES = ("required", "recommended", "optional")
MIN_QUOTE_WORDS = 3
NONE_YET = f"No rules yet. Put the guides in {GUIDES}/ and run: paperkit rules extract"

PROMPT = """You read part of a writing guide (a journal's instructions for authors, a reporting guideline or a style guide) and list the rules that say how the TEXT of a scientific paper must be written. You write no prose.

For each rule return:
- instruction: one short imperative sentence a writer can follow, in your own words. One rule per instruction.
- quote: the passage of the guide that states the rule, copied character for character. One continuous passage of 5 to 60 words: no "...", and never two places joined together.
- category: structure, argumentation, language, statistics, reporting, citations, formatting or scientific_reasoning.
- sections: the sections of a paper it applies to, in lower case, such as ["abstract"], ["methods"] or ["discussion"]; ["all"] if it applies everywhere. Prefer the names in <paper_sections>.
- priority: "required" if the guide says must, required, never or always; "recommended" if it says should; otherwise "optional".
- avoid_terms: only when the rule bans specific words or phrases, those words exactly as they appear in your quote; otherwise an empty list.

Leave out everything that is not about writing the text: submission and upload steps, fees, file formats and image resolution, cover letters, authorship and ethics forms, copyright, the review process, contact details.
Never invent a rule. If these pages hold no writing rule, return an empty list. Return at most 15 rules."""


class ProposedRule(BaseModel):
    instruction: str = Field(description="One short imperative sentence a writer can follow")
    quote: str = Field(description="The passage of the guide that states it, copied character for character")
    category: str = Field(default="language", description="One of: " + ", ".join(CATEGORIES))
    sections: list[str] = Field(default_factory=lambda: ["all"], description='Paper sections in lower case, or ["all"]')
    priority: str = Field(default="recommended", description="required, recommended or optional")
    avoid_terms: list[str] = Field(default_factory=list, description="Banned words or phrases, exactly as in the quote")


class RuleList(BaseModel):
    rules: list[ProposedRule] = Field(default_factory=list)


# ------------------------------------------------------------------ reading

def _key(text: str) -> str:
    """Letters and digits only, in lower case. Quotes are compared on this, so the line breaks, hyphens
    and quote marks of a PDF do not matter, but every word must be there in the same order."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _short(text: object, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def clean(text: str) -> str:
    """Page text as running text: a word split over a line break is joined, and lines become sentences."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
    blocks = (" ".join(block.split()) for block in re.split(r"\n[ \t]*\n", text))
    return "\n\n".join(block for block in blocks if block)


def guide_files(root: str | Path) -> list[Path]:
    folder = Path(root) / GUIDES
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)


def read_guide(path: Path) -> list[tuple[int, str]]:
    """(page number, text) for every page that has text. A .md or .txt file is one page unless it holds form feeds."""
    if path.suffix.lower() == ".pdf":
        try:
            from .pdf_parser import parse_pdf

            raw = [(page["page"], page["text"]) for page in parse_pdf(path)]
        except ImportError:
            raise RuntimeError("reading a PDF needs PyMuPDF: pip install pymupdf") from None
    else:
        raw = list(enumerate(path.read_text(encoding="utf-8-sig").split("\f"), 1))
    pages = [(number, clean(text)) for number, text in raw]
    return [(number, text) for number, text in pages if text]


def parts(pages: list[tuple[int, str]], limit: int) -> list[list[tuple[int, str]]]:
    """Consecutive pages grouped into parts of about `limit` words, so no request is long. A page is never cut."""
    out, current, size = [], [], 0
    for page in pages:
        words = len(page[1].split())
        if current and size + words > limit:
            out.append(current)
            current, size = [], 0
        current.append(page)
        size += words
    return out + ([current] if current else [])


def section_ids(root: str | Path) -> list[str]:
    try:
        raw = yaml.safe_load((Path(root) / "paper.yaml").read_text(encoding="utf-8")) or {}
        return [str(sec["id"]).lower() for sec in raw.get("sections", []) if isinstance(sec, dict) and sec.get("id")]
    except Exception:
        return []


# ------------------------------------------------------------------ the two rule files

def _file(root: str | Path, name: str) -> Path:
    return Path(root) / "rules" / f"{name}.json"


def load(root: str | Path, name: str = "candidates") -> list[WritingRule]:
    """rules/<name>.json as rules. A missing or empty file is an empty list; a broken one is an error."""
    path = _file(root, name)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.strip():
        return []
    try:
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError("it must be a list of rules")
        return [WritingRule.model_validate(item) for item in raw]
    except ValueError as exc:                  # also covers a JSON error and a rule that does not fit the schema
        raise ValueError(f"rules/{name}.json is not valid: {_short(exc)}") from None


def save(root: str | Path, rules: list[WritingRule]) -> None:
    """Writes rules/candidates.json, and rules/active_rules.json with the approved rules only."""
    for name, rows in (("candidates", rules), ("active_rules", [r for r in rules if r.approved])):
        path = _file(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([r.model_dump() for r in rows], ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def for_section(root: str | Path, sec_id: str, title: str = "") -> list[WritingRule]:
    """The approved rules that apply to one section: its own and those for all sections."""
    names = {"all", sec_id.lower(), title.lower()}
    return [r for r in load(root, "active_rules") if r.approved and names & {s.lower() for s in r.sections}]


def state(root: str | Path) -> dict:
    try:
        rules = load(root)
    except ValueError:
        rules = []
    return {"guides": len(guide_files(root)), "candidates": len(rules), "approved": sum(r.approved for r in rules)}


# ------------------------------------------------------------------ checking a proposal

def _same(rule: WritingRule) -> tuple[str, str, str]:
    return rule.source_file, _key(rule.source_quote or ""), _key(rule.instruction)


def _page(quote: str, pages: list[tuple[int, str]]) -> int | None:
    """The page that holds the quote, or None if it is not in these pages."""
    wanted = _key(quote)
    keys = [(number, _key(text)) for number, text in pages]
    for number, key in keys:
        if wanted in key:
            return number
    for (number, first), (_, second) in zip(keys, keys[1:]):
        if wanted in first + second:
            return number                      # the passage runs over a page break
    return None


def verify(raw: dict, pages: list[tuple[int, str]], source: str, group: str) -> WritingRule | str:
    """A rule built from one proposal, or the reason it was left out. Nothing is taken on trust:
    the quote must be in the pages, and a banned term must be in the quote."""
    instruction = " ".join(str(raw.get("instruction") or "").split())
    quote = " ".join(unicodedata.normalize("NFKC", str(raw.get("quote") or "")).split())
    if not instruction:
        return "a proposal with no instruction"
    if len(quote.split()) < MIN_QUOTE_WORDS:
        return f"{_short(instruction, 90)} (its quote is too short to check)"
    page = _page(quote, pages)
    if page is None:
        return f"{_short(instruction, 90)} (its quote is not in the guide)"
    category = str(raw.get("category") or "").strip().lower().replace(" ", "_")
    priority = str(raw.get("priority") or "").strip().lower()
    priority = priority if priority in PRIORITIES else "recommended"
    sections = [" ".join(str(s).lower().split()) for s in raw.get("sections") or [] if str(s).strip()]
    terms: list[str] = []
    for term in raw.get("avoid_terms") or []:
        term = " ".join(unicodedata.normalize("NFKC", str(term)).split()).strip("\"'“”‘’.,;:")
        in_quote = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", quote, re.IGNORECASE) if term else None
        if len(term) >= 2 and len(term.split()) <= 6 and in_quote and term.lower() not in [t.lower() for t in terms]:
            terms.append(term)
    return WritingRule(
        id="", category=category if category in CATEGORIES else "language", instruction=instruction,
        sections=sections or ["all"], priority=priority, severity="blocking" if priority == "required" else "warning",
        validation_method="python" if terms else "ai", source_file=source, source_page=page, source_quote=quote,
        group=group, avoid_terms=terms, approved=False)


# ------------------------------------------------------------------ guides -> candidates

def extract(root: str | Path, fresh: bool = False, say=lambda text: None) -> dict:
    """Reads every guide, asks the model part by part and writes rules/candidates.json.

    A rule that is already a candidate is left exactly as it is, with its id, your edits and its approval.
    `fresh` asks the model again instead of using the answers saved in .cache/guides/.
    """
    root = Path(root)
    files = guide_files(root)
    if not files:
        raise ValueError(f"No guides found. Put PDF, .md or .txt files in {GUIDES}/journal, "
                         f"{GUIDES}/reporting or {GUIDES}/general.")
    old = load(root)
    sections = section_ids(root)
    limit = int(os.environ.get("PAPERKIT_GUIDE_WORDS") or "1500")
    agents.LOG_DIR = root / "state" / "log"
    found: list[WritingRule] = []
    seen: set[tuple[str, str, str]] = set()
    dropped: list[str] = []
    failed: list[str] = []
    unread: set[str] = set()                   # guides that were not read in full this time

    for path in files:
        source = path.relative_to(root).as_posix()
        inner = path.relative_to(root / GUIDES).parts
        group = inner[0] if len(inner) > 1 else "general"
        try:
            pages = read_guide(path)
        except Exception as exc:
            failed.append(f"{source}: {_short(exc)}")
            unread.add(source)
            continue
        if not pages:
            failed.append(f"{source}: no text in it (a scanned PDF needs OCR first)")
            continue
        chunks = parts(pages, limit)
        for number, chunk in enumerate(chunks, 1):
            span = f"page {chunk[0][0]}" if len(chunk) == 1 else f"pages {chunk[0][0]}-{chunk[-1][0]}"
            where = f"rules: {source}, part {number} of {len(chunks)} ({span})"
            text = "\n\n".join(f"[page {page}]\n{body}" for page, body in chunk)
            digest = hashlib.sha256(json.dumps([PROMPT, sections, text]).encode("utf-8")).hexdigest()[:24]
            cache = root / ".cache" / "guides" / f"{digest}.json"
            proposed = None
            if cache.is_file() and not fresh:
                try:
                    proposed = json.loads(cache.read_text(encoding="utf-8"))
                except ValueError:
                    proposed = None
            if proposed is not None:
                say(f"{where}: answer kept from an earlier run")
            else:
                say(f"{where}: asking the model, {len(text.split())} words ...")
                user = (agents._tag("paper_sections", ", ".join(sections) or "(none listed)") + "\n\n"
                        + agents._tag("guide", text))
                try:
                    proposed = [rule.model_dump() for rule in agents._ask("rules", PROMPT, user, RuleList).rules]
                except Exception as exc:       # a provider error: keep going, this part is asked again next time
                    failed.append(f"{source}, {span}: {type(exc).__name__}: {_short(exc)}")
                    unread.add(source)
                    continue
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(proposed, ensure_ascii=False), encoding="utf-8")
            for raw in proposed:
                rule = verify(raw, chunk, source, group) if isinstance(raw, dict) else "a proposal that is not a rule"
                if isinstance(rule, str):
                    dropped.append(f"{source}, {span}: {rule}")
                elif _same(rule) not in seen:
                    seen.add(_same(rule))
                    found.append(rule)

    by_rule = {_same(r): r for r in old}
    by_quote: dict[tuple[str, str], list[WritingRule]] = {}
    for rule in old:
        by_quote.setdefault((rule.source_file, _key(rule.source_quote or "")), []).append(rule)
    number = max([int(r.id[1:]) for r in old if re.fullmatch(r"R\d+", r.id)] or [0])
    reused: set[int] = set()
    already: dict[int, WritingRule] = {}       # position in `found` -> the candidate it already is
    for position, rule in enumerate(found):
        before = by_rule.get(_same(rule))
        if before is not None:
            reused.add(id(before))
            already[position] = before
    for position, rule in enumerate(found):    # the same passage with an instruction you have edited
        if position not in already:
            same_quote = [r for r in by_quote.get((rule.source_file, _key(rule.source_quote or "")), [])
                          if id(r) not in reused]
            if len(same_quote) == 1:
                reused.add(id(same_quote[0]))
                already[position] = same_quote[0]
    final: list[WritingRule] = []
    new = 0
    for position, rule in enumerate(found):
        if position in already:
            final.append(already[position])
        else:
            number, new = number + 1, new + 1
            rule.id = f"R{number}"
            final.append(rule)
    for rule in old:                           # rules you added by hand, and those of a guide not read in full
        by_hand = not rule.source_file.startswith(GUIDES + "/")
        if id(rule) not in reused and (by_hand or rule.source_file in unread):
            final.append(rule)
    final.sort(key=lambda r: int(r.id[1:]) if re.fullmatch(r"R\d+", r.id) else 10 ** 9)
    save(root, final)
    return {"files": len(files), "rules": final, "new": new, "dropped": dropped, "failed": failed}


# ------------------------------------------------------------------ approval

def set_approved(root: str | Path, ids, value: bool) -> list[WritingRule]:
    rules = load(root)
    wanted = {str(i).upper() for i in ids}
    unknown = sorted(wanted - {r.id.upper() for r in rules})
    if unknown:
        raise ValueError(f"No such rule: {', '.join(unknown)}. `paperkit rules list` shows the ids.")
    for rule in rules:
        if rule.id.upper() in wanted:
            rule.approved = value
    save(root, rules)
    return [r for r in rules if r.id.upper() in wanted]


def show(rule: WritingRule) -> list[str]:
    where = rule.source_file + (f", p. {rule.source_page}" if rule.source_page else "")
    rows = [f"[{'x' if rule.approved else ' '}] {rule.id}  {rule.priority}, {', '.join(rule.sections)}: {rule.instruction}",
            f'      "{_short(rule.source_quote or "", 220)}"  ({where})']
    if rule.avoid_terms:
        rows.append(f"      code will flag: {', '.join(rule.avoid_terms)}")
    return rows


def review(root: str | Path, ask=input, out=print) -> int:
    """Walks through the candidates that are not approved yet. Returns how many were approved."""
    rules = load(root)
    waiting = [r for r in rules if not r.approved]
    count = 0
    try:
        for number, rule in enumerate(waiting, 1):
            out("")
            out(f"Rule {number} of {len(waiting)}")
            for row in show(rule):
                out(row)
            answer = ask("[y] approve  [n] leave out  [a] approve this and all the rest  [q] stop > ").strip().lower()[:1]
            if answer == "a":
                for rest in waiting[number - 1:]:
                    rest.approved = True
                count += len(waiting) - number + 1
                break
            if answer == "q":
                break
            if answer == "y":
                rule.approved = True
                count += 1
    except EOFError:
        pass
    finally:
        save(root, rules)                      # whatever was decided so far is kept
    return count


# ------------------------------------------------------------------ `paperkit rules`

def run(root: str | Path, action: str = "list", ids=(), everything: bool = False, fresh: bool = False,
        out=print, ask=input) -> int:
    """extract | list | approve | reject. Exit code 1 if something failed."""
    root = Path(root)
    try:
        if action == "extract":
            got = extract(root, fresh, out)
            approved = sum(r.approved for r in got["rules"])
            out(f"rules: {len(got['rules'])} candidate(s) from {got['files']} guide file(s) -> rules/candidates.json "
                f"({got['new']} new, {approved} approved)")
            for row in got["dropped"][:10]:
                out(f"  left out: {row}")
            if len(got["dropped"]) > 10:
                out(f"  ... and {len(got['dropped']) - 10} more left out")
            for row in got["failed"]:
                out(f"  failed: {row}")
            if got["failed"]:
                out("Run it again for what failed: finished parts are kept and are not asked again.")
            if len(got["rules"]) > approved:
                out("Nothing is used until you approve it: paperkit rules approve")
            return 1 if got["failed"] else 0

        rules = load(root)
        if action == "list":
            if not rules:
                out(NONE_YET)
                return 0
            for rule in rules:
                for row in show(rule):
                    out(row)
            out(f"{sum(r.approved for r in rules)} of {len(rules)} approved. Approved rules are in rules/active_rules.json.")
            return 0
        if not rules:
            out(NONE_YET)
            return 1
        if action == "reject":
            if not ids:
                out("Name the rules to take out, for example: paperkit rules reject R3 R7")
                return 1
            out(f"{len(set_approved(root, ids, False))} rule(s) taken out.")
        elif everything:
            for rule in rules:
                rule.approved = True
            save(root, rules)
            out(f"All {len(rules)} rule(s) approved.")
        elif ids:
            out(f"{len(set_approved(root, ids, True))} rule(s) approved.")
        else:
            out(f"{review(root, ask, out)} rule(s) approved.")
        active = len(load(root, "active_rules"))
        out(f"{active} rule(s) in rules/active_rules.json: the writer and reviewer get the ones for their section.")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        out(f"rules: {type(exc).__name__}: {_short(exc, 300)}")
        return 1
