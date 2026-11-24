"""Interactive start screen: check the inputs, help fill in what is missing, then run steps from a menu.

Standard library only. Every prompt goes through UI, so tests can script the answers.
"""
from __future__ import annotations

import csv
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import agents, build, dryrun, env, facts, orchestrator, preflight, zotero
from .schemas import ClaimTable, Issue
from .validators import blocking

# key -> (file, heading written at the top, True if the content is a list of bullets)
TEXT_INPUTS = {
    "methods": ("inputs/methods.md", "Methods", False),
    "results": ("inputs/results.md", "Results", False),
    "key_messages": ("inputs/key_messages.md", "Key messages", True),
    "introduction": ("inputs/introduction.md", "Introduction notes", False),
    "limitations": ("inputs/limitations.md", "Limitations and assumptions", True),
}
CONVERTIBLE = {".docx", ".odt", ".rtf", ".html", ".htm", ".tex"}
MENU = {
    "1": "Check inputs and fill in what is missing",
    "2": "Dry run on a stand-in model (no API key, no cost, your files are not changed)",
    "3": "Plan the claim table for a section        (calls the API)",
    "4": "Show and approve the claim table",
    "5": "Run writer -> gates -> reviewer            (calls the API)",
    "6": "Validate the current draft (gates only)",
    "7": "Build the paper and the report",
    "8": "Show section statuses",
    "9": "Choose the model provider and test the connection",
    "q": "Quit",
}


class Quit(Exception):
    """The user left: q, Ctrl-D or Ctrl-C."""


def open_editor(path: Path) -> bool:
    """Opens the file in $VISUAL or $EDITOR, or the first common editor found."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        editor = "notepad" if os.name == "nt" else next((e for e in ("nano", "vim", "vi") if shutil.which(e)), "")
    if not editor:
        return False
    subprocess.run([*shlex.split(editor), str(path)], check=False)
    return True


class UI:
    """All terminal input and output. Pass other callables to drive it from a test."""

    def __init__(self, ask=input, out=print, secret=getpass.getpass, edit=open_editor, color=None):
        self._ask, self.out, self._secret, self.edit = ask, out, secret, edit
        self.color = preflight.use_color() if color is None else color

    def ask(self, prompt: str, strip: bool = True) -> str:
        try:
            answer = self._ask(prompt)
        except (EOFError, KeyboardInterrupt, StopIteration):
            raise Quit from None
        return answer.strip() if strip else answer.rstrip("\r\n")

    def text(self, prompt: str, default: str = "") -> str:
        return self.ask(f"{prompt}{f' [{default}]' if default else ''}: ") or default

    def confirm(self, prompt: str, default: bool = True) -> bool:
        answer = self.ask(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").lower()
        return default if not answer else answer.startswith("y")

    def choose(self, prompt: str, options: dict[str, str], default: str = "") -> str:
        self.out(prompt)
        for key, label in options.items():
            self.out(f"  [{key}] {label}")
        while True:
            answer = self.ask(f"> [{default}] " if default else "> ").lower() or default
            if answer in options:
                return answer
            self.out(f"Type one of: {', '.join(options)}")

    def lines(self, prompt: str) -> str:
        """Free text over several lines, ended by a line that holds only a dot."""
        self.out(f"{prompt} End with a line that contains only a dot (.)")
        got = []
        while True:
            row = self.ask("", strip=False)
            if row.strip() == ".":
                return "\n".join(got)
            got.append(row)

    def secret(self, prompt: str) -> str:
        try:
            return self._secret(prompt).strip()
        except (EOFError, KeyboardInterrupt, StopIteration):
            raise Quit from None


# ------------------------------------------------------------------ importing

def clean_path(raw: str) -> Path:
    """A typed or dragged-in path: quotes, ~ and shell-escaped spaces are handled."""
    raw = raw.strip().strip("'\"")
    if os.name != "nt":
        raw = raw.replace("\\ ", " ")
    return Path(raw).expanduser()


def import_text(path: Path) -> str:
    """Text of a .md/.txt file, a PDF (PyMuPDF), or a .docx and similar (pandoc)."""
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from .ingestion.pdf_parser import parse_pdf
            pages = parse_pdf(path)
        except ImportError as exc:
            raise RuntimeError("PDF import needs PyMuPDF: pip install pymupdf") from exc
        return "\n\n".join(page["text"].strip() for page in pages)
    if suffix in CONVERTIBLE:
        if shutil.which("pandoc") is None:
            raise RuntimeError(f"{suffix} import needs pandoc on the PATH")
        done = subprocess.run(["pandoc", str(path), "-t", "gfm", "--wrap=none"],
                              capture_output=True, text=True, check=True)
        return done.stdout
    return path.read_text(encoding="utf-8-sig")


def to_bullets(text: str) -> str:
    rows = [preflight.BULLET.sub("", line).strip() for line in text.splitlines()]
    return "\n".join(f"- {row}" for row in rows if row and not row.startswith("#"))


def strip_title(text: str) -> str:
    """Drops a leading '# Heading' line so the file does not end up with two titles."""
    rows = text.strip().splitlines()
    return "\n".join(rows[1:]).strip() if rows and rows[0].startswith("# ") else text.strip()


# ------------------------------------------------------------------- fillers

def fill_text(ui: UI, root: Path, check: preflight.Check) -> None:
    rel, heading, as_list = TEXT_INPUTS[check.key]
    path = root / rel
    choice = ui.choose("How do you want to fill it in?", {
        "p": "import from a file (.md .txt .docx .pdf)",
        "t": "type them here, one per line" if as_list else "paste the text here",
        "e": "open the file in an editor",
        "s": "skip for now"}, default="s")
    if choice == "s":
        return
    if choice == "e":
        if not ui.edit(path):
            ui.out("No editor found. Set the EDITOR variable, or edit the file yourself.")
        return
    if check.ok and not ui.confirm("This replaces the current content. Continue?", False):
        return
    if choice == "p":
        try:
            body = import_text(clean_path(ui.text("Path to the file")))
        except Exception as exc:
            ui.out(f"Could not import: {exc}")
            return
    else:
        body = ui.lines("One per line." if as_list else "Paste the text.")
    body = to_bullets(body) if as_list else strip_title(body)
    if not body:
        ui.out("Nothing to save.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {heading}\n\n{body}\n", encoding="utf-8")
    ui.out(f"Saved {rel}.")


def fill_spec(ui: UI, root: Path, check: preflight.Check) -> None:
    path = root / "paper.yaml"
    if not path.is_file():
        ui.out("paper.yaml is missing. Run scaffold.py on this folder to create it.")
        return
    text = path.read_text(encoding="utf-8")
    title_line = re.search(r"(?m)^title:[ \t]*(.*)$", text)
    design_line = re.search(r"(?m)^design:[ \t]*(\w+)", text)
    if not title_line or not design_line:
        ui.out("paper.yaml has no title: or design: line to update, so it needs editing by hand.")
    else:
        current = title_line.group(1).split(" #")[0].strip().strip("'\"")
        title = ui.text("Paper title", current)
        design = ui.choose("Study design", {"o": "observational (causal wording is blocked)",
                                            "e": "experimental"}, default=design_line.group(1)[0])
        word = "observational" if design == "o" else "experimental"
        text = re.sub(r"(?m)^title:.*$", lambda m: "title: " + json.dumps(title, ensure_ascii=False), text, count=1)
        text = re.sub(r"(?m)^(design:[ \t]*)\w+", lambda m: m.group(1) + word, text, count=1)
        path.write_text(text, encoding="utf-8")
        ui.out("Saved paper.yaml.")
    ui.out("Sections, required headings and word limits are set in paper.yaml itself.")
    if ui.confirm("Open paper.yaml in an editor now?", False) and not ui.edit(path):
        ui.out("No editor found. Set the EDITOR variable, or edit the file yourself.")


def write_facts_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "text", "source"])
        writer.writeheader()
        writer.writerows(rows)


def fill_facts(ui: UI, root: Path, check: preflight.Check) -> None:
    path = root / "inputs" / "facts.csv"
    try:
        rows = preflight.read_facts_csv(path) if path.is_file() else []
    except (ValueError, csv.Error) as exc:
        ui.out(f"The current file is not readable ({exc}); it will be replaced if you add or import facts.")
        rows = []
    choice = ui.choose("How do you want to fill it in?", {
        "a": "add facts one by one",
        "i": "import a CSV with the columns id, text, source",
        "e": "open the file in an editor",
        "b": "rebuild facts/facts.json from the file as it is",
        "s": "skip for now"}, default="s")
    if choice == "s":
        return
    if choice == "a":
        real = [r for r in rows if "EXAMPLE" not in r["text"]]
        numbers = [int(m.group(1)) for r in real if (m := re.fullmatch(r"F(\d+)", r["id"]))]
        n, added = max(numbers, default=0) + 1, []
        ui.out("Type each number exactly as it should print, for example: r = 0.31, 95% CI [0.22, 0.40]")
        while True:
            text = ui.text(f"F{n} text (empty to finish)")
            if not text:
                break
            added.append({"id": f"F{n}", "text": text, "source": ui.text("   source, for example Table 2")})
            n += 1
        if not added:
            return
        write_facts_csv(path, real + added)     # the example rows go once real facts exist
    elif choice == "i":
        try:
            incoming = preflight.read_facts_csv(clean_path(ui.text("Path to the CSV")))
        except (OSError, ValueError, csv.Error) as exc:
            ui.out(f"Could not import: {exc}")
            return
        write_facts_csv(path, incoming)
    elif choice == "e" and not ui.edit(path):
        ui.out("No editor found. Set the EDITOR variable, or edit the file yourself.")
        return
    try:
        built = facts.from_csv(path, root / "facts" / "facts.json")
        ui.out(f"{len(built)} fact(s) -> facts/facts.json")
    except (OSError, ValueError, KeyError) as exc:
        ui.out(f"facts/facts.json was not rebuilt: {exc}")


def fill_bib(ui: UI, root: Path, check: preflight.Check) -> None:
    ui.out("Best: in Zotero, export the collection with Better BibTeX, tick 'Keep updated',")
    ui.out(f"and save it as {root / 'refs' / 'library.bib'}. Or copy a .bib file in now.")
    if ui.choose("What now?", {"i": "copy a .bib file in", "s": "skip for now"}, default="s") == "s":
        return
    source = clean_path(ui.text("Path to the .bib file"))
    if not source.is_file():
        ui.out(f"Could not import: no such file: {source}")
        return
    target = root / "refs" / "library.bib"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    count = len(zotero.load_bib(target))
    ui.out(f"Copied: {count} reference(s) found." if count else "Copied, but no references could be read from it.")


def save_setting(ui: UI, root: Path, name: str, value: str) -> None:
    """Writes one variable to the shared .env (kept out of git) and applies it to this run."""
    if not env.is_ignored(root):
        env.ignore(root)
        ui.out("Added .env to .gitignore so keys stay out of git.")
    env.save_env(root, name, value)
    os.environ[name] = value


def fill_key(ui: UI, root: Path, check: preflight.Check | None = None) -> None:
    try:
        providers = sorted({agents.route(kind)[0] for kind in agents.PIPELINE_AGENTS})
    except ValueError as exc:
        ui.out(f"Fix config/models.yaml first: {exc}")
        return
    ui.out("Keys are only needed for the real plan and run steps. A dry run works without them.")
    for provider in [p for p in providers if not agents.has_key(p)] or providers:
        name = agents.PROVIDERS[provider][0]
        if provider == "nvidia":
            ui.out("A free NVIDIA key: sign in at build.nvidia.com and choose Get API Key.")
        if ui.choose(f"{provider}: what now?", {"k": f"enter {name} now (hidden; saved to the .env next to setup.sh)",
                                                "s": "skip for now"}, default="s") == "s":
            continue
        key = ui.secret(f"{name}: ")
        if not key:
            ui.out("Nothing entered.")
            continue
        save_setting(ui, root, name, key)
        ui.out("Saved to .env.")


FILLERS = {"spec": fill_spec, "title": fill_spec, "facts": fill_facts, "bib": fill_bib, "api_key": fill_key,
           **{key: fill_text for key in TEXT_INPUTS}}


def fill(ui: UI, root: Path, check: preflight.Check) -> None:
    """Asks about one input, then shows its new status."""
    ui.out("")
    ui.out(f"{check.label}  ({check.path}): {check.detail}")
    ui.out(f"  Needs: {check.hint}")
    if check.key not in FILLERS:
        ui.out("  Add the files to that folder yourself; there is nothing to type here.")
        return
    FILLERS[check.key](ui, root, check)
    after = next((c for c in preflight.check_inputs(root) if c.key == check.key), None)
    if after:
        ui.out(preflight.line(after, ui.color))


def guided(ui: UI, root: Path, levels: tuple[str, ...]) -> None:
    asked_spec = False
    for check in preflight.check_inputs(root):
        if check.level not in levels or check.ok:
            continue
        if check.key in ("spec", "title"):       # both are answered by the same questions
            if asked_spec:
                continue
            asked_spec = True
        fill(ui, root, check)


# -------------------------------------------------------------- menu actions

def show_issues(ui: UI, issues: list[Issue]) -> None:
    for i in issues:
        ui.out(f"  [{i.severity}] {i.gate}: {i.message}" + (f" | {i.excerpt}" if i.excerpt else ""))
    if not issues:
        ui.out("  ok")


def show_claims(ui: UI, table: ClaimTable) -> None:
    ui.out(f"Claim table for '{table.section_id}' ({'approved' if table.approved else 'not approved'})")
    for c in table.claims:
        ui.out(f"  {c.id:<4}{c.category:<12}{c.text}")
        extra = [f"facts: {', '.join(c.fact_ids)}" if c.fact_ids else "",
                 f"cites: {', '.join(c.cite_keys)}" if c.cite_keys else "",
                 f"assumes: {'; '.join(c.assumptions)}" if c.assumptions else ""]
        if any(extra):
            ui.out("      " + "   ".join(e for e in extra if e))


def _project(ui: UI, root: Path) -> orchestrator.Project | None:
    try:
        return orchestrator.Project(root)
    except Exception as exc:
        ui.out(f"paper.yaml cannot be loaded: {' '.join(str(exc).split())[:120]}")
        return None


def _section(ui: UI, p: orchestrator.Project) -> str:
    ids = [sec.id for sec in p.spec.sections]
    if len(ids) == 1:
        return ids[0]
    return ids[int(ui.choose("Which section?", {str(n): sec_id for n, sec_id in enumerate(ids, 1)})) - 1]


def _inputs_ready(ui: UI, root: Path) -> bool:
    gaps = preflight.missing(preflight.check_inputs(root))
    for check in gaps:
        ui.out(preflight.line(check, ui.color))
    if gaps:
        ui.out("Required inputs are missing, so the model is not called. Use menu 1 to fill them in.")
    return not gaps


def show_routes(ui: UI) -> None:
    for kind in agents.PIPELINE_AGENTS:
        provider, model = agents.route(kind)
        ui.out(f"  {kind:<10}{provider:<11}{model}" + ("" if agents.has_key(provider) else "   (no key set)"))


def _confirm_api(ui: UI, *kinds: str) -> bool:
    routes = {kind: agents.route(kind) for kind in kinds}
    for provider in sorted({provider for provider, _ in routes.values()}):
        if not agents.has_key(provider):
            ui.out(f"No key is set for {provider}, so this call will fail. Menu 9 can save one.")
    used = "; ".join(f"{kind}: {provider} {model}" for kind, (provider, model) in routes.items())
    return ui.confirm(f"This calls the model API ({used}). Continue?", False)


def act_inputs(ui: UI, root: Path) -> None:
    checks = preflight.check_inputs(root)
    ui.out(preflight.render(checks, ui.color))
    if any(not c.ok and c.level != "optional" for c in checks):
        guided(ui, root, ("required", "recommended"))
        return
    fillable = [c for c in checks if c.key in FILLERS]
    options = {str(n): c.path if c.key != "title" else "paper title" for n, c in enumerate(fillable, 1)}
    choice = ui.choose("Everything needed is there. Change one anyway?", {**options, "b": "back"}, default="b")
    if choice != "b":
        fill(ui, root, fillable[int(choice) - 1])


def act_dry_run(ui: UI, root: Path) -> None:
    if _project(ui, root) is not None:
        ui.out(dryrun.summary(dryrun.dry_run(root)))


def act_plan(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is None or not _inputs_ready(ui, root):
        return
    sec_id = _section(ui, p)
    if p.load_claims(sec_id) and not ui.confirm("A claim table exists and will be replaced. Continue?", False):
        return
    if not _confirm_api(ui, "planner"):
        return
    table, issues = orchestrator.plan(p, sec_id)
    show_claims(ui, table)
    if issues:
        show_issues(ui, issues)
    ui.out(f"Read it, correct {p.claims_path(sec_id)} if needed, then approve it with menu 4.")


def act_approve(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is None:
        return
    sec_id = _section(ui, p)
    table = p.load_claims(sec_id)
    if table is None:
        ui.out("There is no claim table yet. Plan it first (menu 3).")
        return
    show_claims(ui, table)
    if table.approved or not ui.confirm("Approve this table?", False):
        return
    issues = orchestrator.approve(p, sec_id)
    if issues:
        show_issues(ui, issues)
    else:
        ui.out("Approved.")


def act_run(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is None or not _inputs_ready(ui, root):
        return
    sec_id = _section(ui, p)
    table = p.load_claims(sec_id)
    if table is None or not table.approved:
        ui.out("The claim table must be planned (menu 3) and approved (menu 4) first.")
        return
    if not _confirm_api(ui, "writer", "reviewer"):
        return
    status = orchestrator.run_section(p, sec_id)
    ui.out(f"{sec_id}: {status}")
    if status == "DONE":
        ui.out(f"Draft: {p.root / 'drafts' / f'{sec_id}.md'}")
    elif status == "ESCALATED":
        ui.out(f"Open issues: {p.root / 'state' / 'reviews' / f'{sec_id}.open.json'}")


def act_validate(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is not None:
        show_issues(ui, orchestrator.validate(p, _section(ui, p)))


def act_build(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is None:
        return
    paper, issues = build.assemble(root, p.spec, p.facts)
    if not blocking(issues):
        docx = build.pandoc(paper, root, p.spec)
        ui.out(f"{paper}" + (f"\n{docx}" if docx else "\npandoc not found: .docx skipped"))
    ui.out(str(build.report(root, p.spec, p.status(), issues)))
    show_issues(ui, issues)


def act_status(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is not None:
        status = p.status()
        for sec in p.spec.sections:
            ui.out(f"  {sec.id}: {status.get(sec.id, 'NEW')}")


def show_ping(ui: UI) -> bool:
    rows = agents.ping_all()
    for kinds, provider, model, result in rows:
        ui.out(f"  {provider:<11}{model}  ({kinds}): {result}")
    return all(result == "ok" for *_, result in rows)


def act_models(ui: UI, root: Path) -> None:
    """Pick the provider and model, save any missing key, and send one small test request."""
    agents.configure(root)
    ui.out("Current routing (config/models.yaml, then .env):")
    show_routes(ui)
    choice = ui.choose("Provider for the agents", {
        "a": "anthropic",
        "n": "nvidia (free hosted endpoints at build.nvidia.com; rate limited)",
        "k": "keep as it is"}, default="k")
    if choice != "k":
        provider = "anthropic" if choice == "a" else "nvidia"
        model = ui.text("Model ID", agents.PROVIDERS[provider][1])
        save_setting(ui, root, "PAPERKIT_PROVIDER", provider)
        save_setting(ui, root, "PAPERKIT_MODEL", model)
        ui.out("Saved to .env. An agent with its own entry in config/models.yaml keeps that entry:")
        show_routes(ui)
    if not all(agents.has_key(agents.route(kind)[0]) for kind in agents.PIPELINE_AGENTS):
        fill_key(ui, root)
    if ui.confirm("Send one small test request to each model now?", False):
        ui.out("All models answered." if show_ping(ui) else "At least one model did not answer: see above.")


ACTIONS = {"1": act_inputs, "2": act_dry_run, "3": act_plan, "4": act_approve,
           "5": act_run, "6": act_validate, "7": act_build, "8": act_status, "9": act_models}


def menu(ui: UI, root: Path) -> int:
    while True:
        ui.out("")
        choice = ui.choose("What next?", MENU)
        if choice == "q":
            return 0
        try:
            ACTIONS[choice](ui, root)
        except Quit:
            raise
        except Exception as exc:      # a failed step must not close the screen
            ui.out(f"That step failed: {type(exc).__name__}: {' '.join(str(exc).split())[:300]}")


def start(root: str | Path, ui: UI | None = None) -> int:
    """Checklist first, then guided fill-in for whatever is missing, then the menu."""
    root = Path(root)
    if not (root / "paper.yaml").exists() and not (root / "inputs").is_dir():
        print(f"{root.resolve()} is not a paperkit project. Run scaffold.py first, or pass --root.")
        return 2
    interactive = ui is not None or (sys.stdin.isatty() and sys.stdout.isatty())
    ui = ui or UI()
    checks = preflight.check_inputs(root)
    ui.out(preflight.render(checks, ui.color))
    if not interactive:
        ui.out("No terminal is attached, so nothing was asked. Run `paperkit start` in a terminal.")
        return 1 if preflight.missing(checks) else 0
    try:
        gaps = preflight.missing(checks)
        if gaps and ui.confirm(f"\n{len(gaps)} required input(s) are not ready. Fill them in now?", True):
            guided(ui, root, ("required",))
        extras = preflight.missing(preflight.check_inputs(root), "recommended")
        if extras and ui.confirm(f"\n{len(extras)} recommended item(s) are open "
                                 f"({', '.join(c.label.lower() for c in extras)}). Set them up now?", False):
            guided(ui, root, ("recommended",))
        return menu(ui, root)
    except Quit:
        ui.out("\nBye.")
        return 0
