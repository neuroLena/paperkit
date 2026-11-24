"""Draft the two inputs that come straight from the Results section: facts.csv and key_messages.md.

The model proposes; code verifies. A fact is kept only if its text appears word for word in the Results or
Methods text, and its source (file and line) is worked out here, never by the model. A key message is kept
only if it has no digit and, for an observational study, no causal wording. Real content is never replaced
unless `force` is set. Nothing is approved here: a person reads the result, as with the claim table.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from . import agents, facts, preflight
from .schemas import PaperSpec
from .validators.language import CAUSAL

SOURCES = (("results", "Results"), ("methods", "Methods"))
MAX_MESSAGES = 5

FACTS = """You list the numbers that the Discussion of a paper may cite, taken from its Results and Methods text. You write no prose.

Return every statistic as one string copied character for character from the text, with its label, for example "r = 0.31, 95% CI [0.22, 0.40]" or "n = 412".
- One statistic per string. Keep a value and its interval or p-value together when the text prints them together.
- Never compute, round, convert, combine or reformat a number. If you cannot copy it exactly, leave it out.
- Skip years, citation numbers, table and figure numbers, and page numbers."""

MESSAGES = """You draft the key messages of a scientific paper from its Results text.

Return 3 to 5 messages. Each is one complete sentence that says what was found and in whom or what.
- No digit anywhere: write "was associated with higher", not the number.
- Say only what the results support. If the study design is observational, use no causal wording.
- Do not list limitations: they are kept elsewhere.
- Do not say one message twice in different words."""


class FactList(BaseModel):
    facts: list[str] = Field(description="Each statistic exactly as printed in the text, with its label")


class MessageList(BaseModel):
    messages: list[str] = Field(description="Three to five one-sentence key messages with no digits")


class Skip(Exception):
    """The file already has real content. Not an error."""


def _norm(text: str) -> str:
    return " ".join(text.split())


def facts_are_default(root: Path) -> bool:
    """inputs/facts.csv is missing, empty, or holds only the scaffold's EXAMPLE rows."""
    path = Path(root) / "inputs" / "facts.csv"
    if not path.is_file():
        return True
    try:
        rows = preflight.read_facts_csv(path)
    except (ValueError, csv.Error, UnicodeDecodeError):
        return False                       # a file somebody wrote and broke: leave it alone
    return all("EXAMPLE" in row["text"] for row in rows)


def messages_are_default(root: Path) -> bool:
    return not preflight.content_lines(Path(root) / "inputs" / "key_messages.md")


def _read(root: Path, name: str) -> str:
    path = Path(root) / "inputs" / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _results(root: Path) -> None:
    words = sum(len(line.split()) for line in preflight.content_lines(Path(root) / "inputs" / "results.md"))
    if words < preflight.MIN_WORDS:
        raise ValueError("Fill in inputs/results.md first: the Results section is what these are drafted from.")


def _where(texts: dict[str, str], fact: str) -> str | None:
    """'Results, line 7' for the first place the fact appears (spaces ignored), or None if it is not there."""
    for name, label in SOURCES:
        for number, line in enumerate(texts[name].splitlines(), 1):
            if fact in _norm(line):
                return f"{label}, line {number}"
        if fact in _norm(texts[name]):
            return label                   # the fact runs over a line break
    return None


def _ask(root: Path, kind: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    agents.LOG_DIR = Path(root) / "state" / "log"
    return agents._ask(kind, system, user, schema)


def extract_facts(root: str | Path, force: bool = False) -> dict:
    """inputs/facts.csv and facts/facts.json from the Results and Methods text."""
    root = Path(root)
    if not force and not facts_are_default(root):
        raise Skip("inputs/facts.csv already has facts (repeat with --force to replace them)")
    _results(root)
    texts = {name: _read(root, name) for name, _ in SOURCES}
    user = "\n\n".join(agents._tag(name, texts[name]) for name, _ in SOURCES)
    proposed = _ask(root, "facts", FACTS, user, FactList).facts
    rows, dropped, seen = [], [], set()
    for raw in proposed:
        text = _norm(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        place = _where(texts, text)
        if place is None or not re.search(r"\d", text):
            dropped.append(text)           # not in the text, or not a number: never trusted
            continue
        rows.append({"id": f"F{len(rows) + 1}", "text": text, "source": place})
    if not rows:
        raise ValueError("None of the proposed facts could be found word for word in the text.")
    path = root / "inputs" / "facts.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "text", "source"])
        writer.writeheader()
        writer.writerows(rows)
    facts.from_csv(path, root / "facts" / "facts.json")
    return {"rows": rows, "dropped": dropped}


def _design(root: Path) -> str:
    try:
        return PaperSpec.model_validate(yaml.safe_load((root / "paper.yaml").read_text(encoding="utf-8"))).design
    except Exception:
        return "observational"             # the stricter reading


def extract_key_messages(root: str | Path, force: bool = False) -> dict:
    """inputs/key_messages.md from the Results text."""
    root = Path(root)
    if not force and not messages_are_default(root):
        raise Skip("inputs/key_messages.md already has messages (repeat with --force to replace them)")
    _results(root)
    design = _design(root)
    user = "\n\n".join([agents._tag("study_design", design), agents._tag("results", _read(root, "results"))])
    proposed = _ask(root, "planner", MESSAGES, user, MessageList).messages
    kept, dropped = [], []
    for raw in proposed:
        text = _norm(raw).lstrip("-*• ").strip()
        if not text:
            continue
        why = ("has a digit" if re.search(r"\d", text)
               else "causal wording in an observational study" if design == "observational" and CAUSAL.search(text)
               else "")
        if why:
            dropped.append(f"{text} ({why})")
        elif text not in kept:
            kept.append(text)
    kept = kept[:MAX_MESSAGES]
    if not kept:
        raise ValueError("None of the proposed messages passed the checks.")
    (root / "inputs" / "key_messages.md").write_text(
        "# Key messages\n\n## Drafted by the model from inputs/results.md: review and edit before planning\n\n"
        + "\n".join(f"- {text}" for text in kept) + "\n", encoding="utf-8")
    return {"messages": kept, "dropped": dropped}


def run(root: str | Path, what: str = "all", force: bool = False, out=print) -> int:
    """`paperkit extract`: prints what was written and what was thrown away. Exit code 1 if a step failed."""
    root, code = Path(root), 0
    if what in ("all", "facts"):
        try:
            got = extract_facts(root, force)
            out(f"facts: {len(got['rows'])} -> inputs/facts.csv and facts/facts.json")
            for r in got["rows"]:
                out(f"  {r['id']:<5}{r['text']}   ({r['source']})")
            for text in got["dropped"]:
                out(f"  not in the text, left out: {text}")
        except Skip as why:
            out(f"facts: skipped, {why}")
        except Exception as exc:               # a missing key or a provider error: say so, do not crash
            out(f"facts: {type(exc).__name__}: {' '.join(str(exc).split())[:300]}")
            code = 1
    if what in ("all", "key-messages"):
        try:
            got = extract_key_messages(root, force)
            out(f"key messages: {len(got['messages'])} -> inputs/key_messages.md")
            for text in got["messages"]:
                out(f"  - {text}")
            for text in got["dropped"]:
                out(f"  left out: {text}")
        except Skip as why:
            out(f"key messages: skipped, {why}")
        except Exception as exc:
            out(f"key messages: {type(exc).__name__}: {' '.join(str(exc).split())[:300]}")
            code = 1
    if code == 0:
        out("Read both files and correct them before `paperkit plan`: a model drafted them.")
    return code
