"""Dry run: the whole pipeline on a stand-in model, in a scratch copy of the project.

It calls no API and costs nothing. The stand-in writes fixed placeholder sentences, so the output
is not a paper. What it shows is whether your inputs load, your claim tables validate, and every
step from planning to the build runs. The project's own state, drafts and build are never touched:
everything happens in .cache/dryrun/.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from . import agents, build, orchestrator
from .schemas import Claim, ClaimList, Draft, Review, WikiPage

SCRATCH = Path(".cache") / "dryrun"
COPIED = ["inputs", "facts", "refs", "wiki"]
ROTATION = ["OBSERVED", "INFERRED", "ASSUMED", "SPECULATIVE"]
SENTENCES = {
    "OBSERVED": "Dry run: we observed {facts}",
    "INFERRED": "Dry run: this suggests an interpretation that the real writer will supply",
    "ASSUMED": "Dry run: this assumes a premise that was not tested",
    "SPECULATIVE": "Dry run: one possibility is that later work may clarify this",
}


def _block(user: str, name: str) -> str:
    """Body of one <name>...</name> block of the prompt that agents.py builds."""
    found = re.search(rf"<{name}>\n(.*?)\n</{name}>", user, re.S)
    return found.group(1) if found else ""


def _claims(user: str) -> ClaimList:
    section = json.loads(_block(user, "section"))
    fact_ids = list(json.loads(_block(user, "facts_registry") or "{}"))
    keys = re.findall(r"(?m)^- (\S+): ", _block(user, "library"))
    count = max(len(section.get("required_headings") or []), 3)
    claims = []
    for i in range(count):
        category = ROTATION[i % len(ROTATION)]
        if category == "OBSERVED" and not fact_ids:
            category = "INFERRED"
        claims.append(Claim(
            id=f"C{i + 1}", text=f"Dry-run {category.lower()} claim.", category=category,
            fact_ids=fact_ids[:2] if category == "OBSERVED" else [],
            cite_keys=keys[:1] if category == "INFERRED" else []))
    return ClaimList(claims=claims)


def _paragraph(claim: dict) -> str:
    facts = " and ".join("{{%s}}" % fid for fid in claim.get("fact_ids", []))
    body = SENTENCES[claim["category"]].format(facts=facts or "the stated result")
    if facts and claim["category"] != "OBSERVED":
        body += f", given {facts}"
    cites = "; ".join(f"@{key}" for key in claim.get("cite_keys", []))
    return f"{body}{f' [{cites}]' if cites else ''}. <!-- {claim['id']} -->"


def _draft(user: str) -> Draft:
    section = json.loads(_block(user, "section"))
    claims = json.loads(_block(user, "claims"))
    headings = section.get("required_headings") or []
    if not headings:
        return Draft(markdown="\n\n".join(_paragraph(c) for c in claims) + "\n")
    per = max(1, math.ceil(len(claims) / len(headings)))
    parts = []
    for i, heading in enumerate(headings):
        chunk = claims[i * per:(i + 1) * per] if i < len(headings) - 1 else claims[i * per:]
        parts.append(f"## {heading}")
        parts += [_paragraph(c) for c in chunk]
    return Draft(markdown="\n\n".join(parts) + "\n")


def stand_in(system: str, user: str, schema):
    """Replaces agents.call_llm. Answers every agent with schema-valid placeholder output."""
    if schema is ClaimList:
        return _claims(user)
    if schema is Draft:
        return _draft(user)
    if schema is Review:
        return Review(issues=[])
    if schema is WikiPage:
        key = _block(user, "citation_key") or "source"
        return WikiPage(markdown=f"# {key}\n\n## Question\n\n## Design and sample\n\n## Key findings\n\n"
                                 "## Quotes\n\n## Limitations\n")
    raise TypeError(f"The stand-in model has no answer for {schema.__name__}")


def dry_run(root: str | Path, only: str | None = None) -> dict:
    """Copies the inputs to .cache/dryrun/ and runs plan -> approve -> run -> build there."""
    root = Path(root)
    scratch = root / SCRATCH
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    shutil.copy2(root / "paper.yaml", scratch / "paper.yaml")
    for name in COPIED:
        if (root / name).is_dir():
            shutil.copytree(root / name, scratch / name)
    if (root / "state" / "claims").is_dir():        # your real claim tables are exercised if they exist
        shutil.copytree(root / "state" / "claims", scratch / "state" / "claims")

    saved = agents.LLM, agents.LOG_DIR
    agents.LLM = stand_in
    result = {"scratch": scratch, "sections": {}, "issues": {}, "planned": [], "paper": None, "build_issues": []}
    try:
        p = orchestrator.Project(scratch)
        result["facts"], result["references"] = len(p.facts), len(p.bib)
        for sec in p.spec.sections:
            if only not in (None, sec.id):
                continue
            if p.load_claims(sec.id) is None:
                orchestrator.plan(p, sec.id)
                result["planned"].append(sec.id)
            problems = orchestrator.approve(p, sec.id)
            status = p.set_status(sec.id, "CLAIMS_INVALID") if problems else orchestrator.run_section(p, sec.id)
            result["sections"][sec.id] = status
            open_file = scratch / "state" / "reviews" / f"{sec.id}.open.json"
            if problems:
                result["issues"][sec.id] = [f"[{i.gate}] {i.message}" for i in problems]
            elif status == "ESCALATED" and open_file.is_file():
                rows = json.loads(open_file.read_text(encoding="utf-8"))
                result["issues"][sec.id] = [f"[{r['gate']}] {r['message']}" for r in rows]
        paper, build_issues = build.assemble(scratch, p.spec, p.facts)
        result["paper"] = paper
        skipped = {sec.id for sec in p.spec.sections} - set(result["sections"])
        result["build_issues"] = [f"[{i.severity}] {i.message}" for i in build_issues
                                  if not any(f"'{sec_id}'" in i.message for sec_id in skipped)]
    finally:
        agents.LLM, agents.LOG_DIR = saved
    return result


def passed(result: dict) -> bool:
    return bool(result["sections"]) and all(status == "DONE" for status in result["sections"].values())


def summary(result: dict) -> str:
    rows = ["Dry run on a stand-in model (no API call, your project files were not changed)",
            f"  loaded {result.get('facts', 0)} fact(s) and {result.get('references', 0)} reference(s)"]
    for sec_id, status in result["sections"].items():
        source = "stand-in claim table" if sec_id in result["planned"] else "your claim table"
        rows.append(f"  {sec_id}: {status}  ({source})")
        rows += [f"      {text}" for text in result["issues"].get(sec_id, [])[:8]]
    rows += [f"  build: {text}" for text in result["build_issues"]]
    rows.append(f"  scratch copy: {result['scratch']}")
    if result["paper"]:
        rows.append(f"  assembled text: {result['paper']}")
    rows.append("Every step ran." if passed(result) else "Something did not pass: see the lines above.")
    return "\n".join(rows)
