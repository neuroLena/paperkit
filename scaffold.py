#!/usr/bin/env python3
"""Creates the paperkit scaffold: the folder structure and the minimal content of every file.

    python scaffold.py my-paper          # create the project in the folder my-paper
    python scaffold.py my-paper --update-code   # refresh src/ and tests/ in an existing project

The folder that holds this script is the one git repository. Next to the project, in that folder,
the scaffold also creates .env (all keys, mode 600), .env.example and .gitignore. They are never
created inside the project, and the project has no .git folder of its own.

Needs only Python 3.10+. Existing files are never overwritten, with one exception:
--update-code rewrites files under src/ and tests/ that differ from this scaffold.
Inputs, state, drafts and paper.yaml are never touched.
The content of each file is below, in the FILES dictionary, under its own path.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Folders that fill up while the pipeline runs
EMPTY_DIRS = ["inputs/tables", "state/claims", "state/reviews", "drafts"]

FILES: dict[str, str] = {}



# ----------------------------------------------------------------------------
# README.md
# ----------------------------------------------------------------------------
FILES['README.md'] = r'''
# paperkit

A framework for writing a paper from finished results with AI agents.
Code decides the order of steps; agents are called only for single steps, each with a clean context.

## Run first

Run `bash setup.sh` in the repository folder, the one above this project. It creates this project,
the shared `.env`, the virtual environment (`.venv`, next to `setup.sh`), installs the packages and runs the tests.

```
paperkit/                  <- the one git repository
  .git/  .gitignore  .env  .env.example  .venv/
  setup.sh  scaffold.py  publish.sh
  sci_paper_writing_agent/ <- this project
```

## Install

```bash
# bash setup.sh does all of this. By hand, from the project folder:
python -m venv ../.venv && source ../.venv/bin/activate
pip install -e ".[dev]"             # also installs python-dotenv, which reads ../.env
pytest                              # runs without a key, on a stand-in model
```

## Keys

Every key lives in one `.env` file in the repository folder, next to `setup.sh`, one folder above this
project. It is never inside the project. `.env.example` beside it is the public template.
`paperkit` loads it with python-dotenv (`NVIDIA_API_KEY`, `ANTHROPIC_API_KEY`, `PAPERKIT_PROVIDER`,
`PAPERKIT_MODEL`), and `publish.sh` reads `GITHUB_USER`, `GITHUB_TOKEN` and `VISIBILITY` from the same file.
A value already set in the shell wins over the file. `PAPERKIT_ENV_FILE=/path/to/.env` points paperkit at another file.

## Start here

`paperkit start` (or just `paperkit`) opens a checklist of the required inputs, helps fill in the
missing ones, and then offers every step from a menu. `paperkit check` prints the same checklist
without asking anything. `paperkit dry-run` runs every step on a stand-in model in a scratch copy
(`.cache/dryrun/`): no API key, no cost, and the project's own files are not changed.

`plan` and `run` refuse to call the model while a required input is missing; `--force` overrides that.

## Git

The repository is the folder above this one, the one that holds `setup.sh`, `scaffold.py` and
`publish.sh`. This project is tracked inside it as ordinary files, so it has no `.git` folder of its own.
`bash publish.sh "what changed"` in that folder commits everything and pushes it to GitHub.

The one `.gitignore` is in that folder too. It keeps keys (`.env`), the virtual environment, caches,
model call logs (`state/log/`), `build/` and your source PDFs (`.papers/`) out of git. Inputs, claim
tables, drafts and reviews are tracked, so every round leaves a history you can diff.

## Models

Each agent calls the provider and model set in `config/models.yaml`. `PAPERKIT_PROVIDER` and
`PAPERKIT_MODEL` in `.env` change the default without editing that file. Two providers are built in:
`anthropic` (key in `ANTHROPIC_API_KEY`) and `nvidia` (key in `NVIDIA_API_KEY`: the free, rate-limited
endpoints at build.nvidia.com, or a local NIM through `NVIDIA_BASE_URL`).

`paperkit ping` shows which model each agent uses and sends each one a small test request.
Menu 9 on the start screen does the same and can save the provider, the model and the key.

## Workflow

1. Fill in `paper.yaml` and the files in `inputs/`.
2. Set up Better BibTeX auto-export from Zotero to `refs/library.bib`.
3. `paperkit facts` builds `facts/facts.json` from `inputs/facts.csv`. With no tables, `paperkit extract` drafts `inputs/facts.csv`
   and `inputs/key_messages.md` from the Results section (only while they are empty or still the scaffold's examples;
   `--force` replaces them). Every fact must appear word for word in Results or Methods. Read both files afterwards.
4. `paperkit plan introduction` (and `paperkit plan discussion`) builds the claim table in `state/claims/<section>.json`.
5. Read and correct the table, then run `paperkit approve introduction`. This is the one required manual check for each section.
6. `paperkit run introduction` runs the writer -> gates -> reviewer loop and writes `drafts/introduction.md`.
7. `paperkit build` produces `build/paper.md`, `build/paper.docx` and `build/report.md`.

`paperkit validate discussion` runs the gates only and exits with code 1 on blocking issues,
so it can be used in a hook or in CI. `paperkit status` shows the section statuses.

## Draft rules that code checks

- The required `## ...` headings from `paper.yaml`, in the given order.
- Every paragraph ends with a claim tag: `<!-- C3 -->` or `<!-- C3,C4 -->`.
- No digits in the text. Numbers are written as `{{F12}}` and substituted from `facts/facts.json` at build time.
- Citations only as `[@key]`, and the key must be in `refs/library.bib` and in the claim table.
- Wording matches the claim category: OBSERVED, INFERRED, ASSUMED, SPECULATIVE.

## Where to change things

- Provider and model per agent: `config/models.yaml`, or `PAPERKIT_PROVIDER` and `PAPERKIT_MODEL`.
- Prompts: `src/paperkit/agents.py`.
- Banned word lists: `src/paperkit/validators/language.py`.
- A new gate: a module with a `check(draft, ctx)` function, plus one line in `validators/__init__.py`.


'''

# ----------------------------------------------------------------------------
# pyproject.toml
# ----------------------------------------------------------------------------
FILES['pyproject.toml'] = r'''
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "paperkit"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pydantic>=2", "pyyaml>=6", "anthropic", "python-dotenv>=1.0"]

[project.optional-dependencies]
zotero = ["pyzotero"]
dev = ["pytest>=7"]

[project.scripts]
paperkit = "paperkit.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
'''

# ----------------------------------------------------------------------------
# paper.yaml
# ----------------------------------------------------------------------------
FILES['paper.yaml'] = r'''
# Paper specification. Only code reads it; the agent never changes it.
title: "Working title"
design: observational        # observational | experimental; observational bans causal wording
max_rounds: 3                # writer -> gates -> reviewer rounds before escalating to a person
csl: null                    # path to the journal's .csl file for pandoc, if needed
number_whitelist: []         # tokens with digits that are allowed in the text: ["COVID-19", "3D"]
term_whitelist: []           # terms the language gate should leave alone: ["main effect of"]

sections:
  - id: introduction
    title: Introduction
    max_words: 700
    required_headings:       # "## ..." headings, strictly in this order
      - Background
      - Knowledge gap
      - Aim
  - id: discussion
    title: Discussion
    max_words: 1200
    required_headings:       # "## ..." headings, strictly in this order
      - Principal findings
      - Comparison with prior work
      - Limitations
      - Conclusion
'''

# ----------------------------------------------------------------------------
# inputs/methods.md
# ----------------------------------------------------------------------------
FILES['inputs/methods.md'] = r'''
# Methods

Paste the full Methods section here, as it appears in the manuscript.
'''

# ----------------------------------------------------------------------------
# inputs/results.md
# ----------------------------------------------------------------------------
FILES['inputs/results.md'] = r'''
# Results

Paste the full Results section here: text, tables and figure captions.
'''

# ----------------------------------------------------------------------------
# inputs/key_messages.md
# ----------------------------------------------------------------------------
FILES['inputs/key_messages.md'] = r'''
# Key messages

Three to five points the paper must get across. One per line.

- 
'''

# ----------------------------------------------------------------------------
# inputs/limitations.md
# ----------------------------------------------------------------------------
FILES['inputs/limitations.md'] = r'''
# Limitations and assumptions

Known limitations and assumptions: design, sample, missing data, unmeasured factors,
and which model assumptions were tested and which were not.

- 
'''

# ----------------------------------------------------------------------------
# inputs/introduction.md
# ----------------------------------------------------------------------------
FILES['inputs/introduction.md'] = r'''
# Introduction notes

Your notes for the Introduction: what is known, what is not known, and what this study set out to do.

## Background

- 

## Knowledge gap

- 

## Aim

- 
'''

# ----------------------------------------------------------------------------
# inputs/facts.csv
# ----------------------------------------------------------------------------
FILES['inputs/facts.csv'] = r'''
id,text,source
F1,"EXAMPLE r = 0.00, 95% CI [0.00, 0.00]",Table 0
F2,EXAMPLE n = 000,Methods 0.0
'''

# ----------------------------------------------------------------------------
# facts/facts.json
# ----------------------------------------------------------------------------
FILES['facts/facts.json'] = r'''
{}
'''

# ----------------------------------------------------------------------------
# refs/library.bib
# ----------------------------------------------------------------------------
FILES['refs/library.bib'] = r'''
% Better BibTeX auto-export from Zotero writes here. Do not edit by hand or by agent.
'''

# ----------------------------------------------------------------------------
# wiki/index.md
# ----------------------------------------------------------------------------
FILES['wiki/index.md'] = r'''
# Wiki index

One line per page: `- [[citekey]]: what the source is about`.

'''

# ----------------------------------------------------------------------------
# wiki/SCHEMA.md
# ----------------------------------------------------------------------------
FILES['wiki/SCHEMA.md'] = r'''
# Wiki schema

Rules for the pages in this folder. The file name is the citation key: `smith2020.md`.

Each page describes one source and has these sections:

- `## Question`: what was studied.
- `## Design and sample`: design, sample, measures.
- `## Key findings`: the findings, one per line.
- `## Quotes`: word-for-word passages, with page or section, that support the findings.
- `## Limitations`: limitations the authors themselves state.

A page contains only what the source says. The reviewer checks citations in the paper against the Quotes section.
'''

# ----------------------------------------------------------------------------
# src/paperkit/__init__.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/__init__.py'] = r'''
"""paperkit: write a paper from finished results, with code, not the agent, deciding the order of steps."""

__version__ = "0.1.0"
'''

# ----------------------------------------------------------------------------
# src/paperkit/schemas.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/schemas.py'] = r'''
"""Data schemas. Everything that moves between code and agents goes through these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["OBSERVED", "INFERRED", "ASSUMED", "SPECULATIVE"]


class SectionSpec(BaseModel):
    id: str
    title: str
    max_words: int = 1000
    required_headings: list[str] = Field(default_factory=list)


class PaperSpec(BaseModel):
    title: str
    design: Literal["observational", "experimental"] = "observational"
    max_rounds: int = 3
    csl: str | None = None
    number_whitelist: list[str] = Field(default_factory=list)
    term_whitelist: list[str] = Field(default_factory=list)
    sections: list[SectionSpec]

    def section(self, sec_id: str) -> SectionSpec:
        for sec in self.sections:
            if sec.id == sec_id:
                return sec
        raise KeyError(f"No section '{sec_id}' in paper.yaml")


class Claim(BaseModel):
    id: str = Field(description="C1, C2, ...")
    text: str = Field(description="One claim in one sentence")
    category: Category
    fact_ids: list[str] = Field(default_factory=list, description="Ids from the facts registry")
    cite_keys: list[str] = Field(default_factory=list, description="Citation keys from the library")
    assumptions: list[str] = Field(default_factory=list, description="What this claim depends on")


class ClaimList(BaseModel):
    """What the planner returns."""

    claims: list[Claim]


class ClaimTable(BaseModel):
    """What is stored on disk. Only a person sets the approved flag, through the CLI."""

    section_id: str
    approved: bool = False
    claims: list[Claim]


class Draft(BaseModel):
    markdown: str = Field(description="The full section in Markdown")


class Issue(BaseModel):
    gate: str = Field(description="Which check raised it")
    severity: Literal["blocking", "warning"] = "blocking"
    message: str
    excerpt: str = ""


class Review(BaseModel):
    issues: list[Issue] = Field(default_factory=list)


class WikiPage(BaseModel):
    markdown: str
'''

# ----------------------------------------------------------------------------
# src/paperkit/facts.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/facts.py'] = r'''
"""Facts registry: the only source of numbers in the text.

The writer types {{F12}}; code substitutes the fact text at build time. The model never types a number.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{(F\w+)\}\}")


def load(path: Path) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def from_csv(csv_path: Path, out_path: Path) -> dict[str, dict]:
    """CSV with columns id,text,source -> facts.json."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    facts = {r["id"].strip(): {"text": r["text"].strip(), "source": r["source"].strip()} for r in rows}
    bad = [k for k in facts if not re.fullmatch(r"F\w+", k)]
    if bad:
        raise ValueError(f"Fact ids must look like F1, F2a: {bad}")
    if len(facts) != len(rows):
        raise ValueError("Duplicate fact ids in CSV")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return facts


def used(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render(text: str, facts: dict[str, dict]) -> str:
    """Substitutes known facts. Unknown placeholders are left in place and caught by the build."""
    return PLACEHOLDER.sub(lambda m: facts[m.group(1)]["text"] if m.group(1) in facts else m.group(0), text)
'''

# ----------------------------------------------------------------------------
# src/paperkit/agents.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/agents.py'] = r'''
"""Agents: a prompt plus an answer schema.

Every call starts from a clean context: the model sees only what is passed in as arguments.
State between calls is kept by code on disk, not by a chat history.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable, Sequence

from pydantic import BaseModel, Field

from .schemas import Claim, ClaimList, Draft, Issue, Review, SectionSpec, WikiPage

# provider -> (environment variable that holds its key, model used when none is configured)
PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", "claude-sonnet-5-5"),
    "nvidia": ("NVIDIA_API_KEY", "nvidia/nemotron-3-super-120b-a12b"),   # IDs change: check build.nvidia.com
}
PIPELINE_AGENTS = ("planner", "writer", "reviewer")

LLM: Callable | None = None      # swapped in tests and in the dry run: agents.LLM = fake
LOG_DIR: Path | None = None      # when set, every call is logged as JSON
CONFIG: dict = {}                # contents of config/models.yaml, loaded by configure()


def max_tokens() -> int:
    return int(os.environ.get("PAPERKIT_MAX_TOKENS") or "8000")


def configure(root: str | Path) -> dict:
    """Loads <root>/config/models.yaml. Without the file, only the environment and the defaults apply."""
    global CONFIG
    path = Path(root) / "config" / "models.yaml"
    loaded: dict = {}
    if path.is_file():
        import yaml

        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"config/models.yaml is not valid YAML: {' '.join(str(exc).split())[:120]}") from None
        if not isinstance(loaded, dict):
            raise ValueError("config/models.yaml must be a mapping")
    CONFIG = loaded
    return CONFIG


def route(kind: str) -> tuple[str, str]:
    """Provider and model for one agent.

    Order: the agent's own entry in config/models.yaml, then PAPERKIT_PROVIDER and PAPERKIT_MODEL
    from the environment or .env, then the file's top-level provider, then that provider's default model.
    """
    own = (CONFIG.get("agents") or {}).get(kind) or {}
    default_provider = os.environ.get("PAPERKIT_PROVIDER") or CONFIG.get("provider") or "anthropic"
    provider = own.get("provider") or default_provider
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}' for the {kind}: use one of {', '.join(PROVIDERS)}")
    env_model = os.environ.get("PAPERKIT_MODEL") if provider == default_provider else None
    return provider, own.get("model") or env_model or PROVIDERS[provider][1]


def has_key(provider: str) -> bool:
    names = [PROVIDERS[provider][0]] + (["ANTHROPIC_AUTH_TOKEN"] if provider == "anthropic" else [])
    return any(os.environ.get(name) for name in names)


def call_anthropic(system: str, user: str, schema: type[BaseModel], model: str) -> BaseModel:
    """One request with no history. The answer is forced through a tool with a JSON schema."""
    import anthropic  # lazy import: gates and tests run without the SDK or a key

    client = anthropic.Anthropic()  # reads the key from ANTHROPIC_API_KEY
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens(),
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{
            "name": "submit",
            "description": "Submit the result in the required structure.",
            "input_schema": schema.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": "submit"},
    )
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Answer was cut off: raise PAPERKIT_MAX_TOKENS")
    block = next(b for b in resp.content if b.type == "tool_use")
    return schema.model_validate(block.input)


def call_llm(kind: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """Sends one request to whichever provider and model this agent is routed to."""
    provider, model = route(kind)
    if provider == "nvidia":
        from . import nvidia

        return nvidia.call(system, user, schema, model, max_tokens())
    return call_anthropic(system, user, schema, model)


class Ping(BaseModel):
    ok: bool = Field(description="Always true")


def ping_all() -> list[tuple[str, str, str, str]]:
    """One tiny request per distinct provider and model in use: (agents, provider, model, 'ok' or the error)."""
    routes: dict[tuple[str, str], list[str]] = {}
    for kind in PIPELINE_AGENTS:
        routes.setdefault(route(kind), []).append(kind)
    rows = []
    for (provider, model), kinds in routes.items():
        try:
            call_llm(kinds[0], "You are a connection test.", "Reply with ok set to true.", Ping)
            result = "ok"
        except Exception as exc:
            result = " ".join(str(exc).split())[:200] or type(exc).__name__
        rows.append((", ".join(kinds), provider, model, result))
    return rows


def _ask(kind: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    out = LLM(system, user, schema) if LLM else call_llm(kind, system, user, schema)
    if LOG_DIR is not None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:6]}.json"
        used = "stand-in" if LLM else ":".join(route(kind))
        record = {"kind": kind, "model": used, "system": system, "user": user, "output": out.model_dump()}
        (LOG_DIR / name).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _tag(name: str, body: str) -> str:
    return f"<{name}>\n{body.strip() or '(empty)'}\n</{name}>"


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _issues(issues: Sequence[Issue]) -> str:
    return "\n".join(f"- [{i.gate}] {i.message}" + (f" | {i.excerpt}" if i.excerpt else "") for i in issues)


# -------------------------------------------------------------------- planner

PLANNER = """You plan one section of a scientific paper as a table of claims. You do not write prose.

Each claim is one sentence with a category, the fact ids that support it, citation keys, and the assumptions it depends on.
Categories:
- OBSERVED: a result that is in the facts registry. It must list fact_ids.
- INFERRED: an interpretation of the results.
- ASSUMED: a premise the interpretation relies on and the study did not test.
- SPECULATIVE: a hypothesis for future work.

Rules:
- Number the claims C1, C2, ... in the order the section should present them.
- Use only fact ids from the registry and citation keys from the library list.
- If a needed source is not in the library, do not invent a key. Leave cite_keys empty and add "NEEDS SOURCE: what for" to the claim's assumptions.
- Cover every required heading. In the Discussion, also cover every key message.
- In the Introduction (section id "introduction"), take the background, the knowledge gap and the aim from <introduction_notes>. State no result of this study and use no OBSERVED claim there. A statement about earlier work is INFERRED, with its cite_keys, and any number in it comes from a fact id.
- Respect the stated limitations.
- Do not claim more than the results support."""


def plan_claims(sec: SectionSpec, *, design: str, key_messages: str, limitations: str, methods: str,
                results: str, fact_reg: dict, library: str, wiki_index: str,
                issues: Sequence[Issue] = (), introduction: str = "") -> list[Claim]:
    user = "\n\n".join([
        _tag("section", _json(sec.model_dump())),
        _tag("study_design", design),
        _tag("key_messages", key_messages),
        _tag("introduction_notes", introduction),
        _tag("limitations", limitations),
        _tag("methods", methods),
        _tag("results", results),
        _tag("facts_registry", _json(fact_reg)),
        _tag("library", library),
        _tag("wiki_index", wiki_index),
    ])
    if issues:
        user += "\n\n" + _tag("problems_in_your_previous_table", _issues(issues))
    return _ask("planner", PLANNER, user, ClaimList).claims


# --------------------------------------------------------------------- writer

WRITER = """You write one section of a scientific paper from an approved claim table. Use nothing beyond the materials given.

Code checks the draft and rejects it on any violation:
- Markdown. Use exactly the required "## " headings, in the given order, with a blank line between blocks. No lists.
- Every paragraph ends with a claim tag: <!-- C3 --> or <!-- C3,C4 -->. Use only claim ids from the table, and use every claim at least once.
- Never type a digit. Every number comes from the facts as a placeholder such as {{F12}}; code substitutes the text later. Use only the facts listed for your claims.
- Cite only as [@key], with keys listed in the claims. Never write author and year by hand.
- Match the wording to the claim category:
  OBSERVED: "we found" or "we observed", with a fact placeholder of that claim.
  INFERRED: "suggests", "is consistent with", "indicates".
  ASSUMED: say "this assumes that ..." and whether it was tested.
  SPECULATIVE: "may", "might", "one possibility is".
- No "novel", "first", "proves", "clearly", "robust". Never "no effect": say "we did not detect".
- If something you need is missing, write [AUTHOR: what is missing] or [NEEDS SOURCE: what for]. Do not fill the gap yourself."""

OBSERVATIONAL = """
- The design is observational: no causal wording (cause, lead to, result in, effect of, impact, drive) outside paragraphs tagged only with SPECULATIVE or ASSUMED claims."""


def write_section(sec: SectionSpec, *, design: str, claims: Sequence[Claim], fact_reg: dict,
                  wiki_pages: dict[str, str], prev_draft: str = "", issues: Sequence[Issue] = ()) -> str:
    system = WRITER + (OBSERVATIONAL if design == "observational" else "")
    user = "\n\n".join([
        _tag("section", _json(sec.model_dump())),
        _tag("claims", _json([c.model_dump() for c in claims])),
        _tag("facts", _json(fact_reg)),
        _tag("sources", "\n\n".join(f"## {k}\n{v}" for k, v in wiki_pages.items())),
    ])
    if prev_draft:
        user += "\n\n" + _tag("previous_draft", prev_draft)
        user += "\n\n" + _tag("problems_to_fix", _issues(issues))
    return _ask("writer", system, user, Draft).markdown


# ------------------------------------------------------------------- reviewer

REVIEWER = """You are a sceptical reviewer of one section of a scientific paper. You flag problems; you never rewrite.

Check the draft sentence by sentence against the methods, results, facts and claim table. Numbers appear as {{F..}} placeholders; their values are in the facts.
Report an issue with gate set to one of:
- unsupported: a statement with no supporting fact or claim
- overclaim: wording stronger than the claim's category or the study design allows
- logic: a conclusion that does not follow, or a contradiction with the results
- alternative: an obvious alternative explanation left unaddressed
- assumption: an assumption the argument relies on but does not state
- citation: a cited source whose page does not support the sentence; a missing page counts

For each issue give severity ("blocking" if the paper would be wrong or misleading, otherwise "warning"), a message saying what is wrong, and the exact sentence as excerpt.
If the draft is sound, return an empty list."""


def review_section(sec: SectionSpec, *, design: str, methods: str, results: str, claims: Sequence[Claim],
                   fact_reg: dict, wiki_pages: dict[str, str], draft: str) -> list[Issue]:
    user = "\n\n".join([
        _tag("section", _json(sec.model_dump())),
        _tag("study_design", design),
        _tag("methods", methods),
        _tag("results", results),
        _tag("claims", _json([c.model_dump() for c in claims])),
        _tag("facts", _json(fact_reg)),
        _tag("sources", "\n\n".join(f"## {k}\n{v}" for k, v in wiki_pages.items())),
        _tag("draft", draft),
    ])
    review = _ask("reviewer", REVIEWER, user, Review)
    return [i.model_copy(update={"gate": f"review:{i.gate}"}) for i in review.issues]


# ----------------------------------------------------------------------- wiki

WIKI = """Write a wiki page for one source, using exactly these headings:
# <citation key>
## Question
## Design and sample
## Key findings
## Quotes
## Limitations

Write only what the source text says. Under Quotes, copy the passages that support each key finding word for word, with page or section."""


def wiki_page(key: str, source_text: str) -> str:
    user = _tag("citation_key", key) + "\n\n" + _tag("source_text", source_text)
    return _ask("wiki", WIKI, user, WikiPage).markdown
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/__init__.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/__init__.py'] = r'''
"""Gates: deterministic checks on a draft. Each module provides check(draft, ctx) -> list[Issue]."""
from __future__ import annotations

from ..schemas import Issue
from . import citations, coverage, language, numbers, structure
from .claims import check_claims
from .common import GateContext

GATES = [structure, citations, numbers, language, coverage]

__all__ = ["GATES", "GateContext", "blocking", "check_claims", "run_gates"]


def run_gates(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    for gate in GATES:
        issues += gate.check(draft, ctx)
    return issues


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "blocking"]
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/common.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/common.py'] = r'''
"""Draft parsing shared by all gates."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import ClaimTable, PaperSpec, SectionSpec

CLAIM_TAG = re.compile(r"<!--\s*(C\d+(?:\s*,\s*C\d+)*)\s*-->")
COMMENT = re.compile(r"<!--.*?-->", re.S)
CITE = re.compile(r"\[([^\[\]]*@[^\[\]]+)\]")
CITE_KEY = re.compile(r"@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)
MARKER = re.compile(r"\[(?:AUTHOR|NEEDS SOURCE):[^\]]*\]")
FACT = re.compile(r"\{\{F\w+\}\}")


@dataclass
class GateContext:
    spec: PaperSpec
    sec: SectionSpec
    claims: ClaimTable
    facts: dict
    bib_keys: set[str]


def headings(md: str) -> list[str]:
    return [title for _, title in HEADING.findall(md)]


def paragraphs(md: str) -> list[tuple[str, list[str]]]:
    """Paragraphs without headings: (text, claim ids from its tags)."""
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        text = "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#")).strip()
        if not text:
            continue
        ids: list[str] = []
        for m in CLAIM_TAG.finditer(text):
            ids += [x.strip() for x in m.group(1).split(",")]
        out.append((text, ids))
    return out


def plain(md: str) -> str:
    """Text without tags, citations, placeholders and heading marks: for counting words and finding digits."""
    text = COMMENT.sub("", md)
    text = CITE.sub("", text)
    text = FACT.sub("", text)
    text = MARKER.sub("", text)
    return re.sub(r"^#{1,6}[ \t]+", "", text, flags=re.M)


def cite_keys(md: str) -> set[str]:
    keys: set[str] = set()
    for m in CITE.finditer(md):
        keys |= {k.rstrip(".,;:") for k in CITE_KEY.findall(m.group(1))}
    return keys


def short(text: str, n: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/claims.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/claims.py'] = r'''
"""Gate for the claim table: runs before a person or the writer sees it."""
from __future__ import annotations

import re

from ..schemas import ClaimTable, Issue


def check_claims(table: ClaimTable, fact_reg: dict, bib_keys: set[str]) -> list[Issue]:
    issues: list[Issue] = []

    def add(message: str, claim_id: str = "") -> None:
        issues.append(Issue(gate="claims", message=message, excerpt=claim_id))

    if not table.claims:
        add("Claim table is empty")
    seen: set[str] = set()
    for c in table.claims:
        if not re.fullmatch(r"C\d+", c.id):
            add(f"Bad claim id '{c.id}': expected C1, C2, ...", c.id)
        if c.id in seen:
            add(f"Duplicate claim id {c.id}", c.id)
        seen.add(c.id)
        for fid in c.fact_ids:
            if fid not in fact_reg:
                add(f"{c.id}: fact id not in facts.json: {fid}", c.id)
        for key in c.cite_keys:
            if key not in bib_keys:
                add(f"{c.id}: citation key not in library.bib: {key}", c.id)
        if c.category == "OBSERVED" and not c.fact_ids:
            add(f"{c.id}: an OBSERVED claim needs at least one fact id", c.id)
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/structure.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/structure.py'] = r'''
"""Structure: required headings in order, and the word limit."""
from __future__ import annotations

from ..schemas import Issue
from .common import GateContext, headings, plain


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    found = headings(draft)
    last = -1
    for required in ctx.sec.required_headings:
        if required not in found:
            issues.append(Issue(gate="structure", message=f"Missing required heading: ## {required}"))
            continue
        pos = found.index(required)
        if pos < last:
            issues.append(Issue(gate="structure", message=f"Heading out of order: ## {required}"))
        last = max(last, pos)
    extra = [h for h in found if h not in ctx.sec.required_headings]
    if ctx.sec.required_headings and extra:
        issues.append(Issue(gate="structure", message=f"Headings not in the spec: {extra}"))
    words = len(plain(draft).split())
    if words == 0:
        issues.append(Issue(gate="structure", message="Draft is empty"))
    if words > ctx.sec.max_words:
        issues.append(Issue(gate="structure", message=f"Too long: {words} words, limit {ctx.sec.max_words}"))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/citations.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/citations.py'] = r'''
"""Citations: [@key] only, and the key is in library.bib and in the approved claim table."""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, cite_keys, short

# "(Smith, 2020)", "(Smith et al. 2020)" and a bare "Smith et al."
TEXTUAL = re.compile(r"\([A-Z][^()\[\]]*?\b(?:19|20)\d{2}[a-z]?\)|\b[A-Z][A-Za-z'-]+ et al\.?")
NEEDS_SOURCE = re.compile(r"\[NEEDS SOURCE:[^\]]*\]")


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    used = cite_keys(draft)
    allowed = {key for c in ctx.claims.claims for key in c.cite_keys}
    for key in sorted(used - ctx.bib_keys):
        issues.append(Issue(gate="citations", message=f"Citation key not in library.bib: {key}"))
    for key in sorted((used & ctx.bib_keys) - allowed):
        issues.append(Issue(gate="citations", message=f"Citation not in the approved claim table: {key}"))
    for m in TEXTUAL.finditer(COMMENT.sub("", draft)):
        issues.append(Issue(gate="citations", message="Citation typed by hand: use [@key]", excerpt=short(m.group(0))))
    for m in NEEDS_SOURCE.finditer(draft):
        issues.append(Issue(gate="citations", severity="warning", message="Source missing from the library",
                            excerpt=short(m.group(0))))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/numbers.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/numbers.py'] = r'''
"""Numbers: no digits in the text, only {{F..}} placeholders for approved facts."""
from __future__ import annotations

import re

from .. import facts
from ..schemas import Issue
from .common import GateContext, plain

TOKEN_WITH_DIGIT = re.compile(r"\S*\d\S*")


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    used = facts.used(draft)
    allowed = {fid for c in ctx.claims.claims for fid in c.fact_ids}
    for fid in sorted(used - set(ctx.facts)):
        issues.append(Issue(gate="numbers", message=f"Unknown fact placeholder: {{{{{fid}}}}}"))
    for fid in sorted((used & set(ctx.facts)) - allowed):
        issues.append(Issue(gate="numbers", message=f"Fact not in the approved claim table: {fid}"))

    text = plain(draft)
    for token in ctx.spec.number_whitelist:
        text = text.replace(token, "")
    raw = sorted({m.group(0).strip(".,;:()") for m in TOKEN_WITH_DIGIT.finditer(text)})
    for token in raw[:10]:
        issues.append(Issue(gate="numbers", message="Number typed by hand: use a {{F..}} placeholder", excerpt=token))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/language.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/language.py'] = r'''
"""Language: wording matches the study design and the claim category.

The lists below are a starting point. Extend them for your field and your style.
"""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, paragraphs, short

IC = re.IGNORECASE
CAUSAL = re.compile(
    r"\b(caus(?:e|es|ed|ing|al)|leads? to|led to|results? in|resulted in|effects? of|"
    r"impact(?:s|ed)?|driv(?:e|es|en|ing)|determin(?:e|es|ed))\b", IC)
HYPE = re.compile(
    r"\b(novel|for the first time|the first to|prov(?:e|es|ed|en)|clearly|undoubtedly|"
    r"robust(?:ly)?|groundbreaking|unprecedented)\b", IC)
NULL = re.compile(r"\bno (?:effect|association|difference|relationship)\b", IC)
FILLER = re.compile(
    r"\b(it is important to note that|it should be noted that|it is worth (?:noting|mentioning) that|"
    r"in order to|very|really|basically)\b", IC)

# The wording a paragraph must contain to show the category of its claim
MARKERS = {
    "INFERRED": re.compile(r"\b(suggest|consistent with|indicat|impl(?:y|ies)|appear|may|might)", IC),
    "ASSUMED": re.compile(r"\bassum", IC),
    "SPECULATIVE": re.compile(r"\b(may|might|could|possib|speculat|hypothes)", IC),
}
HEDGED = {"ASSUMED", "SPECULATIVE"}


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    category = {c.id: c.category for c in ctx.claims.claims}

    for raw, ids in paragraphs(draft):
        text = COMMENT.sub("", raw)
        for term in ctx.spec.term_whitelist:
            text = re.sub(re.escape(term), "", text, flags=IC)
        cats = {category[i] for i in ids if i in category}

        if ctx.spec.design == "observational" and not (cats and cats <= HEDGED):
            for m in CAUSAL.finditer(text):
                issues.append(Issue(gate="language", excerpt=short(text),
                                    message=f"Causal wording in an observational study: '{m.group(0)}'"))
        for m in HYPE.finditer(text):
            issues.append(Issue(gate="language", excerpt=short(text),
                                message=f"Overstated wording: '{m.group(0)}'"))
        for m in NULL.finditer(text):
            issues.append(Issue(gate="language", excerpt=short(text),
                                message=f"'{m.group(0)}': say it was not detected and give the interval"))
        for m in FILLER.finditer(text):
            issues.append(Issue(gate="language", severity="warning", excerpt=short(text),
                                message=f"Filler: '{m.group(0)}'"))
        for cat in sorted(cats & set(MARKERS)):
            if not MARKERS[cat].search(text):
                issues.append(Issue(gate="language", excerpt=short(text),
                                    message=f"Paragraph carries an {cat} claim but is not worded as one"))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/validators/coverage.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/validators/coverage.py'] = r'''
"""Coverage: every paragraph is tied to a claim, and every claim is used."""
from __future__ import annotations

from .. import facts
from ..schemas import Issue
from .common import GateContext, paragraphs, short


def check(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    known = {c.id: c for c in ctx.claims.claims}
    facts_seen: dict[str, set[str]] = {}

    for text, ids in paragraphs(draft):
        if not ids:
            issues.append(Issue(gate="coverage", message="Paragraph without a claim tag <!-- Cn -->",
                                excerpt=short(text)))
        for cid in ids:
            if cid not in known:
                issues.append(Issue(gate="coverage", message=f"Unknown claim id in tag: {cid}", excerpt=short(text)))
            else:
                facts_seen.setdefault(cid, set()).update(facts.used(text))

    for cid, claim in known.items():
        if cid not in facts_seen:
            issues.append(Issue(gate="coverage", message=f"Claim not used in the draft: {cid}", excerpt=claim.text))
        elif claim.category == "OBSERVED" and claim.fact_ids and not facts_seen[cid] & set(claim.fact_ids):
            issues.append(Issue(gate="coverage", excerpt=claim.text,
                                message=f"{cid} is OBSERVED but its paragraph shows none of its facts {claim.fact_ids}"))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/zotero.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/zotero.py'] = r'''
"""Read-only reference library.

The agent never creates references; it picks keys. Keys have one source: refs/library.bib,
which Zotero keeps up to date through Better BibTeX auto-export.
"""
from __future__ import annotations

import re
from pathlib import Path

ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.S)
FIELD = re.compile(r"^\s*(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.M | re.S)
SKIP = {"comment", "string", "preamble"}


def load_bib(path: Path) -> dict[str, dict[str, str]]:
    """Simple .bib parser: key -> fields. Enough for searching and for checking keys."""
    if not path.exists():
        return {}
    bib: dict[str, dict[str, str]] = {}
    for kind, key, body in ENTRY.findall(path.read_text(encoding="utf-8")):
        if kind.lower() in SKIP:
            continue
        bib[key] = {name.lower(): " ".join(re.sub(r"[{}]", "", value).split()) for name, value in FIELD.findall(body)}
    return bib


def _year(fields: dict[str, str]) -> str:
    return fields.get("year") or fields.get("date", "")[:4]


def library_listing(bib: dict[str, dict[str, str]]) -> str:
    """Listing for the planner: one line per source."""
    return "\n".join(f"- {key}: {f.get('title', '')} ({_year(f)})" for key, f in sorted(bib.items()))


def search_bib(bib: dict[str, dict[str, str]], query: str, limit: int = 10) -> list[dict[str, str]]:
    """Word search across key, title, authors, abstract and keywords."""
    words = query.lower().split()
    hits = []
    for key, f in bib.items():
        hay = " ".join([key, f.get("title", ""), f.get("author", ""), f.get("abstract", ""), f.get("keywords", "")]).lower()
        score = sum(word in hay for word in words)
        if score:
            hits.append((score, key, f))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return [{"key": key, "title": f.get("title", ""), "year": _year(f), "abstract": f.get("abstract", "")[:500]}
            for _, key, f in hits[:limit]]


def search_zotero(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Stub: search a running Zotero through its local API.

    Needs `pip install pyzotero`, Zotero open, and the local API enabled in Zotero's settings.
    Untested. Check that the key it returns matches the key in library.bib.
    """
    from pyzotero import zotero

    zot = zotero.Zotero(library_id="0", library_type="user", local=True)
    out = []
    for item in zot.items(q=query, limit=limit):
        data = item.get("data", {})
        pinned = re.search(r"Citation Key:\s*(\S+)", data.get("extra", ""))
        key = data.get("citationKey") or (pinned.group(1) if pinned else "")
        out.append({"key": key, "title": data.get("title", ""), "year": data.get("date", "")[:4],
                    "abstract": data.get("abstractNote", "")[:500]})
    return out
'''

# ----------------------------------------------------------------------------
# src/paperkit/wiki.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/wiki.py'] = r'''
"""Source wiki: one page per citation key. The writer and the reviewer read these pages, not the PDFs."""
from __future__ import annotations

from pathlib import Path

from . import agents
from .schemas import Issue

REQUIRED = ["## Key findings", "## Quotes"]
SERVICE = {"index", "SCHEMA"}


def index(wiki_dir: Path) -> str:
    path = wiki_dir / "index.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def page(wiki_dir: Path, key: str) -> str:
    path = wiki_dir / f"{key}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def pages_for(wiki_dir: Path, keys) -> dict[str, str]:
    """Pages for a set of keys. A missing page is passed on explicitly so the reviewer sees it."""
    return {key: page(wiki_dir, key) or "(no wiki page for this source)" for key in sorted(set(keys))}


def ingest(wiki_dir: Path, key: str, source_text: str) -> Path:
    """The agent writes a page from the source text; code files it and updates the index."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    path = wiki_dir / f"{key}.md"
    path.write_text(agents.wiki_page(key, source_text).strip() + "\n", encoding="utf-8")
    idx = wiki_dir / "index.md"
    current = idx.read_text(encoding="utf-8") if idx.exists() else "# Wiki index\n\n"
    if f"[[{key}]]" not in current:
        idx.write_text(current.rstrip("\n") + f"\n- [[{key}]]:\n", encoding="utf-8")
    return path


def lint(wiki_dir: Path, bib_keys: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    listed = index(wiki_dir)
    for path in sorted(wiki_dir.glob("*.md")):
        key = path.stem
        if key in SERVICE:
            continue
        text = path.read_text(encoding="utf-8")
        for heading in REQUIRED:
            if heading not in text:
                issues.append(Issue(gate="wiki", message=f"{path.name}: missing '{heading}'"))
        if key not in bib_keys:
            issues.append(Issue(gate="wiki", severity="warning", message=f"{path.name}: no such key in library.bib"))
        if f"[[{key}]]" not in listed:
            issues.append(Issue(gate="wiki", severity="warning", message=f"{path.name}: not listed in index.md"))
    return issues
'''

# ----------------------------------------------------------------------------
# src/paperkit/build.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/build.py'] = r'''
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
'''

# ----------------------------------------------------------------------------
# src/paperkit/orchestrator.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/orchestrator.py'] = r'''
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
                                     wiki_pages=pages, prev_draft=draft, issues=issues)
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
'''

# ----------------------------------------------------------------------------
# src/paperkit/__main__.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/__main__.py'] = r'''
"""CLI: python -m paperkit <command>, or paperkit <command> after pip install -e .

With no command it opens the interactive start screen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import agents, build, dryrun, env, extract, facts, orchestrator, preflight, wiki, wizard
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
    ext = sub.add_parser("extract", help="draft facts.csv and key_messages.md from the Results section (calls the model)")
    ext.add_argument("what", nargs="?", choices=["all", "facts", "key-messages"], default="all")
    ext.add_argument("--force", action="store_true", help="replace the file even if it already has real content")
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
        if cmd in ("plan", "run", "ping", "extract"):    # the other commands do not call a model
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
'''

# ----------------------------------------------------------------------------
# tests/test_smoke.py
# ----------------------------------------------------------------------------
FILES['tests/test_smoke.py'] = r'''
"""Smoke test with no network: the model is replaced, so this checks the framework itself."""
import json

import pytest

from paperkit import agents, build, orchestrator
from paperkit.schemas import Claim, ClaimList, Draft, Issue, Review
from paperkit.validators import blocking

SPEC = """
title: Test paper
design: observational
max_rounds: 3
sections:
  - id: discussion
    title: Discussion
    max_words: 200
    required_headings: [Principal findings, Interpretation]
"""
FACTS = {"F1": {"text": "r = 0.31", "source": "Table 2"}, "F2": {"text": "412", "source": "Methods"}}
BIB = "@article{smith2020,\n  title = {A study},\n  author = {Smith, A.},\n  year = {2020},\n}\n"
CLAIMS = [
    Claim(id="C1", text="X is associated with Y.", category="OBSERVED", fact_ids=["F1", "F2"]),
    Claim(id="C2", text="X tracks Y.", category="INFERRED", cite_keys=["smith2020"]),
    Claim(id="C3", text="Measurement error is unrelated to Y.", category="ASSUMED"),
]
GOOD = """## Principal findings

We observed an association between X and Y ({{F1}}) among {{F2}} participants. <!-- C1 -->

## Interpretation

This suggests that X tracks Y, consistent with earlier work [@smith2020]. <!-- C2 -->

This reading assumes that measurement error was unrelated to Y, which we did not test. <!-- C3 -->
"""
BAD = """## Principal findings

X causes Y in 412 participants (Smith et al., 2020).

This clearly proves it [@ghost2019]. <!-- C9 -->
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "paper.yaml").write_text(SPEC, encoding="utf-8")
    for folder in ["facts", "refs", "inputs", "wiki"]:
        (tmp_path / folder).mkdir()
    (tmp_path / "facts" / "facts.json").write_text(json.dumps(FACTS), encoding="utf-8")
    (tmp_path / "refs" / "library.bib").write_text(BIB, encoding="utf-8")
    yield orchestrator.Project(tmp_path)
    agents.LLM = None


def fake_llm(drafts, reviews):
    """Stand-in model: returns prepared answers in order."""
    drafts, reviews = iter(drafts), iter(reviews)

    def llm(system, user, schema):
        if schema is ClaimList:
            return ClaimList(claims=CLAIMS)
        if schema is Draft:
            return Draft(markdown=next(drafts))
        if schema is Review:
            return Review(issues=next(reviews))
        raise AssertionError(schema)

    return llm


def test_gates_catch_a_bad_draft(project, tmp_path):
    agents.LLM = fake_llm([], [])
    orchestrator.plan(project, "discussion")
    bad = tmp_path / "bad.md"
    bad.write_text(BAD, encoding="utf-8")
    issues = blocking(orchestrator.validate(project, "discussion", bad))
    assert {i.gate for i in issues} == {"structure", "citations", "numbers", "language", "coverage"}


def test_good_draft_passes_gates(project, tmp_path):
    agents.LLM = fake_llm([], [])
    orchestrator.plan(project, "discussion")
    good = tmp_path / "good.md"
    good.write_text(GOOD, encoding="utf-8")
    assert orchestrator.validate(project, "discussion", good) == []


def test_full_loop_needs_approval_then_converges(project, tmp_path):
    flagged = [Issue(gate="overclaim", message="Too strong", excerpt="This suggests")]
    agents.LLM = fake_llm([BAD, GOOD, GOOD], [flagged, []])

    assert orchestrator.run_section(project, "discussion") == "AWAITING_APPROVAL"
    assert orchestrator.approve(project, "discussion") == []
    assert orchestrator.run_section(project, "discussion") == "DONE"   # round 1: gates, round 2: reviewer, round 3: clean

    md, issues = build.assemble(tmp_path, project.spec, project.facts)
    text = md.read_text(encoding="utf-8")
    assert not issues
    assert "r = 0.31" in text and "{{" not in text and "<!--" not in text
    assert (tmp_path / "state" / "log").exists()


def test_escalates_when_rounds_run_out(project):
    agents.LLM = fake_llm([BAD, BAD, BAD], [])
    orchestrator.plan(project, "discussion")
    orchestrator.approve(project, "discussion")
    assert orchestrator.run_section(project, "discussion") == "ESCALATED"
    assert (project.root / "state" / "reviews" / "discussion.open.json").exists()
'''



# Extended project layout. Existing files are preserved on reruns.
EMPTY_DIRS += [
    ".papers", ".writing_guides/general", ".writing_guides/journal",
    ".writing_guides/reporting", ".cache/papers", ".cache/guides",
    "inputs/figures", "wiki/sources", "wiki/concepts", "rules", "config",
]
FILES['inputs/tables/manifest.yaml'] = '\n# Add one entry per research table. Example (uncomment and adapt):\n# tables:\n#   - id: T01\n#     file: prediction_performance.csv\n#     title: Cognitive prediction performance\n#     analysis: prediction\n#     grouping_columns: [outcome, modality, model, fold]\n#     metrics:\n#       - column: r\n#         meaning: Pearson correlation\n#         unit: proportion\n#       - column: r2\n#         meaning: Out-of-sample R-squared\n#         unit: proportion\ntables: []\n'
FILES['config/models.yaml'] = r'''
# Which provider and model each agent uses. Read at start-up; `paperkit ping` shows the result.
# For one agent the order is: its own entry below, then PAPERKIT_PROVIDER and PAPERKIT_MODEL from the
# environment or .env, then the provider on the next line with its built-in default model.
provider: anthropic            # anthropic | nvidia
agents:
  planner: {model: null}
  writer: {model: null}
  reviewer: {model: null}
  wiki: {model: null}
  literature: {model: null}
  rules: {model: null}
  facts: {model: null}

# Example: free NVIDIA endpoints for planning and writing, a different model family for the review.
# Copy each model ID from the model's page on build.nvidia.com; the catalogue changes.
# provider: nvidia
# agents:
#   planner: {model: nvidia/nemotron-3-super-120b-a12b}
#   writer: {model: nvidia/nemotron-3-super-120b-a12b}
#   reviewer: {provider: anthropic, model: claude-sonnet-5-5}
'''
FILES['facts/candidates.json'] = '\n{}\n'
FILES['wiki/evidence.json'] = '\n[]\n'
FILES['rules/general.json'] = '\n[]\n'
FILES['rules/journal.json'] = '\n[]\n'
FILES['rules/reporting.json'] = '\n[]\n'
FILES['rules/active_rules.json'] = '\n[]\n'
FILES['rules/candidates.json'] = '\n[]\n'
FILES['src/paperkit/ingestion/__init__.py'] = '\n"""Document ingestion components."""\n'
FILES['src/paperkit/ingestion/pdf_parser.py'] = '\n"""Extract page-level text; requires the optional PyMuPDF package."""\nfrom pathlib import Path\n\n\ndef parse_pdf(path: Path) -> list[dict]:\n    import pymupdf\n    with pymupdf.open(path) as doc:\n        return [{"source": str(path), "page": i + 1, "text": page.get_text()}\n                for i, page in enumerate(doc)]\n'
FILES['src/paperkit/ingestion/table_parser.py'] = '\n"""Read CSV/TSV cells without converting or rounding numeric strings."""\nimport csv\nfrom pathlib import Path\n\n\ndef read_table(path: Path) -> list[dict]:\n    if path.suffix.lower() not in {".csv", ".tsv"}:\n        raise ValueError("Expected CSV or TSV")\n    with path.open(encoding="utf-8-sig", newline="") as f:\n        reader = csv.DictReader(f, delimiter="\\t" if path.suffix.lower() == ".tsv" else ",")\n        return list(reader)\n'
FILES['src/paperkit/ingestion/literature_ingest.py'] = '\n"""Reserved for PDF discovery, Zotero matching and evidence extraction; not implemented yet."""\n'
FILES['src/paperkit/ingestion/rules_ingest.py'] = '\n"""Reserved for guideline extraction and approval; not implemented yet."""\n'
FILES['src/paperkit/ingestion/facts_ingest.py'] = '\n"""Reserved for manifest-driven fact extraction and approval; not implemented yet."""\n'
FILES['src/paperkit/validators/writing_rules.py'] = '\n"""Reserved for approved writing-rule validation; not registered as a gate yet."""\n'

FILES['src/paperkit/ingestion_schemas.py'] = '\n"""Additional schemas for ingestion. Not yet connected to the original pipeline."""\nfrom typing import Literal\nfrom pydantic import BaseModel, Field\nfrom decimal import Decimal\n\n\nclass ScientificFact(BaseModel):\n    id: str\n    text: str\n    analysis: str | None = None\n    outcome: str | None = None\n    predictor: str | None = None\n    modality: str | None = None\n    model: str | None = None\n    sample: str | None = None\n    fold: str | None = None\n    metric: str\n    value: Decimal\n    ci_lower: Decimal | None = None\n    ci_upper: Decimal | None = None\n    confidence_level: Decimal | None = None\n    n: int | None = None\n    unit: str | None = None\n    source_file: str\n    source_row: int | None = None\n    source_column: str | None = None\n    source_sha256: str | None = None\n    approved: bool = False\n\n\nclass MetricSpec(BaseModel):\n    column: str\n    meaning: str\n    unit: str | None = None\n\n\nclass TableSpec(BaseModel):\n    id: str\n    file: str\n    title: str\n    analysis: str\n    grouping_columns: list[str] = Field(default_factory=list)\n    metrics: list[MetricSpec] = Field(default_factory=list)\n\n\nclass TableManifest(BaseModel):\n    tables: list[TableSpec] = Field(default_factory=list)\n\n\nclass SourceDocument(BaseModel):\n    path: str\n    sha256: str\n    citation_key: str | None = None\n    doi: str | None = None\n\n\nclass EvidenceItem(BaseModel):\n    id: str\n    citation_key: str\n    statement: str\n    quotation: str\n    page: int | None = None\n    section: str | None = None\n    verified: bool = False\n\n\nclass LiteratureRecord(BaseModel):\n    source: SourceDocument\n    question: str = ""\n    study_design: str = ""\n    population: str = ""\n    methods: str = ""\n    limitations: list[str] = Field(default_factory=list)\n    evidence: list[EvidenceItem] = Field(default_factory=list)\n\n\nclass ConceptRecord(BaseModel):\n    name: str\n    synthesis: str\n    supporting_evidence_ids: list[str] = Field(default_factory=list)\n    contradicting_evidence_ids: list[str] = Field(default_factory=list)\n    unresolved_questions: list[str] = Field(default_factory=list)\n\n\nclass WritingRule(BaseModel):\n    id: str\n    category: Literal["structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting", "scientific_reasoning"]\n    instruction: str\n    rationale: str = ""\n    sections: list[str] = Field(default_factory=lambda: ["all"])\n    study_designs: list[str] = Field(default_factory=lambda: ["all"])\n    priority: Literal["required", "recommended", "optional"]\n    severity: Literal["blocking", "warning"]\n    validation_method: Literal["python", "ai", "human", "hybrid"]\n    source_file: str\n    source_page: int | None = None\n    source_quote: str | None = None\n    approved: bool = False\n\n\nclass RuleSet(BaseModel):\n    name: str\n    version: str = "1.0"\n    rules: list[WritingRule] = Field(default_factory=list)\n\n\nclass AgentConfig(BaseModel):\n    provider: str = "anthropic"\n    model: str | None = None\n    max_tokens: int = 8000\n\n\nclass AgentRun(BaseModel):\n    agent: str\n    model: str\n    status: str\n    input_tokens: int | None = None\n    output_tokens: int | None = None\n'
FILES['docs/ingestion.md'] = '\n# Extended ingestion layout\n\nPlace literature PDFs in `.papers/` and writing guides in `.writing_guides/`.\nUse CSV/TSV tables in `inputs/tables/` and describe them in `manifest.yaml`.\nThe new schemas live in `ingestion_schemas.py`; the existing schemas.py re-exports them for fresh projects.\nExisting projects can import directly from ingestion_schemas without modifying schemas.py.\nCandidate facts go in facts/candidates.json; the original facts/facts.json and inputs/facts.csv remain compatible with the existing CLI.\nThe new registries are templates, not automatically populated. The PDF and table readers are basic utilities; agent ingestion, approvals, configuration loading and new CLI commands are not implemented.\nThe original wiki reads wiki/<citation-key>.md; wiki/sources and wiki/concepts are reserved for future migration.\nInstall PDF parsing support with python -m pip install pymupdf.\n'

FILES['src/paperkit/schemas.py'] += "\n# Extended ingestion schemas\nfrom .ingestion_schemas import (ScientificFact, MetricSpec, TableSpec, TableManifest, SourceDocument, EvidenceItem, LiteratureRecord, ConceptRecord, WritingRule, RuleSet, AgentConfig, AgentRun)\n"
FILES['README.md'] += "\n## Extended ingestion layout\n\nSee [docs/ingestion.md](docs/ingestion.md) for new input folders and current implementation limits.\n"

# ----------------------------------------------------------------------------
# Interactive start screen: input checklist, guided fill-in, menu, dry run
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# src/paperkit/env.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/env.py'] = r'''
"""The shared .env file: one file for every key, in the repository folder (the folder above the project).

Reading and writing go through python-dotenv. Values already set in the environment always win.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key


def env_path(root: Path) -> Path:
    """<repository>/.env, where the repository is the folder that holds the project folder.

    PAPERKIT_ENV_FILE points somewhere else, for a setup that keeps its keys in another place.
    """
    other = os.environ.get("PAPERKIT_ENV_FILE")
    return Path(other).expanduser() if other else Path(root).resolve().parent / ".env"


def load_env(root: Path) -> list[str]:
    """Loads the variables from the shared .env and returns the names it set.

    Empty values are ignored, so an untouched copy of .env.example changes nothing.
    """
    path = env_path(root)
    if not path.is_file():
        return []
    loaded = []
    for name, value in dotenv_values(path).items():
        if name and value and not os.environ.get(name):
            os.environ[name] = value
            loaded.append(name)
    return loaded


def save_env(root: Path, name: str, value: str) -> Path:
    """Sets one variable in the shared .env, keeps its other lines, and limits the file to its owner."""
    path = env_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(path), name, value, quote_mode="never")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def gitignore_path(root: Path) -> Path:
    return env_path(root).parent / ".gitignore"


def is_ignored(root: Path) -> bool:
    """True if the repository's .gitignore already keeps .env out of git."""
    path = gitignore_path(root)
    rules = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()} if path.is_file() else set()
    return bool(rules & {".env", "/.env", "**/.env"})


def ignore(root: Path) -> Path:
    """Adds .env to the repository's .gitignore."""
    path = gitignore_path(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(text + ("\n" if text and not text.endswith("\n") else "") + ".env\n", encoding="utf-8")
    return path
'''

# ----------------------------------------------------------------------------
# src/paperkit/preflight.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/preflight.py'] = r'''
"""Input checklist: what the pipeline needs before a model is called, and whether it is there yet.

Nothing here asks questions. The start screen and the CLI both read this list,
and `plan` and `run` refuse to start while a required item is missing.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import agents, zotero
from .schemas import PaperSpec

MIN_WORDS = 30   # below this, a Methods or Results file counts as not filled in

# Lines the scaffold writes into the input files. They do not count as content.
TEMPLATE_LINES = {
    "paste the full methods section here, as it appears in the manuscript.",
    "paste the full results section here: text, tables and figure captions.",
    "three to five points the paper must get across. one per line.",
    "known limitations and assumptions: design, sample, missing data, unmeasured factors,",
    "and which model assumptions were tested and which were not.",
    "your notes for the introduction: what is known, what is not known, and what this study set out to do.",
}
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s+|$)")
DEFAULT_TITLE = "Working title"


@dataclass
class Check:
    key: str            # stable name: "methods", "facts", ...
    path: str           # where the input lives, relative to the project
    label: str
    level: str          # "required" | "recommended" | "optional"
    ok: bool
    detail: str         # what was found
    hint: str = ""      # what to put there


def content_lines(path: Path) -> list[str]:
    """Lines that carry content: no headings, no scaffold placeholders, no empty bullets."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = BULLET.sub("", line).strip()
        if text and not text.startswith("#") and text.lower() not in TEMPLATE_LINES:
            out.append(text)
    return out


def read_facts_csv(path: Path) -> list[dict]:
    """Rows of a facts CSV. Raises ValueError if the id, text and source columns are not all there."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"id", "text", "source"} <= set(reader.fieldnames or []):
            raise ValueError("needs the columns id, text, source")
        return [{k: (row.get(k) or "").strip() for k in ("id", "text", "source")} for row in reader]


def _text_check(root: Path, key: str, rel: str, label: str, hint: str) -> Check:
    path = root / rel
    if not path.is_file():
        return Check(key, rel, label, "required", False, "file is missing", hint)
    words = sum(len(line.split()) for line in content_lines(path))
    if words == 0:
        return Check(key, rel, label, "required", False, "still the placeholder text", hint)
    if words < MIN_WORDS:
        return Check(key, rel, label, "required", False, f"only {words} words", hint)
    return Check(key, rel, label, "required", True, f"{words} words", hint)


def _list_check(root: Path, key: str, rel: str, label: str, noun: str, hint: str) -> Check:
    path = root / rel
    if not path.is_file():
        return Check(key, rel, label, "required", False, "file is missing", hint)
    count = len(content_lines(path))
    return Check(key, rel, label, "required", count > 0, f"{count} {noun}(s)" if count else "nothing listed yet", hint)


def _has_section(root: Path, sec_id: str) -> bool:
    try:
        raw = yaml.safe_load((root / "paper.yaml").read_text(encoding="utf-8")) or {}
        return any(isinstance(sec, dict) and sec.get("id") == sec_id for sec in raw.get("sections", []))
    except Exception:
        return False


def _spec_checks(root: Path) -> list[Check]:
    hint = "title, study design, and each section with its required headings and word limit"
    path = root / "paper.yaml"
    if not path.is_file():
        return [Check("spec", "paper.yaml", "Paper specification", "required", False, "file is missing", hint)]
    try:
        spec = PaperSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception as exc:   # YAML syntax or schema error: report it, do not crash the checklist
        reason = " ".join(str(exc).split())[:70]
        return [Check("spec", "paper.yaml", "Paper specification", "required", False, f"not valid: {reason}", hint)]
    names = ", ".join(sec.id for sec in spec.sections)
    checks = [Check("spec", "paper.yaml", "Paper specification", "required", bool(spec.sections),
                    f"{spec.design}; sections: {names}" if spec.sections else "no sections defined", hint)]
    titled = bool(spec.title.strip()) and spec.title.strip() != DEFAULT_TITLE
    checks.append(Check("title", "paper.yaml", "Paper title", "recommended", titled,
                        spec.title if titled else "still the default title", "the real title of the paper"))
    return checks


def _facts_check(root: Path) -> Check:
    hint = "one row per number the text may use: id (F1, F2...), text as it should print, source"
    rel, path = "inputs/facts.csv", root / "inputs" / "facts.csv"
    if not path.is_file():
        return Check("facts", rel, "Facts registry", "required", False, "file is missing", hint)
    try:
        rows = read_facts_csv(path)
    except (ValueError, csv.Error, UnicodeDecodeError) as exc:
        return Check("facts", rel, "Facts registry", "required", False, f"not readable: {exc}", hint)
    examples = [r for r in rows if "EXAMPLE" in r["text"]]
    real = [r for r in rows if r not in examples]
    if not real:
        return Check("facts", rel, "Facts registry", "required", False,
                     "only the example rows" if examples else "no facts yet", hint)
    if examples:
        return Check("facts", rel, "Facts registry", "required", False,
                     f"{len(real)} fact(s), but {len(examples)} example row(s) are still there", hint)
    expected = {r["id"]: {"text": r["text"], "source": r["source"]} for r in real}
    built = root / "facts" / "facts.json"
    try:
        current = json.loads(built.read_text(encoding="utf-8")) if built.is_file() else {}
    except ValueError:
        current = None
    if current != expected:
        return Check("facts", rel, "Facts registry", "required", False,
                     f"{len(real)} fact(s), but facts/facts.json is out of date: run `paperkit facts`", hint)
    return Check("facts", rel, "Facts registry", "required", True, f"{len(real)} fact(s)", hint)


def _key_check(root: Path) -> Check:
    """A key for every provider the planner, writer and reviewer are routed to."""
    try:
        agents.configure(root)
        providers = sorted({agents.route(kind)[0] for kind in agents.PIPELINE_AGENTS})
    except (ValueError, OSError) as exc:
        reason = " ".join(str(exc).split())[:70]
        return Check("api_key", "config/models.yaml", "API key", "recommended", False,
                     f"model configuration is not valid: {reason}", "a valid config/models.yaml")
    lacking = [p for p in providers if not agents.has_key(p)]
    names = " and ".join(agents.PROVIDERS[p][0] for p in providers)
    detail = (f"no key for {', '.join(lacking)}: needed for plan and run, not for a dry run" if lacking
              else f"set ({', '.join(providers)})")
    return Check("api_key", ".env", "API key", "recommended", not lacking, detail,
                 f"{names} in the environment or in .env")


def _count(folder: Path, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns for _ in folder.glob(pattern)) if folder.is_dir() else 0


def check_inputs(root: str | Path) -> list[Check]:
    root = Path(root)
    checks = _spec_checks(root)
    checks += [
        _text_check(root, "methods", "inputs/methods.md", "Methods section",
                    "the full Methods section, as in the manuscript"),
        _text_check(root, "results", "inputs/results.md", "Results section",
                    "the full Results section: text, tables, figure captions"),
        _list_check(root, "key_messages", "inputs/key_messages.md", "Key messages", "message",
                    "three to five points the paper must get across, one per line"),
        _list_check(root, "limitations", "inputs/limitations.md", "Limitations", "item",
                    "known limitations and untested assumptions, one per line"),
        _facts_check(root),
    ]
    if _has_section(root, "introduction"):
        checks.insert(len(checks) - 1, _text_check(
            root, "introduction", "inputs/introduction.md", "Introduction notes",
            "background, knowledge gap and aim, in your own words (needs the introduction section in paper.yaml)"))
    entries = len(zotero.load_bib(root / "refs" / "library.bib"))
    checks.append(Check("bib", "refs/library.bib", "Reference library", "recommended", entries > 0,
                        f"{entries} reference(s)" if entries else "no references: nothing can be cited",
                        "Better BibTeX auto-export from Zotero, or a copy of a .bib file"))
    checks.append(_key_check(root))
    pages = [p for p in (root / "wiki").glob("*.md") if p.stem not in {"index", "SCHEMA"}] if (root / "wiki").is_dir() else []
    checks.append(Check("wiki", "wiki/", "Source pages", "optional", bool(pages),
                        f"{len(pages)} page(s)" if pages else "none: the reviewer cannot check citations",
                        "one page per cited source, named <citation key>.md"))
    if (root / ".papers").is_dir():
        pdfs = _count(root / ".papers", ("*.pdf", "*.PDF"))
        checks.append(Check("papers", ".papers/", "Source PDFs", "optional", pdfs > 0,
                            f"{pdfs} PDF(s)" if pdfs else "none", "the papers you cite, for building source pages"))
    if (root / "inputs" / "tables").is_dir():
        tables = _count(root / "inputs" / "tables", ("*.csv", "*.tsv"))
        checks.append(Check("tables", "inputs/tables/", "Result tables", "optional", tables > 0,
                            f"{tables} table file(s)" if tables else "none",
                            "CSV or TSV result tables, described in manifest.yaml"))
    return checks


def missing(checks: list[Check], level: str = "required") -> list[Check]:
    return [c for c in checks if c.level == level and not c.ok]


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def tag(check: Check) -> tuple[str, str]:
    """Status word and its ANSI colour code."""
    if check.ok:
        return "[ok]", "32"
    return {"required": ("[missing]", "31"), "recommended": ("[to do]", "33")}.get(check.level, ("[--]", "2"))


def line(check: Check, color: bool = False) -> str:
    word, code = tag(check)
    status = f"\033[{code}m{word:<10}\033[0m" if color else f"{word:<10}"
    return f"  {status}{check.path:<26}{check.label:<21}{check.detail}"


def render(checks: list[Check], color: bool = False) -> str:
    required = [c for c in checks if c.level == "required"]
    ready = sum(c.ok for c in required)
    rows = ["Inputs"] + [line(c, color) for c in checks]
    rows.append(f"Required inputs ready: {ready} of {len(required)}")
    return "\n".join(rows)
'''

# ----------------------------------------------------------------------------
# src/paperkit/dryrun.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/dryrun.py'] = r'''
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
'''

# ----------------------------------------------------------------------------
# src/paperkit/wizard.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/wizard.py'] = r'''
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

from . import agents, build, dryrun, env, extract, facts, orchestrator, preflight, zotero
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
    options = {
        "p": "import from a file (.md .txt .docx .pdf)",
        "t": "type them here, one per line" if as_list else "paste the text here",
        "e": "open the file in an editor",
        "s": "skip for now"}
    if check.key == "key_messages":
        options = {"x": "draft them from the Results section with the model (calls the API; you review them)", **options}
    choice = ui.choose("How do you want to fill it in?", options, default="s")
    if choice == "s":
        return
    if choice == "e":
        if not ui.edit(path):
            ui.out("No editor found. Set the EDITOR variable, or edit the file yourself.")
        return
    if check.ok and not ui.confirm("This replaces the current content. Continue?", False):
        return
    if choice == "x":
        draft_with_model(ui, root, "key-messages")
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
        "x": "draft them from the Results section with the model (calls the API; you review them)",
        "s": "skip for now"}, default="s")
    if choice == "s":
        return
    if choice == "x":
        if any("EXAMPLE" not in r["text"] for r in rows) and not ui.confirm("This replaces the facts now in the file. Continue?", False):
            return
        draft_with_model(ui, root, "facts")
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


def draft_with_model(ui: UI, root: Path, what: str) -> None:
    """Drafts facts.csv or key_messages.md from the Results section, then shows what was kept and what was left out."""
    if not _confirm_api(ui, "facts" if what == "facts" else "planner"):
        return
    try:
        extract.run(root, what, force=True, out=ui.out)
    except Exception as exc:      # a provider error must not close the screen
        ui.out(f"That step failed: {type(exc).__name__}: {' '.join(str(exc).split())[:300]}")


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
'''

# ----------------------------------------------------------------------------
# tests/test_start.py
# ----------------------------------------------------------------------------
FILES['tests/test_start.py'] = r'''
"""Tests for the start screen: the input checklist, the guided fill-in, the dry run and the CLI gate.

No network and no terminal: the prompts are answered from a list.
"""
import json
import os
import stat

import pytest

from paperkit import agents, dryrun, env, extract, orchestrator, preflight, wizard
from paperkit.__main__ import main
from paperkit.schemas import Claim, ClaimTable
from paperkit.validators import blocking, check_claims, run_gates

SPEC = """title: "Working title"
design: observational        # observational | experimental
max_rounds: 3
sections:
  - id: discussion
    title: Discussion
    max_words: 300
    required_headings: [Principal findings, Limitations, Conclusion]
"""
PLACEHOLDERS = {
    "inputs/methods.md": "# Methods\n\nPaste the full Methods section here, as it appears in the manuscript.\n",
    "inputs/results.md": "# Results\n\nPaste the full Results section here: text, tables and figure captions.\n",
    "inputs/key_messages.md": "# Key messages\n\nThree to five points the paper must get across. One per line.\n\n- \n",
    "inputs/limitations.md": "# Limitations and assumptions\n\nKnown limitations and assumptions: design, sample, "
                             "missing data, unmeasured factors,\nand which model assumptions were tested and "
                             "which were not.\n\n- \n",
    "inputs/facts.csv": 'id,text,source\nF1,"EXAMPLE r = 0.00, 95% CI [0.00, 0.00]",Table 0\n',
    "facts/facts.json": "{}\n",
    "refs/library.bib": "% Better BibTeX auto-export from Zotero writes here.\n",
}
BIB = "@article{smith2020,\n  title = {A study},\n  author = {Smith, A.},\n  year = {2020},\n}\n"
LONG = " ".join(["word"] * 40)


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """A project exactly as the scaffold leaves it: every input is still a placeholder.

    It sits in tmp_path/repo/project like the real layout: the shared .env and .gitignore are in repo/.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")           # empty counts as not set, and is restored afterwards
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "")
    monkeypatch.setenv("PAPERKIT_PROVIDER", "")           # the tests assume the default provider
    monkeypatch.setenv("PAPERKIT_MODEL", "")
    monkeypatch.setenv("PAPERKIT_ENV_FILE", "")
    repo = tmp_path / "repo"
    project = repo / "project"
    project.mkdir(parents=True)
    (repo / ".gitignore").write_text(".env\n.cache/\n", encoding="utf-8")
    (project / "paper.yaml").write_text(SPEC, encoding="utf-8")
    for rel, text in PLACEHOLDERS.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    yield project
    agents.LLM = None
    agents.CONFIG = {}


def scripted(answers):
    """A UI that answers prompts from a list and collects everything it prints."""
    feed, printed = iter(answers), []
    ui = wizard.UI(ask=lambda prompt="": next(feed), out=lambda text="": printed.append(str(text)),
                   secret=lambda prompt="": next(feed), edit=lambda path: True, color=False)
    return ui, printed


def fill_all(root):
    (root / "inputs" / "methods.md").write_text(f"# Methods\n\n{LONG}\n", encoding="utf-8")
    (root / "inputs" / "results.md").write_text(f"# Results\n\n{LONG}\n", encoding="utf-8")
    (root / "inputs" / "key_messages.md").write_text("# Key messages\n\n- X tracks Y\n", encoding="utf-8")
    (root / "inputs" / "limitations.md").write_text("# Limitations\n\n- Cross-sectional\n", encoding="utf-8")
    (root / "inputs" / "facts.csv").write_text("id,text,source\nF1,r = 0.31,Table 2\nF2,n = 412,Methods\n",
                                               encoding="utf-8")
    assert main(["--root", str(root), "facts"]) == 0
    (root / "refs" / "library.bib").write_text(BIB, encoding="utf-8")


def status(root):
    return {c.key: c.ok for c in preflight.check_inputs(root)}


def test_fresh_project_has_nothing_ready(fresh):
    got = status(fresh)
    assert got["spec"] is True
    for key in ["title", "methods", "results", "key_messages", "limitations", "facts", "bib", "api_key"]:
        assert got[key] is False, key
    assert main(["--root", str(fresh), "check"]) == 1


def test_filled_project_is_ready_and_stale_facts_are_caught(fresh):
    fill_all(fresh)
    assert preflight.missing(preflight.check_inputs(fresh)) == []
    assert main(["--root", str(fresh), "check"]) == 0
    with (fresh / "inputs" / "facts.csv").open("a", encoding="utf-8") as f:
        f.write("F3,p = 0.04,Table 2\n")                      # CSV changed, facts.json did not
    facts_check = next(c for c in preflight.check_inputs(fresh) if c.key == "facts")
    assert not facts_check.ok and "out of date" in facts_check.detail


def test_guided_fill_writes_every_required_input(fresh, tmp_path):
    source = tmp_path / "methods_source.md"
    source.write_text(f"# Methods\n\n{LONG}\n", encoding="utf-8")
    ui, printed = scripted([
        "y",                                              # fill in the required inputs now?
        "p", str(source),                                 # methods: import from a file
        "t", LONG, "second line", ".",                    # results: paste
        "t", "X tracks Y", "- Y is stable", ".",          # key messages: one per line
        "t", "Cross-sectional design", ".",               # limitations
        "a", "r = 0.31, 95% CI [0.22, 0.40]", "Table 2", "n = 412", "Methods 2.1", "",   # facts
        "n",                                              # recommended items: not now
        "q",                                              # menu: quit
    ])
    assert wizard.start(fresh, ui) == 0
    assert preflight.missing(preflight.check_inputs(fresh)) == []
    assert (fresh / "inputs" / "methods.md").read_text(encoding="utf-8").count("# Methods") == 1
    assert "- Y is stable" in (fresh / "inputs" / "key_messages.md").read_text(encoding="utf-8")
    built = json.loads((fresh / "facts" / "facts.json").read_text(encoding="utf-8"))
    assert built == {"F1": {"text": "r = 0.31, 95% CI [0.22, 0.40]", "source": "Table 2"},
                     "F2": {"text": "n = 412", "source": "Methods 2.1"}}
    assert "EXAMPLE" not in (fresh / "inputs" / "facts.csv").read_text(encoding="utf-8")


def test_recommended_items_title_library_and_key(fresh, tmp_path):
    fill_all(fresh)
    (fresh / "refs" / "library.bib").write_text("% empty\n", encoding="utf-8")
    bib = tmp_path / "export.bib"
    bib.write_text(BIB, encoding="utf-8")
    ui, printed = scripted([
        "y",                                              # set up the recommended items?
        "Brain and cognition", "o", "n",                  # title, design, do not open the editor
        "i", str(bib),                                    # copy a .bib file in
        "k", "sk-test-not-a-real-key",                    # save the key
        "q",
    ])
    assert wizard.start(fresh, ui) == 0
    got = status(fresh)
    assert got["title"] and got["bib"] and got["api_key"]
    spec_text = (fresh / "paper.yaml").read_text(encoding="utf-8")
    assert 'title: "Brain and cognition"' in spec_text and "# observational | experimental" in spec_text
    assert "ANTHROPIC_API_KEY=sk-test-not-a-real-key" in (fresh.parent / ".env").read_text(encoding="utf-8")
    assert not (fresh / ".env").exists()                       # keys never go inside the project
    assert not any("sk-test" in row for row in printed)       # the key is never echoed


def test_leaving_at_any_prompt_is_clean(fresh):
    ui, printed = scripted([])                             # Ctrl-D at the first question
    assert wizard.start(fresh, ui) == 0
    assert printed[-1].strip() == "Bye."


def test_dry_run_passes_and_leaves_the_project_alone(fresh):
    fill_all(fresh)
    result = dryrun.dry_run(fresh)
    assert result["sections"] == {"discussion": "DONE"} and dryrun.passed(result)
    assert result["facts"] == 2 and result["references"] == 1
    text = result["paper"].read_text(encoding="utf-8")
    assert "r = 0.31" in text and "{{" not in text
    assert not (fresh / "state").exists() and not (fresh / "drafts").exists() and not (fresh / "build").exists()
    assert agents.LLM is None
    assert main(["--root", str(fresh), "dry-run"]) == 0


def test_dry_run_uses_a_real_claim_table_and_reports_a_bad_one(fresh):
    fill_all(fresh)
    p = orchestrator.Project(fresh)
    good = ClaimTable(section_id="discussion", claims=[
        Claim(id="C1", text="X is associated with Y.", category="OBSERVED", fact_ids=["F1", "F2"]),
        Claim(id="C2", text="X tracks Y.", category="INFERRED", fact_ids=["F1"], cite_keys=["smith2020"]),
        Claim(id="C3", text="Error is unrelated to Y.", category="ASSUMED"),
        Claim(id="C4", text="Longitudinal data may differ.", category="SPECULATIVE"),
    ])
    p.save_claims(good)
    result = dryrun.dry_run(fresh)
    assert result["sections"] == {"discussion": "DONE"} and result["planned"] == []
    assert p.load_claims("discussion").approved is False      # only the scratch copy was approved

    p.save_claims(ClaimTable(section_id="discussion", claims=[
        Claim(id="C1", text="Uses a fact that does not exist.", category="OBSERVED", fact_ids=["F99"])]))
    result = dryrun.dry_run(fresh)
    assert result["sections"] == {"discussion": "CLAIMS_INVALID"}
    assert "F99" in " ".join(result["issues"]["discussion"])


def test_stand_in_draft_passes_every_gate(fresh):
    fill_all(fresh)
    agents.LLM = dryrun.stand_in
    p = orchestrator.Project(fresh)
    table, issues = orchestrator.plan(p, "discussion")
    assert issues == [] and blocking(check_claims(table, p.facts, set(p.bib))) == []
    draft = agents.write_section(p.spec.section("discussion"), design="observational", claims=table.claims,
                                 fact_reg=p.facts, wiki_pages={})
    assert run_gates(draft, p.ctx("discussion", table)) == []


def test_plan_and_run_refuse_to_call_the_model_without_inputs(fresh, capsys):
    def boom(*args):
        raise AssertionError("the model must not be called")

    agents.LLM = boom
    assert main(["--root", str(fresh), "plan", "discussion"]) == 1
    assert main(["--root", str(fresh), "run", "discussion"]) == 1
    assert "Required inputs are missing" in capsys.readouterr().out
    assert not (fresh / "state").exists()

SPEC_TWO = """title: "Working title"
design: observational
max_rounds: 3
sections:
  - id: introduction
    title: Introduction
    max_words: 300
    required_headings: [Background, Knowledge gap, Aim]
  - id: discussion
    title: Discussion
    max_words: 300
    required_headings: [Principal findings, Limitations, Conclusion]
"""


def test_introduction_notes_are_checked_only_when_the_section_exists(fresh):
    assert "introduction" not in status(fresh)
    (fresh / "paper.yaml").write_text(SPEC_TWO, encoding="utf-8")
    (fresh / "inputs" / "introduction.md").write_text(
        "# Introduction notes\n\nYour notes for the Introduction: what is known, what is not known, "
        "and what this study set out to do.\n\n## Background\n\n- \n", encoding="utf-8")
    assert status(fresh)["introduction"] is False                 # still the placeholder text
    (fresh / "inputs" / "introduction.md").write_text(f"# Introduction notes\n\n{LONG}\n", encoding="utf-8")
    assert status(fresh)["introduction"] is True


def test_dry_run_writes_the_introduction_and_the_discussion(fresh):
    fill_all(fresh)
    (fresh / "paper.yaml").write_text(SPEC_TWO, encoding="utf-8")
    (fresh / "inputs" / "introduction.md").write_text(f"# Introduction notes\n\n{LONG}\n", encoding="utf-8")
    result = dryrun.dry_run(fresh)
    assert result["sections"] == {"introduction": "DONE", "discussion": "DONE"} and dryrun.passed(result)
    text = result["paper"].read_text(encoding="utf-8")
    assert text.index("## Background") < text.index("## Principal findings")


def test_keys_are_read_from_the_env_file_one_folder_up(fresh, monkeypatch):
    (fresh.parent / ".env").write_text(
        "# keys\nNVIDIA_API_KEY=nvapi-from-file\nANTHROPIC_API_KEY=\nPAPERKIT_MODEL='z-ai/glm-5.3'\n", encoding="utf-8")
    (fresh / ".env").write_text("NVIDIA_API_KEY=nvapi-inside-the-project\n", encoding="utf-8")   # never read
    monkeypatch.setenv("NVIDIA_API_KEY", "")                       # restored (removed) after the test
    assert sorted(env.load_env(fresh)) == ["NVIDIA_API_KEY", "PAPERKIT_MODEL"]     # the empty value is skipped
    assert os.environ["NVIDIA_API_KEY"] == "nvapi-from-file" and os.environ["PAPERKIT_MODEL"] == "z-ai/glm-5.3"
    monkeypatch.setenv("NVIDIA_API_KEY", "from-the-shell")
    assert env.load_env(fresh) == [] and os.environ["NVIDIA_API_KEY"] == "from-the-shell"


def test_saving_a_key_keeps_the_other_lines_and_limits_the_file(fresh):
    target = fresh.parent / ".env"
    target.write_text("GITHUB_USER=alex\nNVIDIA_API_KEY=\n", encoding="utf-8")
    env.save_env(fresh, "NVIDIA_API_KEY", "nvapi-x")
    env.save_env(fresh, "PAPERKIT_PROVIDER", "nvidia")
    assert target.read_text(encoding="utf-8").splitlines() == [
        "GITHUB_USER=alex", "NVIDIA_API_KEY=nvapi-x", "PAPERKIT_PROVIDER=nvidia"]
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not (fresh / ".env").exists()


def test_saving_a_key_adds_env_to_the_repository_gitignore(fresh):
    (fresh.parent / ".gitignore").unlink()
    ui, printed = scripted([])
    wizard.save_setting(ui, fresh, "NVIDIA_API_KEY", "nvapi-x")
    assert ".env" in (fresh.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert not (fresh / ".env").exists() and not (fresh / ".gitignore").exists()
    assert any(".gitignore" in row for row in printed)


def test_cli_finds_the_project_from_the_repository_folder(fresh, capsys):
    assert main(["--root", str(fresh.parent), "status"]) == 0
    assert "discussion: NEW" in capsys.readouterr().out
    assert main(["--root", str(fresh.parent), "check"]) == 1           # the placeholders are still there


RESULTS_TEXT = """# Results

We found a positive association between X and Y (r = 0.31, 95% CI [0.22, 0.40]) among n = 412 participants in the sample.
The association was similar after adjustment for age (r = 0.29, 95% CI [0.20, 0.38]) and weaker in the younger group.
"""


def fake_model(facts=(), messages=()):
    """A model that answers the two drafting requests with prepared text."""
    def llm(system, user, schema):
        if schema is extract.FactList:
            return extract.FactList(facts=list(facts))
        if schema is extract.MessageList:
            return extract.MessageList(messages=list(messages))
        raise AssertionError(schema)
    return llm


def test_facts_are_drafted_only_from_text_that_is_really_there(fresh):
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    agents.LLM = fake_model(facts=["r = 0.31, 95% CI [0.22, 0.40]", "n = 412", "r  =  0.29", "n = 412",
                                   "r = 0.99, invented", "no number here"])
    got = extract.extract_facts(fresh)
    assert [(r["id"], r["text"], r["source"]) for r in got["rows"]] == [
        ("F1", "r = 0.31, 95% CI [0.22, 0.40]", "Results, line 3"),
        ("F2", "n = 412", "Results, line 3"),
        ("F3", "r = 0.29", "Results, line 4")]
    assert got["dropped"] == ["r = 0.99, invented", "no number here"]
    assert json.loads((fresh / "facts" / "facts.json").read_text(encoding="utf-8"))["F3"]["text"] == "r = 0.29"
    assert status(fresh)["facts"] is True


def test_real_facts_and_messages_are_never_replaced_unless_forced(fresh):
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    (fresh / "inputs" / "facts.csv").write_text("id,text,source\nF1,r = 0.31,Table 2\n", encoding="utf-8")
    (fresh / "inputs" / "key_messages.md").write_text("# Key messages\n\n- X tracks Y\n", encoding="utf-8")
    agents.LLM = fake_model(facts=["n = 412"], messages=["Y varies by age group."])
    with pytest.raises(extract.Skip):
        extract.extract_facts(fresh)
    with pytest.raises(extract.Skip):
        extract.extract_key_messages(fresh)
    assert "r = 0.31" in (fresh / "inputs" / "facts.csv").read_text(encoding="utf-8")
    extract.extract_facts(fresh, force=True)
    assert "r = 0.31" not in (fresh / "inputs" / "facts.csv").read_text(encoding="utf-8")


def test_nothing_is_drafted_from_a_placeholder_results_section(fresh):
    def boom(*args):
        raise AssertionError("the model must not be called")

    agents.LLM = boom
    with pytest.raises(ValueError, match="results.md"):
        extract.extract_facts(fresh)
    with pytest.raises(ValueError, match="results.md"):
        extract.extract_key_messages(fresh)


def test_key_messages_drop_digits_and_causal_wording(fresh):
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    agents.LLM = fake_model(messages=["X is associated with Y in this sample.", "The correlation is 0.31 overall.",
                                      "X causes Y.", "- Y varies by age group.", "X is associated with Y in this sample."])
    got = extract.extract_key_messages(fresh)
    assert got["messages"] == ["X is associated with Y in this sample.", "Y varies by age group."]
    assert [d.split(" (")[1] for d in got["dropped"]] == ["has a digit)", "causal wording in an observational study)"]
    assert len(preflight.content_lines(fresh / "inputs" / "key_messages.md")) == 2
    assert status(fresh)["key_messages"] is True


def test_extract_command_drafts_both_files(fresh, capsys):
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    agents.LLM = fake_model(facts=["n = 412"], messages=["Y varies by age group."])
    assert main(["--root", str(fresh), "extract"]) == 0
    out = capsys.readouterr().out
    assert "F1   n = 412   (Results, line 3)" in out and "Read both files" in out
    assert main(["--root", str(fresh), "extract"]) == 0                  # both are real now: skipped, not an error
    assert out.count("skipped") == 0 and capsys.readouterr().out.count("skipped") == 2


def test_start_screen_offers_to_draft_facts_and_messages(fresh):
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    agents.LLM = fake_model(facts=["n = 412"], messages=["Y varies by age group."])
    checks = {c.key: c for c in preflight.check_inputs(fresh)}
    ui, printed = scripted(["x", "y"])                                   # draft them, and yes to the API call
    wizard.fill(ui, fresh, checks["facts"])
    ui, printed = scripted(["x", "y"])
    wizard.fill(ui, fresh, checks["key_messages"])
    assert status(fresh)["facts"] is True and status(fresh)["key_messages"] is True
    assert any("a model drafted them" in row for row in printed)

'''

# ----------------------------------------------------------------------------
# Model providers: routing per agent, and NVIDIA's OpenAI-compatible endpoint
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# src/paperkit/nvidia.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/nvidia.py'] = r'''
"""NVIDIA hosted models (build.nvidia.com) and self-hosted NIM, through the OpenAI-compatible chat endpoint.

Standard library only, so there is no extra dependency. Two things differ from the Anthropic path:
- the free hosted endpoints are rate limited, so HTTP 429 and 5xx are retried after a wait;
- open models do not always honour a JSON schema, so every answer is validated here and the model
  gets a chance to repair it. Schema-guided decoding is requested first and dropped for a model
  whose endpoint rejects it.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ValidationError

BASE_URL = "https://integrate.api.nvidia.com/v1"    # override with NVIDIA_BASE_URL for a local NIM
REPAIRS = 2                     # extra attempts when an answer does not fit the schema
BACKOFF = (2, 5, 15, 30)        # seconds to wait after HTTP 429 or 5xx, one entry per retry
TIMEOUT = 300
RETRYABLE = {429, 500, 502, 503, 504}
HINTS = {
    401: "the key was rejected: check NVIDIA_API_KEY",
    403: "this key has no access to the model",
    404: "model not found: copy the model ID from its page on build.nvidia.com",
    429: "rate limit reached: wait a minute and try again",
}
_NO_GUIDED: set[str] = set()    # models whose endpoint rejected nvext.guided_json


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def post(url: str, key: str, body: dict) -> dict:
    """POSTs JSON and returns the decoded answer. Waits and retries on rate limits and server errors."""
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    for wait in (*BACKOFF, None):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:300]
            if exc.code in RETRYABLE and wait is not None:
                asked = exc.headers.get("Retry-After", "")
                time.sleep(min(float(asked), 60) if asked.replace(".", "", 1).isdigit() else wait)
                continue
            raise ApiError(exc.code, detail) from None
        except urllib.error.URLError as exc:
            raise ApiError(0, f"cannot reach {url}: {exc.reason}") from None
    raise ApiError(0, "no answer")      # not reached: the last round always returns or raises


def extract_json(text: str) -> str:
    """The JSON object inside a model answer. Reasoning blocks, code fences and chatter are dropped."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text.strip()


def call(system: str, user: str, schema: type[BaseModel], model: str, max_tokens: int = 8000) -> BaseModel:
    """One request with no history, answered as a validated instance of `schema`."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set. Get a key at build.nvidia.com and put it in .env.")
    url = (os.environ.get("NVIDIA_BASE_URL") or BASE_URL).rstrip("/") + "/chat/completions"
    json_schema = schema.model_json_schema()
    messages = [
        {"role": "system", "content": f"{system}\n\nAnswer with one JSON object and nothing else. "
                                      f"It must be valid for this JSON schema:\n{json.dumps(json_schema)}"},
        {"role": "user", "content": user},
    ]
    problem, attempts = "", 0
    while attempts <= REPAIRS:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2, "stream": False}
        guided = model not in _NO_GUIDED and os.environ.get("PAPERKIT_GUIDED_JSON", "1") != "0"
        if guided:
            body["nvext"] = {"guided_json": json_schema}
        try:
            data = post(url, key, body)
        except ApiError as exc:
            if guided and exc.status in (400, 422):
                _NO_GUIDED.add(model)   # this endpoint does not take guided_json: rely on the prompt and on validation
                continue
            raise RuntimeError(f"NVIDIA API, model {model}: {HINTS.get(exc.status, exc)}") from None
        attempts += 1
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("Answer was cut off: raise PAPERKIT_MAX_TOKENS")
        text = (choice.get("message") or {}).get("content") or ""
        try:
            return schema.model_validate_json(extract_json(text))
        except ValidationError as exc:
            problem = " ".join(str(exc).split())[:600]
            messages = messages[:2] + [
                {"role": "assistant", "content": text[:6000] or "(empty answer)"},
                {"role": "user", "content": f"That answer is not valid for the schema: {problem}\n"
                                            "Return only the corrected JSON object."},
            ]
    raise RuntimeError(f"{model} gave no valid {schema.__name__} after {REPAIRS + 1} attempts: {problem}")
'''

# ----------------------------------------------------------------------------
# tests/test_providers.py
# ----------------------------------------------------------------------------
FILES['tests/test_providers.py'] = r'''
"""Tests for model routing and for the NVIDIA provider. No network: the endpoint is replaced or served locally."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from paperkit import agents, dryrun, nvidia, orchestrator, preflight, wizard
from paperkit.__main__ import main
from paperkit.schemas import ClaimList, Draft, Review

SPEC = """title: Test paper
design: observational
max_rounds: 3
sections:
  - id: discussion
    title: Discussion
    max_words: 300
    required_headings: [Principal findings, Limitations, Conclusion]
"""
BIB = "@article{smith2020,\n  title = {A study},\n  author = {Smith, A.},\n  year = {2020},\n}\n"
SCHEMAS = {"ClaimList": ClaimList, "Draft": Draft, "Review": Review, "Ping": agents.Ping}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """The project sits in tmp_path/repo/project; the shared .env and .gitignore are in repo/."""
    for name in ["PAPERKIT_PROVIDER", "PAPERKIT_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                 "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "PAPERKIT_GUIDED_JSON", "PAPERKIT_ENV_FILE"]:
        monkeypatch.setenv(name, "")                       # empty counts as not set, and is restored afterwards
    monkeypatch.setattr(nvidia, "BACKOFF", (0, 0))
    nvidia._NO_GUIDED.clear()
    root = tmp_path / "repo" / "project"
    for folder in ["facts", "refs", "inputs", "config"]:
        (root / folder).mkdir(parents=True)
    (root / "paper.yaml").write_text(SPEC, encoding="utf-8")
    (root / "facts" / "facts.json").write_text(json.dumps({"F1": {"text": "r = 0.31", "source": "Table 2"}}),
                                               encoding="utf-8")
    (root / "refs" / "library.bib").write_text(BIB, encoding="utf-8")
    (root.parent / ".gitignore").write_text(".env\n", encoding="utf-8")
    yield root
    agents.LLM = None
    agents.CONFIG = {}


def answer(text: str, finish: str = "stop") -> dict:
    """An OpenAI-format chat completion that carries `text`."""
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}


def stand_in_endpoint(calls: list):
    """A fake NVIDIA endpoint: answers each request with the dry-run stand-in, as JSON text."""
    def post(url, key, body):
        calls.append((url, key, body))
        schema = SCHEMAS[body["nvext"]["guided_json"]["title"]]
        if schema is agents.Ping:
            return answer('{"ok": true}')
        return answer(dryrun.stand_in("", body["messages"][1]["content"], schema).model_dump_json())
    return post


# --------------------------------------------------------------------- routing

def test_default_route_is_anthropic(project):
    agents.configure(project)
    assert agents.route("writer") == ("anthropic", "claude-sonnet-5-5")


def test_environment_switches_provider_and_model(project, monkeypatch):
    agents.configure(project)
    monkeypatch.setenv("PAPERKIT_PROVIDER", "nvidia")
    assert agents.route("writer") == ("nvidia", agents.PROVIDERS["nvidia"][1])
    monkeypatch.setenv("PAPERKIT_MODEL", "meta/some-model")
    assert agents.route("planner") == ("nvidia", "meta/some-model")


def test_config_file_can_mix_providers_per_agent(project, monkeypatch):
    (project / "config" / "models.yaml").write_text(
        "provider: nvidia\nagents:\n  writer: {model: nvidia/model-a}\n"
        "  reviewer: {provider: anthropic, model: claude-x}\n  planner: {model: null}\n", encoding="utf-8")
    agents.configure(project)
    assert agents.route("writer") == ("nvidia", "nvidia/model-a")
    assert agents.route("reviewer") == ("anthropic", "claude-x")
    assert agents.route("planner") == ("nvidia", agents.PROVIDERS["nvidia"][1])
    monkeypatch.setenv("PAPERKIT_MODEL", "nvidia/model-b")      # the default model of the default provider only
    assert agents.route("planner") == ("nvidia", "nvidia/model-b")
    assert agents.route("reviewer") == ("anthropic", "claude-x")


def test_unknown_provider_and_broken_file_are_reported(project):
    (project / "config" / "models.yaml").write_text("provider: openai\n", encoding="utf-8")
    agents.configure(project)
    with pytest.raises(ValueError, match="Unknown provider 'openai'"):
        agents.route("writer")
    assert main(["--root", str(project), "ping"]) == 2
    (project / "config" / "models.yaml").write_text("provider: [unclosed\n", encoding="utf-8")
    key_check = next(c for c in preflight.check_inputs(project) if c.key == "api_key")
    assert not key_check.ok and "not valid" in key_check.detail


def test_key_check_follows_the_provider(project, monkeypatch):
    monkeypatch.setenv("PAPERKIT_PROVIDER", "nvidia")
    key_check = next(c for c in preflight.check_inputs(project) if c.key == "api_key")
    assert not key_check.ok and "nvidia" in key_check.detail and "NVIDIA_API_KEY" in key_check.hint
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert next(c for c in preflight.check_inputs(project) if c.key == "api_key").ok


# ------------------------------------------------------------- nvidia.call

def test_call_sends_an_openai_request_and_parses_a_messy_answer(project, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    seen = []

    def post(url, key, body):
        seen.append((url, key, body))
        return answer('<think>Let me think {about} this.</think>\nHere you go:\n```json\n{"markdown": "Hello"}\n```')

    monkeypatch.setattr(nvidia, "post", post)
    out = nvidia.call("SYSTEM", "USER", Draft, "nvidia/some-model", max_tokens=123)
    assert out == Draft(markdown="Hello")
    url, key, body = seen[0]
    assert url == "https://integrate.api.nvidia.com/v1/chat/completions" and key == "nvapi-test"
    assert body["model"] == "nvidia/some-model" and body["max_tokens"] == 123 and body["stream"] is False
    assert body["nvext"]["guided_json"]["title"] == "Draft"
    assert body["messages"][0]["role"] == "system" and body["messages"][0]["content"].startswith("SYSTEM")
    assert '"markdown"' in body["messages"][0]["content"]          # the schema is also in the prompt
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_guided_json_is_dropped_when_the_endpoint_rejects_it(project, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    bodies = []

    def post(url, key, body):
        bodies.append(body)
        if "nvext" in body:
            raise nvidia.ApiError(400, "extra fields not permitted")
        return answer('{"markdown": "ok"}')

    monkeypatch.setattr(nvidia, "post", post)
    assert nvidia.call("s", "u", Draft, "m1").markdown == "ok"
    assert nvidia.call("s", "u", Draft, "m1").markdown == "ok"
    assert ["nvext" in body for body in bodies] == [True, False, False]     # remembered for this model


def test_invalid_answers_are_repaired_then_given_up_on(project, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    replies = iter(["not json at all", '{"wrong": 1}', '{"markdown": "third time"}'])
    bodies = []

    def post(url, key, body):
        bodies.append(body)
        return answer(next(replies))

    monkeypatch.setattr(nvidia, "post", post)
    assert nvidia.call("s", "u", Draft, "m").markdown == "third time"
    assert len(bodies[2]["messages"]) == 4 and "not valid for the schema" in bodies[2]["messages"][3]["content"]

    monkeypatch.setattr(nvidia, "post", lambda url, key, body: answer("still not json"))
    with pytest.raises(RuntimeError, match="no valid Draft after 3 attempts"):
        nvidia.call("s", "u", Draft, "m")


def test_missing_key_cut_off_answer_and_error_hints(project, monkeypatch):
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY is not set"):
        nvidia.call("s", "u", Draft, "m")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(nvidia, "post", lambda url, key, body: answer('{"markdown": "cut', "length"))
    with pytest.raises(RuntimeError, match="cut off"):
        nvidia.call("s", "u", Draft, "m")

    def not_found(url, key, body):
        raise nvidia.ApiError(404, "Not Found")

    monkeypatch.setattr(nvidia, "post", not_found)
    with pytest.raises(RuntimeError, match="model not found"):
        nvidia.call("s", "u", Draft, "m")


# ------------------------------------------------- the real HTTP path, locally

def test_post_over_http_retries_a_rate_limit(project, monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, self.headers["Authorization"], body["model"]))
            if len(seen) == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
            status = 404 if body["model"] == "missing/model" else 200
            payload = json.dumps(answer('{"markdown": "over http"}')).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1/")
        assert nvidia.call("s", "u", Draft, "nvidia/model").markdown == "over http"
        assert [row[0] for row in seen] == ["/v1/chat/completions"] * 2          # 429, then the retry
        assert seen[0][1] == "Bearer nvapi-test"
        with pytest.raises(RuntimeError, match="model not found"):
            nvidia.call("s", "u", Draft, "missing/model")
    finally:
        server.shutdown()


# ----------------------------------------- the whole pipeline through nvidia

def test_pipeline_runs_through_the_nvidia_provider(project, monkeypatch):
    monkeypatch.setenv("PAPERKIT_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    calls = []
    monkeypatch.setattr(nvidia, "post", stand_in_endpoint(calls))
    agents.configure(project)
    p = orchestrator.Project(project)

    table, issues = orchestrator.plan(p, "discussion")
    assert issues == [] and len(table.claims) == 3
    assert orchestrator.approve(p, "discussion") == []
    assert orchestrator.run_section(p, "discussion") == "DONE"
    assert [body["nvext"]["guided_json"]["title"] for _, _, body in calls] == ["ClaimList", "Draft", "Review"]
    assert {body["model"] for _, _, body in calls} == {agents.PROVIDERS["nvidia"][1]}
    logged = [json.loads(f.read_text(encoding="utf-8"))["model"] for f in (project / "state" / "log").glob("*.json")]
    assert logged and all(name.startswith("nvidia:") for name in logged)


def test_ping_reports_each_model(project, monkeypatch, capsys):
    (project / "config" / "models.yaml").write_text(
        "provider: nvidia\nagents:\n  reviewer: {model: other/model}\n", encoding="utf-8")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(nvidia, "post", stand_in_endpoint([]))
    assert main(["--root", str(project), "ping"]) == 0
    out = capsys.readouterr().out
    assert "(planner, writer): ok" in out and "other/model  (reviewer): ok" in out

    def refuse(url, key, body):
        raise nvidia.ApiError(401, "Unauthorized")

    monkeypatch.setattr(nvidia, "post", refuse)
    assert main(["--root", str(project), "ping"]) == 1
    assert "the key was rejected" in capsys.readouterr().out


def test_menu_switches_to_nvidia_saves_the_key_and_pings(project, monkeypatch):
    monkeypatch.setattr(nvidia, "post", stand_in_endpoint([]))
    feed, printed = iter(["n", "", "k", "nvapi-secret", "y"]), []
    ui = wizard.UI(ask=lambda prompt="": next(feed), out=lambda text="": printed.append(str(text)),
                   secret=lambda prompt="": next(feed), edit=lambda path: True, color=False)
    wizard.act_models(ui, project)
    saved = (project.parent / ".env").read_text(encoding="utf-8")
    assert "PAPERKIT_PROVIDER=nvidia" in saved and "NVIDIA_API_KEY=nvapi-secret" in saved
    assert f"PAPERKIT_MODEL={agents.PROVIDERS['nvidia'][1]}" in saved
    assert agents.route("writer")[0] == "nvidia"
    assert printed[-1] == "All models answered." and not any("nvapi-secret" in row for row in printed)
'''


FILES['src/paperkit/extract.py'] = r'''
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
'''


ENV_TEXT = """# GitHub (used by publish.sh)
GITHUB_USER=
GITHUB_TOKEN=
VISIBILITY=private

# Model providers (used by paperkit)
NVIDIA_API_KEY=
ANTHROPIC_API_KEY=

# Optional: one provider and model for every agent, instead of config/models.yaml
# PAPERKIT_PROVIDER=nvidia
# PAPERKIT_MODEL=z-ai/glm-5.3
"""

# Repository-wide ignore rules. A rule without a leading slash applies at any depth.
IGNORE_RULES = [
    ".env", ".venv/", "__pycache__/", "*.egg-info/", ".pytest_cache/",
    ".DS_Store", "Thumbs.db", "~$*",
    "build/", "state/log/", ".papers/", ".writing_guides/", ".cache/",
    "inputs/", "drafts/", "state/", "facts/", 
]


def setup_repository_files(root: Path) -> None:
    """Creates .env, .env.example and .gitignore in the folder ABOVE the project, the repository folder.

    Nothing is overwritten. A missing ignore rule is appended to an existing .gitignore.
    """
    repo = root.resolve().parent
    if repo in (Path.home(), Path(repo.anchor)):
        print(f"skip    ../.env, ../.env.example, ../.gitignore: {repo} is not a project folder")
        return
    for name in (".env", ".env.example"):
        path = repo / name
        if path.exists():
            print(f"skip    ../{name}")
            continue
        path.write_text(ENV_TEXT, encoding="utf-8")
        if name == ".env":
            path.chmod(0o600)                                # keys: readable by the owner only
        print(f"create  ../{name}")
    ignore = repo / ".gitignore"
    if not ignore.exists():
        ignore.write_text("# Keys and local clutter stay out of the repository, at any depth.\n"
                          + "\n".join(IGNORE_RULES) + "\n", encoding="utf-8")
        print("create  ../.gitignore")
        return
    have = {line.strip() for line in ignore.read_text(encoding="utf-8").splitlines()}
    missing = [rule for rule in IGNORE_RULES if rule not in have]
    if missing:
        with ignore.open("a", encoding="utf-8") as f:
            f.write("\n# Added by scaffold.py\n" + "\n".join(missing) + "\n")
        print(f"update  ../.gitignore: added {', '.join(missing)}")
    else:
        print("skip    ../.gitignore")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--git" in args:
        print("--git was removed: the folder above the project is the one repository (see publish.sh).")
        args.remove("--git")
    update_code = "--update-code" in args
    names = [a for a in args if not a.startswith("--")]
    root = Path(names[0] if names else "paper-project")

    for rel in EMPTY_DIRS:
        folder = root / rel
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitkeep").touch()
    for rel, content in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            is_code = rel.startswith(("src/", "tests/"))
            if update_code and is_code and path.read_text(encoding="utf-8") != content[1:]:
                path.write_text(content[1:], encoding="utf-8")
                print(f"update  {rel}")
            else:
                print(f"skip    {rel}")
            continue
        path.write_text(content[1:], encoding="utf-8")   # [1:] drops the newline after the opening quotes
        print(f"create  {rel}")

    setup_repository_files(root)
    print(f"\nDone: {root}\nNext: bash setup.sh in {root.resolve().parent} installs the packages "
          "(it is what calls this script); then activate the environment and run: paperkit start")
    return 0


if __name__ == "__main__":
    sys.exit(main())