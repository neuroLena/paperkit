"""Writing guides -> writing rules.

PDF, .md or .txt files in .writing_guides/ (general/, journal/, reporting/) become rules for the writer and reviewer.
The model proposes; code verifies; a person approves:
- each guide is read page by page and sent to the `rules` agent a few pages at a time;
- a proposed rule is kept only if its quote is really in those pages (the same letters and digits in the same
  order), and its page is worked out here, never by the model;
- kept rules go to rules/candidates.json with approved set to false. Only approved rules, which are copied to
  rules/active_rules.json, ever reach the writer, the reviewer and the gate;
- every answered part is saved in .cache/guides/, so a run that failed half way continues where it stopped.

`check` is a separate step for after the guides are read. It drops rules that repeat another rule and marks
rules that contradict each other. Nothing is deleted: a dropped rule stays in rules/candidates.json with a note
of the rule it repeats, and `restore` brings it back.
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

from .. import agents, keys
from ..ingestion_schemas import WritingRule

GUIDES = ".writing_guides"
SUFFIXES = (".pdf", ".md", ".txt")
CATEGORIES = ("structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting",
              "scientific_reasoning")
PRIORITIES = ("required", "recommended", "optional")
MIN_QUOTE_WORDS = 3
KEPT_BY_HAND = "none"           # duplicate_of of a rule a person restored: it is never dropped again
STRENGTH = {"required": 0, "recommended": 1, "optional": 2}
AUTHORITY = {"journal": 0, "reporting": 1, "general": 2}       # whose wording is kept when two guides say the same
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


COMPARE = """You compare writing rules that were taken from several guides. You change no rule and you write no new one.

Each line of <rules> is: id [sections; priority; kind of guide] instruction.

Return:
- repeats: groups of rule ids that ask for the same thing, so that a text that follows one of them follows the others too. The same requirement in other words is a repeat. A stricter, narrower or more detailed version is NOT a repeat: leave it out. Put an id in one group at most.
- contradictions: pairs of rule ids that cannot both be followed in the same section, each with a one-sentence reason. Examples: two different word limits for the same section; one rule requires what the other forbids. Rules for different sections do not contradict each other. A general rule and a stricter rule on the same point do not contradict each other.

If there are none, return empty lists. Use only ids that are in <rules>."""


class Repeat(BaseModel):
    ids: list[str] = Field(description="Ids of rules that ask for the same thing")


class Clash(BaseModel):
    first: str = Field(description="A rule id")
    second: str = Field(description="The id of the rule it contradicts")
    reason: str = Field(default="", description="One sentence: why both cannot be followed")


class RuleCheck(BaseModel):
    repeats: list[Repeat] = Field(default_factory=list)
    contradictions: list[Clash] = Field(default_factory=list)


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


def dropped(rule: WritingRule) -> bool:
    """True for a rule that `check` set aside because it repeats another rule."""
    return rule.duplicate_of not in ("", KEPT_BY_HAND)


def paper_sections(root: str | Path) -> set[str]:
    """The names a rule can use for a section of this paper: the ids and titles in paper.yaml, and "all"."""
    names = {"all"}
    try:
        raw = yaml.safe_load((Path(root) / "paper.yaml").read_text(encoding="utf-8")) or {}
        for sec in raw.get("sections", []):
            if isinstance(sec, dict):
                names |= {str(sec[k]).lower() for k in ("id", "title") if sec.get(k)}
    except Exception:
        pass
    return names


def relevant(rule: WritingRule, names: set[str]) -> bool:
    """True if the rule can apply to a section this paper has. Guides are full of rules for other sections
    (abstract, methods, references ...): those are kept but not compared, and you are not asked about them."""
    return len(names) == 1 or bool(names & {s.lower() for s in rule.sections})


def _number(rule: WritingRule) -> int:
    found = re.fullmatch(r"R(\d+)", rule.id)
    return int(found.group(1)) if found else 10 ** 9


def clashes(rules: list[WritingRule], approved_only: bool = False) -> list[tuple[str, str, str]]:
    """(id, id, reason) for every pair of rules marked as contradicting. With approved_only: both are in use."""
    live = {r.id: r for r in rules if not dropped(r) and (r.approved or not approved_only)}
    return [(r.id, other, reason) for r in sorted(live.values(), key=_number) for other, reason in r.conflicts.items()
            if other in live and _number(r) < _number(live[other])]


def state(root: str | Path) -> dict:
    try:
        rules = load(root)
    except ValueError:
        rules = []
    names = paper_sections(root)
    live = [r for r in rules if not dropped(r)]
    ours = [r for r in live if relevant(r, names)]
    return {"guides": len(guide_files(root)), "candidates": len(live), "relevant": len(ours),
            "approved": sum(r.approved for r in ours), "dropped": len(rules) - len(live), "conflicts": len(clashes(rules))}


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


# ------------------------------------------------------------------ repeats and contradictions

def _overlap(first: WritingRule, second: WritingRule) -> bool:
    """True if both rules can apply to the same section. Rules for different sections neither repeat nor contradict."""
    one, two = {s.lower() for s in first.sections}, {s.lower() for s in second.sections}
    return "all" in one or "all" in two or bool(one & two)


def check(root: str | Path, fresh: bool = False, say=lambda text: None) -> dict:
    """Drops rules that repeat another rule and marks rules that contradict each other. Run it after `extract`.

    Only rules for the sections this paper has are compared. Word-for-word repeats are found by code. Repeats in
    other words and contradictions are proposed by the model, one category of rules at a time, and code accepts
    them only between rules it showed the model that can apply to the same section. Of a group of repeats one
    rule is kept: an approved one first, then the journal's guide before a reporting guideline before a general
    style guide. It takes over the widest scope and the strictest priority of the group.
    """
    root = Path(root)
    rules = load(root)
    names = paper_sections(root)
    live = [r for r in rules if not dropped(r)]
    compared = [r for r in live if relevant(r, names)]
    if len(compared) < 2:
        raise ValueError("There are fewer than two rules for this paper's sections to compare. "
                         "Read the guides first: paperkit rules extract")
    for rule in rules:
        rule.conflicts = {}                    # worked out again from scratch every time
    everyone = {r.id.upper(): r for r in rules}

    groups: list[list[WritingRule]] = []
    word_for_word: dict[str, list[WritingRule]] = {}
    for rule in compared:
        word_for_word.setdefault(_key(rule.instruction), []).append(rule)
    groups += [group for group in word_for_word.values() if len(group) > 1]

    # the model sees one category at a time, at most PAPERKIT_CHECK_RULES rules per request
    limit = max(2, int(os.environ.get("PAPERKIT_CHECK_RULES") or "80"))
    by_category: dict[str, list[WritingRule]] = {}
    for rule in compared:
        by_category.setdefault(rule.category, []).append(rule)
    batches: list[tuple[str, list[WritingRule]]] = []
    for category in sorted(by_category):
        rows = sorted(by_category[category], key=lambda r: (sorted(x.lower() for x in r.sections), _number(r)))
        batches += [(category, rows[i:i + limit]) for i in range(0, len(rows), limit) if len(rows[i:i + limit]) > 1]

    agents.LOG_DIR = root / "state" / "log"
    answers: list[tuple[list[WritingRule], RuleCheck]] = []
    failed: list[str] = []
    for number, (category, part) in enumerate(batches, 1):
        listing = "\n".join(f"{r.id} [{', '.join(r.sections)}; {r.priority}; {r.group or 'general'}] {r.instruction}"
                            for r in part)
        digest = hashlib.sha256(json.dumps([COMPARE, listing]).encode("utf-8")).hexdigest()[:24]
        cache = root / ".cache" / "guides" / f"check-{digest}.json"
        where = f"rules: {category} rules, group {number} of {len(batches)} ({len(part)} rules)"
        answer = None
        if cache.is_file() and not fresh:
            try:
                answer = RuleCheck.model_validate_json(cache.read_text(encoding="utf-8"))
                say(f"{where}: answer kept from an earlier run")
            except ValueError:
                answer = None
        if answer is None:
            say(f"{where}: asking the model ...")
            try:
                answer = agents._ask("rules", COMPARE, agents._tag("rules", listing), RuleCheck)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(answer.model_dump_json(), encoding="utf-8")
            except Exception as exc:           # a provider error: the other groups still count
                failed.append(f"{category} rules: {type(exc).__name__}: {_short(exc)}")
                continue
        answers.append((part, answer))

    grouped = {id(r) for group in groups for r in group}
    for part, answer in answers:
        shown = {r.id.upper(): r for r in part}
        for repeat in answer.repeats:
            members: list[WritingRule] = []
            for raw in repeat.ids:
                rule = shown.get(str(raw).strip().upper())
                if (rule is not None and id(rule) not in grouped and rule not in members
                        and all(_overlap(rule, other) for other in members)):
                    members.append(rule)
            if len(members) > 1:
                groups.append(members)
                grouped |= {id(r) for r in members}

    removed: list[tuple[WritingRule, WritingRule]] = []
    for group in groups:
        group = [r for r in group if r.duplicate_of != KEPT_BY_HAND]         # a person kept these: never dropped
        if len(group) < 2:
            continue
        kept = min(group, key=lambda r: (not r.approved, AUTHORITY.get(r.group, 3), STRENGTH.get(r.priority, 3), _number(r)))
        sections = list(dict.fromkeys(x for r in group for x in r.sections))
        kept.sections = ["all"] if "all" in [x.lower() for x in sections] else sections
        kept.priority = min((r.priority for r in group), key=lambda name: STRENGTH.get(name, 3))
        kept.severity = "blocking" if kept.priority == "required" else kept.severity
        for rule in group:
            if rule is kept:
                continue
            kept.avoid_terms += [t for t in rule.avoid_terms if t.lower() not in [k.lower() for k in kept.avoid_terms]]
            rule.duplicate_of, rule.approved = kept.id, False
            removed.append((kept, rule))
        if kept.avoid_terms:
            kept.validation_method = "python"

    found: list[tuple[WritingRule, WritingRule, str]] = []
    for part, answer in answers:
        shown = {r.id.upper(): r for r in part}
        for clash in answer.contradictions:
            pair = []
            for raw in (clash.first, clash.second):
                rule = shown.get(str(raw).strip().upper())
                if rule is not None and dropped(rule):     # it was dropped: the rule it repeats stands in for it
                    rule = everyone.get(rule.duplicate_of.upper())
                pair.append(rule)
            first, second = pair
            if first is None or second is None or first is second or dropped(first) or dropped(second):
                continue
            if not _overlap(first, second) or second.id in first.conflicts:
                continue
            reason = _short(clash.reason) or "They cannot both be followed."
            first.conflicts[second.id] = second.conflicts[first.id] = reason
            found.append((first, second, reason) if _number(first) < _number(second) else (second, first, reason))
    save(root, rules)
    return {"checked": len(compared), "others": len(live) - len(compared), "dropped": removed, "clashes": found,
            "failed": failed}


def restore(root: str | Path, ids) -> list[WritingRule]:
    """Brings back rules that `check` dropped. They become candidates again and are never dropped a second time."""
    rules = load(root)
    wanted = {str(i).upper() for i in ids}
    unknown = sorted(wanted - {r.id.upper() for r in rules})
    if unknown:
        raise ValueError(f"No such rule: {', '.join(unknown)}. `paperkit rules list` shows the ids.")
    back = [r for r in rules if r.id.upper() in wanted and dropped(r)]
    for rule in back:
        rule.duplicate_of = KEPT_BY_HAND
    save(root, rules)
    return back


# ------------------------------------------------------------------ approval

def set_approved(root: str | Path, ids, value: bool) -> list[WritingRule]:
    rules = load(root)
    wanted = {str(i).upper() for i in ids}
    unknown = sorted(wanted - {r.id.upper() for r in rules})
    if unknown:
        raise ValueError(f"No such rule: {', '.join(unknown)}. `paperkit rules list` shows the ids.")
    gone = [r for r in rules if value and r.id.upper() in wanted and dropped(r)]
    if gone:
        raise ValueError(f"{gone[0].id} was dropped because it repeats {gone[0].duplicate_of}. "
                         f"To use it after all: paperkit rules restore {gone[0].id}")
    for rule in rules:
        if rule.id.upper() in wanted:
            rule.approved = value
    save(root, rules)
    return [r for r in rules if r.id.upper() in wanted]


def show(rule: WritingRule) -> list[str]:
    where = rule.source_file + (f", p. {rule.source_page}" if rule.source_page else "")
    mark = "=" if dropped(rule) else "x" if rule.approved else " "
    rows = [f"[{mark}] {rule.id}  {rule.priority}, {', '.join(rule.sections)}: {rule.instruction}",
            f'      "{_short(rule.source_quote or "", 220)}"  ({where})']
    if rule.avoid_terms:
        rows.append(f"      code will flag: {', '.join(rule.avoid_terms)}")
    if dropped(rule):
        rows.append(f"      dropped: it repeats {rule.duplicate_of} (to use it after all: paperkit rules restore {rule.id})")
    for other, reason in rule.conflicts.items():
        rows.append(f"      CONTRADICTS {other}: {reason}")
    return rows


def review(root: str | Path, ask=input, out=print) -> int:
    """Walks through the candidates that are not approved yet. Returns how many were approved."""
    rules = load(root)
    names = paper_sections(root)
    waiting = [r for r in rules if not r.approved and not dropped(r) and relevant(r, names)]
    elsewhere = [r for r in rules if not r.approved and not dropped(r) and not relevant(r, names)]
    if elsewhere:
        other = sorted({x.lower() for r in elsewhere for x in r.sections})
        out(f"{len(elsewhere)} rule(s) are for sections that paper.yaml does not have ({', '.join(other[:8])}"
            f"{', ...' if len(other) > 8 else ''}): you are not asked about them. `paperkit rules list` shows them.")
    count = 0
    try:
        for number, rule in enumerate(waiting, 1):
            out("")
            out(f"Rule {number} of {len(waiting)}")
            for row in show(rule):
                out(row)
            answer = keys.latin(keys.read(
                ask, "[y] approve  [n] leave out  [a] approve this and all the rest  [q] stop > ", out).strip().lower())[:1]
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
    """extract | check | list | approve | reject | restore. Exit code 1 if something failed."""
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
            if len(got["rules"]) > 1:
                out("Next, drop repeated rules and find contradictions: paperkit rules check")
            if len(got["rules"]) > approved:
                out("Nothing is used until you approve it: paperkit rules approve")
            return 1 if got["failed"] else 0

        if action == "check":
            got = check(root, fresh, out)
            out(f"rules: {got['checked']} rule(s) compared."
                + (f" {got['others']} more are for sections that paper.yaml does not have: they were left alone."
                   if got["others"] else ""))
            out(f"Repeats dropped: {len(got['dropped'])}")
            for kept in dict.fromkeys(k.id for k, _ in got["dropped"]):
                first = next(k for k, _ in got["dropped"] if k.id == kept)
                out(f"  {first.id} kept ({first.source_file}, {first.priority}, {', '.join(first.sections)}): {first.instruction}")
                for _, gone in [pair for pair in got["dropped"] if pair[0].id == kept]:
                    out(f"      dropped {gone.id} ({gone.source_file}): {gone.instruction}")
            if got["dropped"]:
                out("  A dropped rule stays in rules/candidates.json. To use one after all: paperkit rules restore <id>")
            out(f"Contradictions: {len(got['clashes'])}" + ("   <- settle these" if got["clashes"] else ""))
            for first, second, reason in got["clashes"]:
                for rule in (first, second):
                    where = rule.source_file + (f", p. {rule.source_page}" if rule.source_page else "")
                    out(f"  {rule.id} ({where}, {rule.priority}{', approved' if rule.approved else ''}): {rule.instruction}")
                out(f"      why: {reason}")
            if got["clashes"]:
                out("  Use one rule of each pair. Take the other out with: paperkit rules reject <id>")
            for row in got["failed"]:
                out(f"  failed: {row}")
            if got["failed"]:
                out("  Those rules were only checked for word-for-word repeats. Run it again: finished groups are kept.")
            in_use = clashes(load(root), approved_only=True)
            for first_id, second_id, _ in in_use:
                out(f"WARNING: {first_id} and {second_id} contradict each other and both are approved.")
            return 1 if got["failed"] or in_use else 0

        rules = load(root)
        if action == "list":
            if not rules:
                out(NONE_YET)
                return 0
            for rule in rules:
                for row in show(rule):
                    out(row)
            live = [r for r in rules if not dropped(r)]
            out(f"{sum(r.approved for r in live)} of {len(live)} approved. Approved rules are in rules/active_rules.json."
                + (f" {len(rules) - len(live)} dropped as repeats [=]." if len(rules) > len(live) else "")
                + (f" {len(clashes(rules))} contradiction(s) to settle." if clashes(rules) else ""))
            return 0
        if not rules:
            out(NONE_YET)
            return 1
        if action == "restore":
            if not ids:
                out("Name the dropped rules to bring back, for example: paperkit rules restore R7")
                return 1
            back = restore(root, ids)
            out(f"{len(back)} rule(s) brought back as candidates" + (f": {', '.join(r.id for r in back)}." if back else "."))
            return 0
        if action == "reject":
            if not ids:
                out("Name the rules to take out, for example: paperkit rules reject R3 R7")
                return 1
            out(f"{len(set_approved(root, ids, False))} rule(s) taken out.")
        elif everything:
            live = [r for r in rules if not dropped(r)]
            for rule in live:
                rule.approved = True
            save(root, rules)
            out(f"All {len(live)} rule(s) approved.")
        elif ids:
            out(f"{len(set_approved(root, ids, True))} rule(s) approved.")
        else:
            out(f"{review(root, ask, out)} rule(s) approved.")
        active = len(load(root, "active_rules"))
        out(f"{active} rule(s) in rules/active_rules.json: the writer and reviewer get the ones for their section.")
        for first_id, second_id, reason in clashes(load(root), approved_only=True):
            out(f"WARNING: {first_id} and {second_id} contradict each other and both are approved: {reason} "
                f"Take one of them out: paperkit rules reject <id>")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        out(f"rules: {type(exc).__name__}: {_short(exc, 300)}")
        return 1
