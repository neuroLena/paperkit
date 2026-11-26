"""Build: join the sections, substitute numbers, run pandoc, write the report."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import facts, shorten
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


def latest_draft(root: Path, sec_id: str) -> Path | None:
    """The finished draft of a section, or the draft of its last round if it never finished."""
    final = root / "drafts" / f"{sec_id}.md"
    if final.exists():
        return final
    rounds = [(int(m.group(1)), f) for f in (root / "drafts").glob(f"{sec_id}.r*.md")
              if (m := re.fullmatch(rf"{re.escape(sec_id)}\.r(\d+)", f.stem))]
    return max(rounds)[1] if rounds else None


def where_to_shorten(root: Path, spec: PaperSpec) -> list[str]:
    """Report lines for every section whose latest draft is over its word limit. Counting only, no model."""
    lines: list[str] = []
    for sec in spec.sections:
        path = latest_draft(root, sec.id)
        found = shorten.analyse(path.read_text(encoding="utf-8"), sec.max_words) if path else None
        if not found:
            continue
        try:
            table = json.loads((root / "state" / "claims" / f"{sec.id}.json").read_text(encoding="utf-8"))
            claims = len(table.get("claims") or [])
        except (OSError, ValueError, AttributeError):
            claims = 0
        own = root / "inputs" / f"{sec.id}_draft.md"
        text = own.read_text(encoding="utf-8") if own.is_file() else ""
        lines += [""] + shorten.report_lines(sec.id, path.relative_to(root).as_posix(), found, claims,
                                             shorten.kept_words(text), shorten.own_words(text))
    return lines


def report(root: Path, spec: PaperSpec, status: dict[str, str], issues: list[Issue]) -> Path:
    """build/report.md: section statuses, everything left open for a person, and where to shorten a long draft."""
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
    lines += where_to_shorten(root, spec)
    out = root / "build" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
