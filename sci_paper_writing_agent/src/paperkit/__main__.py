"""CLI: python -m paperkit <command>, or paperkit <command> after pip install -e .

With no command it opens the interactive start screen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import agents, build, dryrun, env, facts, orchestrator, preflight, wiki, wizard
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
        if cmd in ("plan", "run", "ping"):               # the other commands do not call a model
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
    if cmd == "dry-run":
        result = dryrun.dry_run(root, args.section)
        print(dryrun.summary(result))
        return 0 if dryrun.passed(result) else 1

    p = orchestrator.Project(root)
    if cmd == "status":
        status = p.status()
        for sec in p.spec.sections:
            print(f"{sec.id}: {status.get(sec.id, 'NEW')}")
        return 0
    if cmd == "plan":
        if not _inputs_ready(root, args.force):
            return 1
        table, issues = orchestrator.plan(p, args.section)
        print(f"{len(table.claims)} claims -> {p.claims_path(args.section)}")
        return _show(issues)
    if cmd == "approve":
        return _show(orchestrator.approve(p, args.section))
    if cmd == "run":
        if not _inputs_ready(root, args.force):
            return 1
        result = orchestrator.run(p, args.section)
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
