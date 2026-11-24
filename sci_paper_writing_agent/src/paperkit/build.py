"""Build: join the sections, substitute numbers, run pandoc, write the report."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import facts
from .schemas import Issue, PaperSpec
from .validators.common import COMMENT, MARKER


def assemble(root: Path, spec: PaperSpec, fact_reg: dict) -> tuple[Path, list[Issue]]:
    """drafts/<section>.md -> build/paper.md. Numbers are substituted here and claim tags removed."""
    issues: list[Issue] = []
    parts = ["---", f"title: {json.dumps(spec.title, ensure_ascii=False)}", "---", ""]
    for sec in spec.sections:
        path = root / "drafts" / f"{sec.id}.md"
        if not path.exists():
            issues.append(Issue(gate="build", message=f"No finished draft for section '{sec.id}'"))
            continue
        text = path.read_text(encoding="utf-8")
        for fid in sorted(facts.used(text) - set(fact_reg)):
            issues.append(Issue(gate="build", message=f"{sec.id}: fact {fid} is not in facts.json"))
        text = COMMENT.sub("", facts.render(text, fact_reg))
        for m in MARKER.finditer(text):
            issues.append(Issue(gate="build", severity="warning", message=f"{sec.id}: open marker {m.group(0)}"))
        body = "\n".join(line.rstrip() for line in text.strip().splitlines())
        parts += [f"# {sec.title}", "", body, ""]
    parts += ["# References", ""]
    out = root / "build" / "paper.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out, issues


def pandoc(md_path: Path, root: Path, spec: PaperSpec) -> Path | None:
    """paper.md -> paper.docx with a reference list. Skipped when pandoc is not installed."""
    if shutil.which("pandoc") is None:
        return None
    out = md_path.with_suffix(".docx")
    cmd = ["pandoc", str(md_path), "--citeproc", "--bibliography", str(root / "refs" / "library.bib"), "-o", str(out)]
    if spec.csl:
        cmd += ["--csl", str(root / spec.csl)]
    subprocess.run(cmd, check=True)
    return out


def report(root: Path, spec: PaperSpec, status: dict[str, str], issues: list[Issue]) -> Path:
    """build/report.md: section statuses and everything left open for a person."""
    lines = [f"# Report: {spec.title}", "", "## Sections", ""]
    lines += [f"- {sec.id}: {status.get(sec.id, 'NEW')}" for sec in spec.sections]
    lines += ["", "## Open issues", ""]
    rows = [f"- [{i.severity}] {i.gate}: {i.message}" + (f" | {i.excerpt}" if i.excerpt else "") for i in issues]
    for sec in spec.sections:
        path = root / "state" / "reviews" / f"{sec.id}.open.json"
        if status.get(sec.id) == "ESCALATED" and path.exists():
            for item in json.loads(path.read_text(encoding="utf-8")):
                rows.append(f"- [escalated] {sec.id} / {item['gate']}: {item['message']}"
                            + (f" | {item['excerpt']}" if item.get("excerpt") else ""))
    lines += rows or ["- none"]
    out = root / "build" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
