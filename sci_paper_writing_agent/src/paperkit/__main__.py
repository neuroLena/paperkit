"""CLI: python -m paperkit <command>, or paperkit <command> after pip install -e .

With no command it opens the interactive start screen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import agents, build, dryrun, env, evidence, extract, facts, orchestrator, preflight, wiki, wizard
from .ingestion import rules_ingest
from .schemas import Issue
from .validators import blocking


def _show(issues: list[Issue], as_json: bool = False) -> int:
    """Prints the issues and returns the exit code: 1 if any are blocking."""
    if as_json:
        print(json.dumps([i.model_dump() for i in issues], ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(f"[{i.severity}] {i.gate}: {i.message}" + (f" | {i.excerpt}" if i.excerpt else ""))
        if not issues:
            print("ok")
    return 1 if blocking(issues) else 0


def _say(text: str = "") -> None:
    print(text, flush=True)                # flushed: each stage shows at once, also when the output is piped


def _inputs_ready(root: Path, force: bool) -> bool:
    """The model is not called while a required input is missing, unless --force is given."""
    gaps = preflight.missing(preflight.check_inputs(root))
    if not gaps or force:
        return True
    print("Required inputs are missing:")
    for check in gaps:
        print(preflight.line(check))
    print("Run `paperkit start` to fill them in, or repeat the command with --force.")
    return False


def find_project(root: Path) -> Path:
    """The project folder: root itself, or the one folder directly below it that holds paper.yaml.

    This lets `paperkit start` run from the repository folder, next to setup.sh.
    """
    if (root / "paper.yaml").is_file() or not root.is_dir():
        return root
    found = sorted(path.parent for path in root.glob("*/paper.yaml"))
    return found[0] if len(found) == 1 else root


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paperkit")
    ap.add_argument("--root", default=".", help="project folder that holds paper.yaml (or the folder above it)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="interactive checklist and menu (the default command)")
    sub.add_parser("check", help="print the input checklist; exit code 1 if a required input is missing")
    dry = sub.add_parser("dry-run", help="run every step on a stand-in model, in a scratch copy, with no API call")
    dry.add_argument("section", nargs="?")
    sub.add_parser("facts", help="inputs/facts.csv -> facts/facts.json")
    sub.add_parser("status", help="show section statuses")
    sub.add_parser("build", help="build build/paper.md, the .docx and the report")
    sub.add_parser("wiki-lint", help="check the wiki pages")
    sub.add_parser("ping", help="show which model each agent uses and send each one a small test request")
    ext = sub.add_parser("extract", help="draft facts.csv and key_messages.md from the Results section (calls the model)")
    ext.add_argument("what", nargs="?", choices=["all", "facts", "key-messages"], default="all")
    ext.add_argument("--force", action="store_true", help="replace the file even if it already has real content")
    rul = sub.add_parser("rules", help="writing guides in .writing_guides/ -> rules for the writer and reviewer")
    rul.add_argument("action", choices=["extract", "check", "list", "approve", "reject", "restore"],
                     help="extract and check call the model; check drops repeated rules and flags contradictions; "
                          "approve with no ids asks about each rule in turn")
    rul.add_argument("ids", nargs="*", help="rule ids such as R3 R7 (approve, reject, restore)")
    rul.add_argument("--all", action="store_true", help="approve every candidate")
    rul.add_argument("--fresh", action="store_true", help="ask the model again instead of using saved answers")
    evi = sub.add_parser("evidence", help="search the literature for a section's claims: support, contradiction, "
                                          "other interpretations")
    evi.add_argument("action", choices=["search", "list", "review", "accept", "reject", "apply"],
                     help="search calls the model and Semantic Scholar; review asks about each suggestion in turn")
    evi.add_argument("section", nargs="?", help="may be left out when paper.yaml has one section")
    evi.add_argument("ids", nargs="*", help="suggestion ids such as E2 A1, for accept and reject")
    evi.add_argument("--fresh", action="store_true", help="search and ask again instead of using saved answers")
    evi.add_argument("--add-to-library", action="store_true",
                     help="append accepted papers to refs/library.bib (only if Zotero does not write that file)")
    plan = sub.add_parser("plan", help="build the claim table")
    plan.add_argument("section")
    plan.add_argument("--force", action="store_true", help="call the model even if required inputs are missing")
    sub.add_parser("approve", help="approve the claim table").add_argument("section")
    run = sub.add_parser("run", help="writer -> gates -> reviewer")
    run.add_argument("section", nargs="?")
    run.add_argument("--force", action="store_true", help="call the model even if required inputs are missing")
    val = sub.add_parser("validate", help="gates only; exit code 1 on blocking issues")
    val.add_argument("section")
    val.add_argument("--file", help="check a specific draft file")
    val.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = find_project(Path(args.root))
    cmd = args.cmd or "start"

    env.load_env(root)                                   # the shared .env one folder up; never overrides the shell
    try:
        agents.configure(root)                           # config/models.yaml: provider and model per agent
        for kind in agents.PIPELINE_AGENTS:
            agents.route(kind)
    except (ValueError, OSError) as exc:
        if (cmd in ("plan", "run", "ping", "extract") or (cmd == "rules" and args.action in ("extract", "check"))
                or (cmd == "evidence" and args.action == "search")):
            print(f"Model configuration is not valid: {exc}")
            return 2

    if cmd == "start":
        return wizard.start(root)
    if cmd == "check":
        checks = preflight.check_inputs(root)
        print(preflight.render(checks, preflight.use_color()))
        return 1 if preflight.missing(checks) else 0
    if cmd == "facts":
        made = facts.from_csv(root / "inputs" / "facts.csv", root / "facts" / "facts.json")
        print(f"{len(made)} facts -> facts/facts.json")
        return 0
    if cmd == "ping":
        rows = agents.ping_all()
        for kinds, provider, model, result in rows:
            print(f"{provider:<11}{model}  ({kinds}): {result}")
        return 0 if all(result == "ok" for *_, result in rows) else 1
    if cmd == "extract":
        return extract.run(root, args.what, args.force)
    if cmd == "rules":
        return rules_ingest.run(root, args.action, args.ids, args.all, args.fresh, out=_say)
    if cmd == "dry-run":
        result = dryrun.dry_run(root, args.section)
        print(dryrun.summary(result))
        return 0 if dryrun.passed(result) else 1

    p = orchestrator.Project(root)
    if cmd == "evidence":
        names = [sec.id for sec in p.spec.sections]
        section, ids = args.section, list(args.ids)
        if section not in names and len(names) == 1:       # one section: its name may be left out
            section, ids = names[0], ([section] if section else []) + ids
        if section not in names:
            print(f"Name the section: paperkit evidence {args.action} <section>, one of: {', '.join(names)}")
            return 1
        return evidence.run(root, args.action, section, ids, args.fresh, args.add_to_library, out=_say)
    if cmd == "status":
        status = p.status()
        for sec in p.spec.sections:
            print(f"{sec.id}: {status.get(sec.id, 'NEW')}")
        return 0
    if cmd == "plan":
        if not _inputs_ready(root, args.force):
            return 1
        table, issues = orchestrator.plan(p, args.section, _say)
        print(f"{len(table.claims)} claims -> {p.claims_path(args.section)}")
        return _show(issues)
    if cmd == "approve":
        return _show(orchestrator.approve(p, args.section))
    if cmd == "run":
        if not _inputs_ready(root, args.force):
            return 1
        result = orchestrator.run(p, args.section, _say)
        for sec_id, status in result.items():
            print(f"{sec_id}: {status}")
        return 0 if all(s == "DONE" for s in result.values()) else 1
    if cmd == "validate":
        return _show(orchestrator.validate(p, args.section, Path(args.file) if args.file else None), args.json)
    if cmd == "wiki-lint":
        return _show(wiki.lint(root / "wiki", set(p.bib)))
    if cmd == "build":
        md, issues = build.assemble(root, p.spec, p.facts)
        if not blocking(issues):
            docx = build.pandoc(md, root, p.spec)
            print(f"{md}" + (f"\n{docx}" if docx else "\npandoc not found: .docx skipped"))
        print(build.report(root, p.spec, p.status(), issues))
        return _show(issues)
    return 2


if __name__ == "__main__":
    sys.exit(main())
