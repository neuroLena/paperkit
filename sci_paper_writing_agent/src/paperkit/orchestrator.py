"""State machine. This file, not the agent, decides what happens next.

Section statuses:
NEW -> AWAITING_APPROVAL (or CLAIMS_INVALID) -> APPROVED -> DONE (or ESCALATED)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from . import agents, facts, wiki, zotero
from .ingestion import rules_ingest
from .schemas import ClaimTable, Issue, PaperSpec
from .validators import GateContext, blocking, check_claims, run_gates
from .validators.common import COMMENT


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rows(issues: list[Issue]) -> list[dict]:
    return [i.model_dump() for i in issues]


class Project:
    """All state lives on disk, so a run can be resumed from any point."""

    def __init__(self, root: str | Path = "."):
        self.root = Path(root)
        raw = yaml.safe_load((self.root / "paper.yaml").read_text(encoding="utf-8"))
        self.spec = PaperSpec.model_validate(raw)
        self.facts = facts.load(self.root / "facts" / "facts.json")
        self.bib = zotero.load_bib(self.root / "refs" / "library.bib")
        agents.LOG_DIR = self.root / "state" / "log"

    def inp(self, name: str) -> str:
        path = self.root / "inputs" / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def draft(self, sec_id: str) -> str:
        """The author's own starting draft, inputs/<section>_draft.md, without its explanatory comment.

        Empty when the file holds nothing but headings, so the default file changes nothing.
        """
        text = COMMENT.sub("", self.inp(f"{sec_id}_draft")).strip()
        return text if any(row.strip() and not row.lstrip().startswith("#") for row in text.splitlines()) else ""

    def claims_path(self, sec_id: str) -> Path:
        return self.root / "state" / "claims" / f"{sec_id}.json"

    def load_claims(self, sec_id: str) -> ClaimTable | None:
        path = self.claims_path(sec_id)
        return ClaimTable.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def save_claims(self, table: ClaimTable) -> None:
        _dump(self.claims_path(table.section_id), table.model_dump())

    def status(self) -> dict[str, str]:
        path = self.root / "state" / "status.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def set_status(self, sec_id: str, value: str) -> str:
        _dump(self.root / "state" / "status.json", {**self.status(), sec_id: value})
        return value

    def rules(self, sec_id: str) -> list:
        """The approved writing rules for this section, from rules/active_rules.json."""
        sec = self.spec.section(sec_id)
        return rules_ingest.for_section(self.root, sec.id, sec.title)

    def ctx(self, sec_id: str, table: ClaimTable) -> GateContext:
        return GateContext(spec=self.spec, sec=self.spec.section(sec_id), claims=table,
                           facts=self.facts, bib_keys=set(self.bib), rules=self.rules(sec_id))


def _quiet(text: str = "") -> None:
    """The default `say`: nothing is reported."""


def _model(kind: str) -> str:
    return "stand-in model" if agents.LLM else agents.route(kind)[1]


def _next(rnd: int, rounds: int, who: str) -> str:
    return f"back to the {who}" if rnd < rounds else "no rounds left"


def _list(say, issues: list[Issue], limit: int = 5) -> None:
    for issue in issues[:limit]:
        say(f"           [{issue.gate}] {' '.join(issue.message.split())[:160]}")
    if len(issues) > limit:
        say(f"           ... and {len(issues) - limit} more")


def plan(p: Project, sec_id: str, say=_quiet) -> tuple[ClaimTable, list[Issue]]:
    """Planner -> claim table. The claims gate sends its errors back to the planner. `say` gets a line per stage."""
    sec = p.spec.section(sec_id)
    issues: list[Issue] = []
    table = ClaimTable(section_id=sec_id, claims=[])
    rounds = p.spec.max_rounds
    for rnd in range(1, rounds + 1):
        say(f"{sec_id}: planning, round {rnd} of {rounds}")
        say(f"  planner  {_model('planner')} is building the claim table ...")
        started = time.monotonic()
        claims = agents.plan_claims(
            sec, design=p.spec.design, key_messages=p.inp("key_messages"), limitations=p.inp("limitations"),
            methods=p.inp("methods"), results=p.inp("results"), introduction=p.inp("introduction"), fact_reg=p.facts,
            starting_draft=p.draft(sec_id),
            library=zotero.library_listing(p.bib), wiki_index=wiki.index(p.root / "wiki"), issues=issues)
        table = ClaimTable(section_id=sec_id, approved=False, claims=claims)
        issues = blocking(check_claims(table, p.facts, set(p.bib)))
        say(f"  planner  done in {time.monotonic() - started:.0f} s: {len(claims)} claims")
        if not issues:
            say("  check    passed")
            break
        say(f"  check    {len(issues)} problem(s), {_next(rnd, rounds, 'planner')}:")
        _list(say, issues)
    p.save_claims(table)
    p.set_status(sec_id, "CLAIMS_INVALID" if issues else "AWAITING_APPROVAL")
    return table, issues


def approve(p: Project, sec_id: str) -> list[Issue]:
    """A person has read the table. Code checks it once more and only then sets the flag."""
    table = p.load_claims(sec_id)
    if table is None:
        raise FileNotFoundError(f"No claim table for '{sec_id}'. Run: paperkit plan {sec_id}")
    issues = blocking(check_claims(table, p.facts, set(p.bib)))
    if not issues:
        table.approved = True
        p.save_claims(table)
        p.set_status(sec_id, "APPROVED")
    return issues


def run_section(p: Project, sec_id: str, say=_quiet) -> str:
    """Writer -> gates -> reviewer, until clean or until the rounds run out. `say` gets a line per stage."""
    sec = p.spec.section(sec_id)
    table = p.load_claims(sec_id)
    if table is None:
        table, _ = plan(p, sec_id, say)
    if blocking(check_claims(table, p.facts, set(p.bib))):
        say(f"{sec_id}: the claim table has errors, nothing was written")
        return p.set_status(sec_id, "CLAIMS_INVALID")
    if not table.approved:
        say(f"{sec_id}: the claim table is not approved yet, nothing was written")
        return p.set_status(sec_id, "AWAITING_APPROVAL")

    ctx = p.ctx(sec_id, table)
    fact_sub = {fid: p.facts[fid] for c in table.claims for fid in c.fact_ids}
    pages = wiki.pages_for(p.root / "wiki", [k for c in table.claims for k in c.cite_keys])
    drafts, reviews = p.root / "drafts", p.root / "state" / "reviews"
    drafts.mkdir(parents=True, exist_ok=True)
    rules = [{"id": r.id, "instruction": r.instruction, "priority": r.priority} for r in ctx.rules]
    if rules:
        say(f"{sec_id}: {len(rules)} approved writing rule(s) apply")

    draft, issues, rounds = "", [], p.spec.max_rounds
    for rnd in range(1, rounds + 1):
        say(f"{sec_id}: round {rnd} of {rounds}")
        say(f"  writer   {_model('writer')} is writing the draft ...")
        started = time.monotonic()
        draft = agents.write_section(sec, design=p.spec.design, claims=table.claims, fact_reg=fact_sub,
                                     wiki_pages=pages, prev_draft=draft, issues=issues,
                                     starting_draft=p.draft(sec_id), rules=rules)
        (drafts / f"{sec_id}.r{rnd}.md").write_text(draft, encoding="utf-8")
        say(f"  writer   done in {time.monotonic() - started:.0f} s: {len(draft.split())} words "
            f"-> drafts/{sec_id}.r{rnd}.md")

        gate_issues = run_gates(draft, ctx)
        issues = blocking(gate_issues)
        if issues:
            _dump(reviews / f"{sec_id}.r{rnd}.json", {"gates": _rows(gate_issues), "review": []})
            say(f"  gates    {len(issues)} problem(s), {_next(rnd, rounds, 'writer')}:")
            _list(say, issues)
            continue                                   # never reaches the reviewer
        say("  gates    passed")

        say(f"  reviewer {_model('reviewer')} is reading the draft ...")
        started = time.monotonic()
        review = agents.review_section(sec, design=p.spec.design, methods=p.inp("methods"),
                                       results=p.inp("results"), claims=table.claims, fact_reg=fact_sub,
                                       wiki_pages=pages, draft=draft, rules=rules)
        _dump(reviews / f"{sec_id}.r{rnd}.json", {"gates": _rows(gate_issues), "review": _rows(review)})
        issues = blocking(review)
        took = f"done in {time.monotonic() - started:.0f} s"
        if not issues:
            (drafts / f"{sec_id}.md").write_text(draft, encoding="utf-8")
            say(f"  reviewer {took}: no problems -> drafts/{sec_id}.md")
            return p.set_status(sec_id, "DONE")
        say(f"  reviewer {took}: {len(issues)} problem(s), {_next(rnd, rounds, 'writer')}:")
        _list(say, issues)

    _dump(reviews / f"{sec_id}.open.json", _rows(issues))   # hand over to a person; never accept silently
    say(f"{sec_id}: {len(issues)} problem(s) left after {rounds} rounds -> state/reviews/{sec_id}.open.json")
    return p.set_status(sec_id, "ESCALATED")


def run(p: Project, only: str | None = None, say=_quiet) -> dict[str, str]:
    return {sec.id: run_section(p, sec.id, say) for sec in p.spec.sections if only in (None, sec.id)}


def validate(p: Project, sec_id: str, path: Path | None = None) -> list[Issue]:
    """Gates only, no model. Uses the finished draft by default, otherwise the latest round."""
    table = p.load_claims(sec_id)
    if table is None:
        return [Issue(gate="claims", message=f"No claim table for '{sec_id}'")]
    if path is None:
        final = p.root / "drafts" / f"{sec_id}.md"
        rounds = sorted((p.root / "drafts").glob(f"{sec_id}.r*.md"),
                        key=lambda f: int(f.stem.rsplit(".r", 1)[1]))
        path = final if final.exists() else (rounds[-1] if rounds else None)
    if path is None or not Path(path).exists():
        return [Issue(gate="structure", message=f"No draft for '{sec_id}'")]
    return check_claims(table, p.facts, set(p.bib)) + run_gates(Path(path).read_text(encoding="utf-8"), p.ctx(sec_id, table))
