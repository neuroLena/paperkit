"""State machine. This file, not the agent, decides what happens next.

Section statuses:
NEW -> AWAITING_APPROVAL (or CLAIMS_INVALID) -> APPROVED -> DONE (or ESCALATED)
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import agents, facts, wiki, zotero
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

    def ctx(self, sec_id: str, table: ClaimTable) -> GateContext:
        return GateContext(spec=self.spec, sec=self.spec.section(sec_id), claims=table,
                           facts=self.facts, bib_keys=set(self.bib))


def plan(p: Project, sec_id: str) -> tuple[ClaimTable, list[Issue]]:
    """Planner -> claim table. The claims gate sends its errors back to the planner."""
    sec = p.spec.section(sec_id)
    issues: list[Issue] = []
    table = ClaimTable(section_id=sec_id, claims=[])
    for _ in range(p.spec.max_rounds):
        claims = agents.plan_claims(
            sec, design=p.spec.design, key_messages=p.inp("key_messages"), limitations=p.inp("limitations"),
            methods=p.inp("methods"), results=p.inp("results"), introduction=p.inp("introduction"), fact_reg=p.facts,
            starting_draft=p.draft(sec_id),
            library=zotero.library_listing(p.bib), wiki_index=wiki.index(p.root / "wiki"), issues=issues)
        table = ClaimTable(section_id=sec_id, approved=False, claims=claims)
        issues = blocking(check_claims(table, p.facts, set(p.bib)))
        if not issues:
            break
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


def run_section(p: Project, sec_id: str) -> str:
    """Writer -> gates -> reviewer, until clean or until the rounds run out."""
    sec = p.spec.section(sec_id)
    table = p.load_claims(sec_id)
    if table is None:
        table, _ = plan(p, sec_id)
    if blocking(check_claims(table, p.facts, set(p.bib))):
        return p.set_status(sec_id, "CLAIMS_INVALID")
    if not table.approved:
        return p.set_status(sec_id, "AWAITING_APPROVAL")

    ctx = p.ctx(sec_id, table)
    fact_sub = {fid: p.facts[fid] for c in table.claims for fid in c.fact_ids}
    pages = wiki.pages_for(p.root / "wiki", [k for c in table.claims for k in c.cite_keys])
    drafts, reviews = p.root / "drafts", p.root / "state" / "reviews"
    drafts.mkdir(parents=True, exist_ok=True)

    draft, issues = "", []
    for rnd in range(1, p.spec.max_rounds + 1):
        draft = agents.write_section(sec, design=p.spec.design, claims=table.claims, fact_reg=fact_sub,
                                     wiki_pages=pages, prev_draft=draft, issues=issues,
                                     starting_draft=p.draft(sec_id))
        (drafts / f"{sec_id}.r{rnd}.md").write_text(draft, encoding="utf-8")

        gate_issues = run_gates(draft, ctx)
        issues = blocking(gate_issues)
        if issues:
            _dump(reviews / f"{sec_id}.r{rnd}.json", {"gates": _rows(gate_issues), "review": []})
            continue                                   # never reaches the reviewer

        review = agents.review_section(sec, design=p.spec.design, methods=p.inp("methods"),
                                       results=p.inp("results"), claims=table.claims, fact_reg=fact_sub,
                                       wiki_pages=pages, draft=draft)
        _dump(reviews / f"{sec_id}.r{rnd}.json", {"gates": _rows(gate_issues), "review": _rows(review)})
        issues = blocking(review)
        if not issues:
            (drafts / f"{sec_id}.md").write_text(draft, encoding="utf-8")
            return p.set_status(sec_id, "DONE")

    _dump(reviews / f"{sec_id}.open.json", _rows(issues))   # hand over to a person; never accept silently
    return p.set_status(sec_id, "ESCALATED")


def run(p: Project, only: str | None = None) -> dict[str, str]:
    return {sec.id: run_section(p, sec.id) for sec in p.spec.sections if only in (None, sec.id)}


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
