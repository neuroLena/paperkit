#!/usr/bin/env python3
"""Creates the paperkit scaffold: the folder structure and the minimal content of every file.

    python scaffold.py my-paper          # create the project in the folder my-paper
    python scaffold.py my-paper --update-code   # refresh src/, tests/, README.md and docs/ in an existing project

The folder that holds this script is the one git repository. Next to the project, in that folder,
the scaffold also creates .env (all keys, mode 600), .env.example and .gitignore. They are never
created inside the project, and the project has no .git folder of its own.

Needs only Python 3.10+. Existing files are never overwritten, with one exception:
--update-code rewrites the files under src/ and tests/, README.md and the files under docs/ that differ from
this scaffold: the code and the documentation that describes it. Inputs, state, drafts, rules, config and
paper.yaml are never touched.
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

Writes the sections of a scientific paper from finished results, with AI agents.

Code decides the order of the steps. A model is called for one step at a time, with a clean context.
Three things hold throughout: the model proposes, code checks, and you approve.

## Before you start

Setup is done from the folder above this one. See `start_here.txt` there: run `bash setup.sh` first, then put your key in `.env`.

Every command below needs the environment to be active:

```bash
cd paperkit
source .venv/bin/activate
paperkit start
```

`paperkit start` shows the checklist of inputs and then a menu. Every step below is also in that menu; its key is given in brackets.
`paperkit` works from the `paperkit` folder and from this project folder.

## The order of work

"Required" means the paper cannot be written without the step. "Optional" steps improve the result and can be left out.

| # | Step | Command | Menu | Needed | Calls the model |
|---|---|---|---|---|---|
| 1 | Fill in the inputs | edit the files, or `paperkit start` | [1] | Required | no |
| 2 | Test the connection | `paperkit ping` | [9] | Recommended | a small test |
| 3 | Dry run on a stand-in model | `paperkit dry-run` | [2] | Optional | no |
| 4 | Draft facts and key messages from the Results | `paperkit extract facts`, `paperkit extract key-messages` | [f] [k] | Optional | yes |
| 5 | Writing rules from guides | `paperkit rules extract`, then `check`, then `approve` | [r] | Optional | yes |
| 6 | Plan the claim table | `paperkit plan discussion` | [3] | Required | yes |
| 7 | Search the literature | `paperkit evidence search discussion`, then `review`, then `apply` | [e] | Optional | yes |
| 8 | Read and approve the claim table | `paperkit approve discussion` | [4] | Required | no |
| 9 | Write: writer, gates, reviewer | `paperkit run discussion` | [5] | Required | yes |
| 10 | Build the paper and the report | `paperkit build` | [7] | Required | no |

The shortest path is 1, 6, 8, 9, 10. Steps 6 to 9 are done once for each section in `paper.yaml`.

At any time: `paperkit status` [8] shows where each section stands, `paperkit check` prints the input checklist, and `paperkit validate discussion` [6] runs the checks on the current draft without calling a model.

### 1. Fill in the inputs (required)

See the table under "Inputs". `paperkit start` goes through the missing ones with you.
`plan` and `run` do not call the model while a required input is missing. `--force` overrides that.

### 2. Test the connection (recommended)

`paperkit ping` shows which model each agent uses and sends each one a small request. Do this before the first real step.

### 3. Dry run (optional)

`paperkit dry-run` runs every step on a stand-in model, in a scratch copy under `.cache/dryrun/`. It needs no key and costs nothing, and your files are not changed. It shows that the inputs fit together.

### 4. Draft facts and key messages (optional)

Use this if you have not written `inputs/facts.csv` or `inputs/key_messages.md` by hand.

- `paperkit extract facts` reads the Results and Methods a few paragraphs at a time. A fact is kept only if it appears word for word in your text.
- `paperkit extract key-messages` drafts three to five messages from the Results.
- Both only fill a file that is empty or still holds the examples. `--force` replaces real content; the menu asks first.

Read both files afterwards and correct them. If you edit `inputs/facts.csv` by hand, run `paperkit facts` to rebuild `facts/facts.json`.

### 5. Writing rules from guides (optional)

Put the journal's guide for authors, reporting guidelines and style guides in `.writing_guides/journal`, `reporting` or `general`, as PDF, `.md` or `.txt`. Then, in this order:

```bash
paperkit rules extract      # reads the guides and proposes rules -> rules/candidates.json
paperkit rules check        # drops rules that repeat another, flags rules that contradict each other
paperkit rules approve      # asks about each rule; or: paperkit rules approve R1 R4, or --all
```

- A rule is kept only if its quote is really in the guide. Code works out the page.
- Only rules for the sections in your `paper.yaml` are compared and asked about.
- Nothing is used until you approve it. Approved rules go to `rules/active_rules.json`, and the writer and reviewer get the ones for their section.
- A rule that bans specific words is also checked by code.
- `paperkit rules list` shows every rule. `paperkit rules reject R4` takes one out. `paperkit rules restore R7` brings back a rule that `check` dropped.
- Word limits and required headings from a guide still go in `paper.yaml` by hand.

### 6. Plan the claim table (required)

`paperkit plan discussion` builds `state/claims/discussion.json`: one row for each claim the section will make, with its category, its facts and its sources.

### 7. Search the literature (optional)

Run this after planning, because it searches for the claims in the table. It uses Semantic Scholar; put a free key in `.env` as `SEMANTIC_SCHOLAR_API_KEY`, because searches without a key are often refused.

```bash
paperkit evidence search discussion    # searches and screens -> build/evidence_discussion.md
paperkit evidence review discussion    # asks about each suggestion: accept, reject or later
paperkit evidence apply discussion     # carries accepted suggestions into the claim table
```

- For each claim it looks for studies that support it, studies that contradict it, and other ways to read the finding.
- Every paper is a real record from the search service. A label is kept only if the sentence it rests on is in the abstract.
- The labels come from abstracts only: read a paper before you accept it.
- An accepted paper must be in `refs/library.bib` before a claim can cite it. Papers that are not there are written to `refs/suggested.bib`: import that file into Zotero and run `apply` again. If Zotero does not write `library.bib`, use `--add-to-library`.
- Accepted papers and interpretations become new claims. The claim table then loses its approval.

### 8. Read and approve the claim table (required)

This is the one manual check for each section. Open `state/claims/discussion.json` (or menu [4]), correct what is wrong, then run `paperkit approve discussion`.
Nothing is written from a table you have not approved.

### 9. Write (required)

`paperkit run discussion` runs writer, then gates, then reviewer, for up to `max_rounds` rounds. It prints each stage as it happens.
`paperkit run` with no section name does this for every section.

- If the gates find a problem, the draft goes back to the writer without reaching the reviewer.
- The finished section is `drafts/discussion.md`. The draft of each round is `drafts/discussion.r1.md`, `r2` and so on.
- If problems remain after the last round, the status is ESCALATED and the open problems are in `state/reviews/discussion.open.json`. Nothing is accepted silently.

### 10. Build (required)

`paperkit build` joins the finished sections into `build/paper.md`, puts the numbers in, and writes `build/report.md`.

- `build/paper.docx` is also made if pandoc is installed and nothing blocking is left.
- A section in `paper.yaml` without a finished draft is reported as blocking. Remove a section from `paper.yaml` if you are not writing it.
- For a draft over its word limit, the report says where to shorten it.

## Inputs

"Required" inputs are the ones `plan` and `run` insist on. `paperkit check` shows the state of each.

| File or folder | What goes in it | Needed |
|---|---|---|
| `paper.yaml` | Title, study design, and for each section its word limit and headings | Required; the title itself is recommended |
| `inputs/methods.md` | The full Methods section, as in the manuscript (at least 30 words) | Required |
| `inputs/results.md` | The full Results section: text, tables, figure captions | Required |
| `inputs/key_messages.md` | Three to five points the paper must get across, one per line | Required; step 4 can draft it |
| `inputs/limitations.md` | Known limitations and untested assumptions, one per line | Required |
| `inputs/facts.csv` | Every number the text may use: `id,text,source` | Required; step 4 can draft it |
| `inputs/introduction.md` | Background, knowledge gap and aim, in your own words | Required only if `paper.yaml` has an `introduction` section |
| `.env` (in the folder above) | The key of your model provider | Required for every step that calls a model |
| `refs/library.bib` | Your references, best as a Better BibTeX auto-export from Zotero | Recommended: without it nothing can be cited |
| `inputs/<section>_draft.md` | Your own draft of a section, as a starting point | Optional |
| `.writing_guides/` | Guides for step 5 | Optional |
| `wiki/<citation key>.md` | One page per cited source: what it found, with quotes | Optional: the reviewer checks citations against these pages |
| `.papers/`, `inputs/tables/` | Source PDFs and result tables | Not read by any command yet |

Notes on single inputs:

- **`paper.yaml`:** `design: observational` bans causal wording; `experimental` allows it. `max_words` is enforced. `required_headings` must appear in that order. `number_whitelist` and `term_whitelist` list tokens the checks should leave alone.
- **`inputs/facts.csv`:** the text never contains a typed number. Each number is a fact with an id, and the writer uses the id.
- **`inputs/<section>_draft.md`:** leave it empty and the section is written from scratch. Or paste what you have and mark it: `[KEEP]` for final wording, `[CHANGE: what to change]`, and `[WRITE: what it covers]` on its own line where text is missing. The file's own header explains this.
- **`wiki/`:** step 7 writes a page for each paper you accept, from its abstract. Add what you find in the full text.

## What the checks enforce in a draft

- The required `## ...` headings from `paper.yaml`, in the given order, and the word limit.
- Every paragraph ends with a claim tag: `<!-- C3 -->` or `<!-- C3,C4 -->`. Every claim in the table is used.
- No digits in the text. Numbers are written as `{{F12}}` and filled in from `facts/facts.json` at build time.
- Citations only as `[@key]`. The key must be in `refs/library.bib` and in the claim table.
- Wording matches the claim category: OBSERVED, INFERRED, ASSUMED or SPECULATIVE.
- No overstated wording, and no causal wording in an observational study.
- A word that an approved writing rule bans is flagged. It blocks the draft if the rule is marked as required.
- No `[KEEP]`, `[CHANGE: ...]` or `[WRITE: ...]` mark left over from your starting draft.

## Section statuses

| Status | Meaning | What to do |
|---|---|---|
| NEW | Not planned yet | Step 6 |
| CLAIMS_INVALID | The claim table has an error, such as an unknown fact or citation key | Correct the table, or plan again |
| AWAITING_APPROVAL | The claim table is waiting for you | Step 8 |
| APPROVED | Ready to write | Step 9 |
| DONE | The section passed the gates and the reviewer | Step 10 |
| ESCALATED | Problems remained after the last round | Read `state/reviews/<section>.open.json` and the report, fix the cause, run step 9 again |

## Where the results are

| File | What it is |
|---|---|
| `state/claims/<section>.json` | The claim table |
| `drafts/<section>.md` | The finished section |
| `drafts/<section>.rN.md` | The draft of round N |
| `state/reviews/` | What the gates and the reviewer found in each round |
| `build/paper.md`, `build/paper.docx` | The assembled paper |
| `build/report.md` | Statuses, open problems, and where to shorten |
| `build/evidence_<section>.md` | The literature search, to read |
| `rules/candidates.json`, `rules/active_rules.json` | All rules from the guides, and the approved ones |
| `refs/suggested.bib` | Accepted papers that are not in your library yet |
| `state/log/` | Every model call, as JSON |

## Models and keys

Every key is in one `.env` file in the `paperkit` folder, next to `setup.sh`. It is never inside this project. A value already set in the shell wins over the file.

Each agent uses the provider and model set in `config/models.yaml`. `PAPERKIT_PROVIDER` and `PAPERKIT_MODEL` in `.env` change the default without editing that file. Two providers are built in:

- `nvidia`: key in `NVIDIA_API_KEY`. The free, rate-limited endpoints at build.nvidia.com, or a local NIM through `NVIDIA_BASE_URL`.
- `anthropic`: key in `ANTHROPIC_API_KEY`.

Menu [9] can save the provider, the model and the key, and tests the connection.

### Settings in .env

| Setting | Default | What it does |
|---|---|---|
| `PAPERKIT_PROVIDER`, `PAPERKIT_MODEL` | `anthropic` and its default model | Provider and model for every agent without its own entry in `config/models.yaml` |
| `PAPERKIT_REASONING` | the model's own | `low`, `high` or `max` sets how much a reasoning model thinks; `off` turns thinking off where a model allows it. NVIDIA only |
| `PAPERKIT_MAX_TOKENS` | 8000 | The longest answer a model may give |
| `PAPERKIT_TIMEOUT` | 300 | Seconds to wait without any bytes from the model. NVIDIA only |
| `PAPERKIT_CHUNK_WORDS` | 500 | Words of Results per request in `extract facts` |
| `PAPERKIT_GUIDE_WORDS` | 1500 | Words of a guide per request in `rules extract` |
| `PAPERKIT_CHECK_RULES` | 80 | Rules per request in `rules check` |
| `PAPERKIT_SEARCH_RESULTS` | 5 | Papers per search in `evidence search` |
| `SEMANTIC_SCHOLAR_API_KEY` | none | Key for the literature search |
| `GITHUB_USER`, `GITHUB_TOKEN`, `VISIBILITY` | | Used only by `publish.sh` |

## When something goes wrong

| What you see | What to do |
|---|---|
| `Answer was cut off: raise PAPERKIT_MAX_TOKENS` | Set `PAPERKIT_MAX_TOKENS=16000` (or 32000) in `.env` |
| `HTTP 504`, or no answer from an NVIDIA model | Set `PAPERKIT_REASONING=low`. Run `paperkit ping`: if that fails too, the model is down or busy, so wait or put another model in `config/models.yaml` |
| `Too long: N words, limit M`, section ESCALATED | Run `paperkit build` and read "Where to shorten" in `build/report.md`. Often the claim table has too many claims for the limit |
| `No finished draft for section 'x'` in the report | Write that section (steps 6 to 9), or remove it from `paper.yaml` |
| Section is CLAIMS_INVALID | A claim names a fact id or citation key that does not exist. Correct `state/claims/<section>.json` |
| Semantic Scholar is not answering | Put a free key in `.env` as `SEMANTIC_SCHOLAR_API_KEY`, then run the search again |
| A step that failed half way | Run it again. Answers already received are saved in `.cache/` and are not asked for twice |

## Git and publish.sh

`publish.sh`, in the folder above, is a development tool: it commits the code and uploads it to GitHub. You do not need it to write a paper. See Part B of `start_here.txt`.

The one `.gitignore` is in that folder too. It keeps `.env`, `.venv/`, `inputs/`, `drafts/`, `state/`, `facts/`, `build/`, `.papers/`, `.writing_guides/` and `.cache/` out of Git. So `publish.sh` does not back up your manuscript text.

## Where to change things

- Provider and model per agent: `config/models.yaml`, or `PAPERKIT_PROVIDER` and `PAPERKIT_MODEL`.
- Prompts: `src/paperkit/agents.py`.
- Banned word lists: `src/paperkit/validators/language.py`.
- A new gate: a module with a `check(draft, ctx)` function, plus one line in `validators/__init__.py`.
- The tests run without a key, on a stand-in model: `python -m pytest -q` in this folder.
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
# inputs/discussion_draft.md
# ----------------------------------------------------------------------------
FILES['inputs/discussion_draft.md'] = r'''
<!--
HOW TO USE THIS FILE. This comment is never sent to the model.

Optional. Leave the text below empty and the Discussion is written from scratch. Or paste what you
already have, in any state, and the planner and the writer start from it.

Write the text as it should read in the paper, with the two rules the checks enforce:
  - numbers as {{F1}}, {{F2}} ... (the ids in inputs/facts.csv), never as digits
  - citations as [@citekey], with keys from refs/library.bib

Mark what still needs work at the end of the sentence or paragraph it applies to:

  [KEEP]                    the wording is final: keep it as it is
  [CHANGE: what to change]  the text is there but must change, for example
                            [CHANGE: hedge this, the design is observational]
  [WRITE: what it covers]   nothing is written yet: put this on its own line where the text goes, for example
                            [WRITE: one paragraph on why the association may differ by age]

Unmarked text is a draft: the model may improve it but keeps its meaning. If the results contradict
a statement, the claim table says so and you decide. The markers are never copied into the result:
a marker left in a finished draft is reported as an error.
Keep the headings the same as the required headings in paper.yaml.
-->

## Principal findings

## Comparison with prior work

## Limitations

## Conclusion
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
    origin: str = Field(default="", description="Leave empty. Code fills it in for claims that the evidence search added.")


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
    for kind in (*PIPELINE_AGENTS, "facts", "rules", "literature"):    # also the models behind extract, rules, evidence
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
- Do not claim more than the results support.
- If <starting_draft> is given, it is the author's own draft of this section. Build the claims from it: one claim per statement the author made, in the author's order, with the author's meaning. Text marked [KEEP] is final: keep its claims as they are. At [CHANGE: ...] make that change. At [WRITE: ...] add the claims it asks for, from the results and facts. Drop an author's statement only if the results contradict it; then keep the claim and add "CONTRADICTS: what" to its assumptions."""


def plan_claims(sec: SectionSpec, *, design: str, key_messages: str, limitations: str, methods: str,
                results: str, fact_reg: dict, library: str, wiki_index: str,
                issues: Sequence[Issue] = (), introduction: str = "", starting_draft: str = "") -> list[Claim]:
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
    if starting_draft:
        user += "\n\n" + _tag("starting_draft", starting_draft)
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
- If something you need is missing, write [AUTHOR: what is missing] or [NEEDS SOURCE: what for]. Do not fill the gap yourself.
- If <starting_draft> is given, follow it: keep text marked [KEEP] word for word (it still needs its claim tag), make the change at each [CHANGE: ...], and write each [WRITE: ...] from the claims. Never copy the markers [KEEP], [CHANGE: ...] or [WRITE: ...] into your draft.
- Stay within max_words of <section>: the words are counted. If a draft comes back as too long, cut to the targets given with that problem, and say each claim once instead of in several paragraphs.
- If <writing_rules> is given, follow every rule in it: they come from the journal's and other writing guides, and the author approved them. Where one of them conflicts with the rules above, the rules above win."""

OBSERVATIONAL = """
- The design is observational: no causal wording (cause, lead to, result in, effect of, impact, drive) outside paragraphs tagged only with SPECULATIVE or ASSUMED claims."""


def write_section(sec: SectionSpec, *, design: str, claims: Sequence[Claim], fact_reg: dict,
                  wiki_pages: dict[str, str], prev_draft: str = "", issues: Sequence[Issue] = (),
                  starting_draft: str = "", rules: Sequence[dict] = ()) -> str:
    system = WRITER + (OBSERVATIONAL if design == "observational" else "")
    user = "\n\n".join([
        _tag("section", _json(sec.model_dump())),
        _tag("claims", _json([c.model_dump() for c in claims])),
        _tag("facts", _json(fact_reg)),
        _tag("sources", "\n\n".join(f"## {k}\n{v}" for k, v in wiki_pages.items())),
    ])
    if rules:
        user += "\n\n" + _tag("writing_rules", _json(list(rules)))
    if starting_draft:
        user += "\n\n" + _tag("starting_draft", starting_draft)
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
- rule: the draft breaks a rule in <writing_rules>, if that block is given. Name the rule id in the message. This one is blocking only if the rule's priority is "required". Placeholders, claim tags and [@key] citations are replaced later and never break a rule.

For each issue give severity ("blocking" if the paper would be wrong or misleading, otherwise "warning"), a message saying what is wrong, and the exact sentence as excerpt.
If the draft is sound, return an empty list."""


def review_section(sec: SectionSpec, *, design: str, methods: str, results: str, claims: Sequence[Claim],
                   fact_reg: dict, wiki_pages: dict[str, str], draft: str,
                   rules: Sequence[dict] = ()) -> list[Issue]:
    user = "\n\n".join([
        _tag("section", _json(sec.model_dump())),
        _tag("study_design", design),
        _tag("methods", methods),
        _tag("results", results),
        _tag("claims", _json([c.model_dump() for c in claims])),
        _tag("facts", _json(fact_reg)),
        _tag("sources", "\n\n".join(f"## {k}\n{v}" for k, v in wiki_pages.items())),
        *([_tag("writing_rules", _json(list(rules)))] if rules else []),
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
from . import citations, coverage, language, numbers, structure, writing_rules
from .claims import check_claims
from .common import GateContext

GATES = [structure, citations, numbers, language, coverage, writing_rules]

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
from dataclasses import dataclass, field

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
    rules: list = field(default_factory=list)      # approved writing rules for this section


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
"""Structure: required headings in order, the word limit, and no action marker left over."""
from __future__ import annotations

import re

from .. import shorten
from ..schemas import Issue
from .common import GateContext, headings, plain, short

ACTION = re.compile(r"\[(?:WRITE|CHANGE)\b[^\]]*\]|\[KEEP\]")   # marks from inputs/<section>_draft.md


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
    for m in ACTION.finditer(draft):
        issues.append(Issue(gate="structure", message="Action marker left in the draft", excerpt=short(m.group(0))))
    words = len(plain(draft).split())
    if words == 0:
        issues.append(Issue(gate="structure", message="Draft is empty"))
    if words > ctx.sec.max_words:
        found = shorten.analyse(draft, ctx.sec.max_words)      # how much to cut and where: sent back to the writer
        issues.append(Issue(gate="structure", message=f"Too long: {words} words, limit {ctx.sec.max_words}",
                            excerpt=shorten.hint(found) if found else ""))
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
FILES['src/paperkit/shorten.py'] = r'''
"""Where a draft that is over its word limit can be shortened. Counting only: no model is called.

The same numbers are used twice. The report lists them for a person, and the structure gate sends a
short form back to the writer together with the "Too long" problem.
"""
from __future__ import annotations

import re
from collections import Counter

from .validators.common import COMMENT, HEADING, paragraphs, plain, short
from .validators.language import FILLER

LONG_SENTENCE = 35          # words: longer sentences are listed as candidates to trim
THIN_CLAIM = 70             # words per claim: below this the claim table is too large for the limit
KEEP = "[KEEP]"
MARKS = re.compile(r"\[(?:WRITE|CHANGE)\b[^\]]*\]|\[KEEP\]")    # the marks of inputs/<section>_draft.md


def words(md: str) -> int:
    """The count the structure gate uses: no tags, citations, placeholders or heading marks."""
    return len(plain(md).split())


def by_heading(md: str) -> list[tuple[str, int]]:
    """(heading, words under it) in the order of the draft."""
    out: list[tuple[str, int]] = []
    name, rows = "(before the first heading)", []

    def close() -> None:
        count = words("\n".join(rows))
        if count:
            out.append((name, count))

    for line in md.splitlines():
        found = HEADING.match(line)
        if found:
            close()
            name, rows = found.group(2), []
        else:
            rows.append(line)
    close()
    return out


def analyse(draft: str, limit: int) -> dict | None:
    """None when the draft is within the limit. Otherwise how much is over, and where the words are."""
    total = words(draft)
    if total <= limit:
        return None
    paras = [(text, ids, words(text)) for text, ids in paragraphs(draft)]
    in_paragraphs: dict[str, list[int]] = {}
    for _, ids, count in paras:
        for claim_id in dict.fromkeys(ids):
            in_paragraphs.setdefault(claim_id, []).append(count)
    repeated = sorted(((claim_id, len(counts), sum(counts)) for claim_id, counts in in_paragraphs.items()
                       if len(counts) > 1), key=lambda row: -row[2])
    long_sentences = sum(1 for text, _, _ in paras for sentence in re.split(r"(?<=[.!?])\s+", plain(text))
                         if len(sentence.split()) > LONG_SENTENCE)
    filler = Counter(m.group(0).lower() for m in FILLER.finditer(plain(draft)))
    longest = sorted(paras, key=lambda row: -row[2])[:5]
    return {
        "total": total, "limit": limit, "over": total - limit, "percent": round(100 * (total - limit) / total),
        "headings": [(name, count, round(count * limit / total)) for name, count in by_heading(draft)],
        "longest": [(count, ids, short(COMMENT.sub("", text), 80)) for text, ids, count in longest],
        "repeated": repeated, "long_sentences": long_sentences, "filler": filler.most_common(),
    }


def hint(found: dict) -> str:
    """One line for the writer: how much to cut, the target under each heading, and the claims said twice."""
    parts = [f"cut {found['over']} words ({found['percent']}%)"]
    if found["headings"]:
        parts.append("aim per heading: " + "; ".join(f"{name} {now} -> {target}" for name, now, target in found["headings"]))
    if found["repeated"]:
        parts.append("say each claim once: " + ", ".join(row[0] for row in found["repeated"][:8])
                     + " take more than one paragraph")
    return ". ".join(parts)


def own_words(starting_draft: str) -> int:
    """Words of the author's own text in inputs/<section>_draft.md, without its comment and its marks."""
    return words(MARKS.sub("", COMMENT.sub("", starting_draft)))


def kept_words(starting_draft: str) -> int:
    """Words in the paragraphs of inputs/<section>_draft.md that carry a [KEEP] mark."""
    text = COMMENT.sub("", starting_draft)
    return sum(words(MARKS.sub("", block)) for block, _ in paragraphs(text) if KEEP in block)


def report_lines(sec_id: str, source: str, found: dict, claims: int = 0, kept: int = 0, starting: int = 0) -> list[str]:
    """The "Where to shorten" block of build/report.md for one section."""
    limit = found["limit"]
    lines = [f"## Where to shorten: {sec_id}", "",
             f"The latest draft ({source}) has {found['total']} words. The limit is {limit}, "
             f"so {found['over']} words ({found['percent']}%) have to go.", ""]
    if found["headings"]:
        lines += ["Words under each heading, with the target if every heading shrinks by the same share:", "",
                  "| Heading | Now | Target | Cut |", "|---|---|---|---|"]
        lines += [f"| {name} | {now} | {target} | {now - target} |" for name, now, target in found["headings"]]
        lines.append("")
    if found["longest"]:
        lines += ["The longest paragraphs:", ""]
        lines += [f"{n}. {count} words{', claims ' + ', '.join(ids) if ids else ''}: \"{start}\""
                  for n, (count, ids, start) in enumerate(found["longest"], 1)]
        lines.append("")
    if found["repeated"]:
        lines += ["Claims that take more than one paragraph (say each once and cut the repeats):", ""]
        lines += [f"- {claim_id}: {count} paragraphs, {total} words" for claim_id, count, total in found["repeated"]]
        lines.append("")
    more = []
    if claims:
        per_claim = limit // claims
        row = f"The claim table has {claims} claims. At {limit} words that is about {per_claim} words per claim"
        if per_claim < THIN_CLAIM:
            row += (f", less than one short paragraph each: the writer cannot fit them. Delete or merge claims in "
                    f"state/claims/{sec_id}.json (then approve and run again), or raise max_words in paper.yaml")
        more.append(row + ".")
    if kept:
        more.append(f"inputs/{sec_id}_draft.md marks about {kept} words as [KEEP]. The writer must keep them word for word"
                    + (", and that alone is over the limit." if kept > limit else "."))
    if starting > limit:
        more.append(f"Your starting draft in inputs/{sec_id}_draft.md has {starting} words, and the writer follows it. "
                    "Shorten it there, or mark what can go with [CHANGE: shorten].")
    if found["long_sentences"]:
        more.append(f"{found['long_sentences']} sentence(s) have more than {LONG_SENTENCE} words: split or trim them.")
    if found["filler"]:
        more.append("Filler to delete: " + ", ".join(f'"{phrase}" ({count})' for phrase, count in found["filler"][:6]) + ".")
    if more:
        lines += ["Also:", ""] + [f"- {row}" for row in more] + [""]
    return lines[:-1] if lines[-1] == "" else lines
'''

FILES['src/paperkit/build.py'] = r'''
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
        claims = [c.model_copy(update={"origin": ""}) for c in claims]     # only code marks where a claim came from
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
    for first_id, second_id, _ in rules_ingest.clashes(ctx.rules, approved_only=True):
        say(f"  warning: writing rules {first_id} and {second_id} contradict each other and both are approved "
            f"(paperkit rules reject <id> takes one out)")

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
    if any(i.message.startswith("Too long") for i in issues):
        say("  The draft is over its word limit: the build (menu 7, or `paperkit build`) writes where to "
            "shorten it into build/report.md")
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
'''

# ----------------------------------------------------------------------------
# src/paperkit/__main__.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/scholar.py'] = r'''
"""Semantic Scholar search. Standard library only, so there is no extra dependency.

Every record here came from the API: the model never names a paper. Requests are paced, a refused
request is tried again after a wait, and each answered search is saved in .cache/scholar/.

A key is optional but matters: without one, searches share a pool with every other anonymous user and
are often turned away. A free key (semanticscholar.org/product/api) allows one request per second.
Put it in .env as SEMANTIC_SCHOLAR_API_KEY.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://api.semanticscholar.org/graph/v1"      # SEMANTIC_SCHOLAR_BASE_URL overrides it
FIELDS = "title,abstract,year,authors,venue,externalIds,citationCount,url"
PAUSE = 1.1                     # seconds between requests: a key allows one request per second
BACKOFF = (3, 8, 20, 40)        # waits after HTTP 429 or 5xx: the API sends no Retry-After
TIMEOUT = 30
KEY_HINT = ("Without a key, Semantic Scholar often turns searches away. Request a free key at "
            "semanticscholar.org/product/api and put SEMANTIC_SCHOLAR_API_KEY=... in .env.")
STOPWORDS = {"the", "and", "for", "with", "from", "into", "that", "this", "does", "are", "was", "were", "between",
             "among", "study", "analysis", "effect", "effects", "using", "based", "toward", "towards", "about"}
_last = 0.0                     # when the last request was sent


class SearchError(RuntimeError):
    """The search service could not be used. The message says what to do."""


def has_key() -> bool:
    return bool((os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or "").strip())


def _get(url: str) -> dict:
    """One paced GET. HTTP 429 and 5xx are both the service saying "not now": wait and try again."""
    global _last
    key = (os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or "").strip()
    headers = {"Accept": "application/json", "User-Agent": "paperkit (literature search for a manuscript)"}
    if key:
        headers["x-api-key"] = key
    for wait in (*BACKOFF, None):
        gap = PAUSE - (time.monotonic() - _last)
        if gap > 0:
            time.sleep(gap)
        _last = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:200]
            busy = exc.code == 429 or exc.code >= 500
            if busy and wait is not None:
                time.sleep(wait)
                continue
            if exc.code in (401, 403):
                raise SearchError("Semantic Scholar rejected the key: check SEMANTIC_SCHOLAR_API_KEY in .env") from None
            if busy:
                raise SearchError(f"Semantic Scholar is not answering (HTTP {exc.code}, {len(BACKOFF) + 1} tries). "
                                  + ("Try again later." if key else KEY_HINT)) from None
            raise SearchError(f"Semantic Scholar: HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            if wait is not None:
                time.sleep(min(wait, 5))
                continue
            reason = getattr(exc, "reason", exc)
            raise SearchError(f"cannot reach Semantic Scholar: {' '.join(str(reason).split())[:160]}") from None
    raise SearchError("no answer from Semantic Scholar")       # not reached


def paper(raw: dict) -> dict | None:
    """One API record in paperkit's shape, or None when it has no id or no title."""
    if not isinstance(raw, dict):
        return None
    title = " ".join(str(raw.get("title") or "").split())
    if not raw.get("paperId") or not title:
        return None
    ids = raw.get("externalIds") or {}
    doi = next((str(value).strip().lower() for name, value in ids.items() if str(name).lower() == "doi" and value), "")
    year = raw.get("year")
    return {
        "paper_id": str(raw["paperId"]), "title": title,
        "authors": [str(a["name"]).strip() for a in raw.get("authors") or [] if isinstance(a, dict) and a.get("name")],
        "year": year if isinstance(year, int) else None,
        "venue": " ".join(str(raw.get("venue") or "").split()),
        "doi": doi, "url": f"https://doi.org/{doi}" if doi else str(raw.get("url") or ""),
        "abstract": " ".join(str(raw.get("abstract") or "").split()),      # often missing, even for well-known papers
        "citations": int(raw.get("citationCount") or 0),
    }


def clean_query(query: str, words: int = 12) -> str:
    """A query the relevance search accepts: no quotes or operators, and no hyphens (they match nothing there)."""
    text = re.sub(r"[\"'“”‘’()\[\]{}:;,+|*~<>]", " ", unicodedata.normalize("NFKC", query)).replace("-", " ")
    return " ".join(text.split()[:words])


def search(query: str, limit: int = 5, cache_dir: Path | None = None, fresh: bool = False) -> list[dict]:
    """The papers the relevance search returns for a query, best match first."""
    query = clean_query(query)
    if not query:
        return []
    base = (os.environ.get("SEMANTIC_SCHOLAR_BASE_URL") or BASE_URL).rstrip("/")
    name = hashlib.sha256(json.dumps([query, limit, FIELDS]).encode("utf-8")).hexdigest()[:24]
    cache = Path(cache_dir) / f"{name}.json" if cache_dir else None
    if cache and cache.is_file() and not fresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    data = _get(f"{base}/paper/search?" + urllib.parse.urlencode({"query": query, "limit": limit, "fields": FIELDS}))
    rows = data.get("data") if isinstance(data, dict) else None
    papers = [found for found in map(paper, rows or []) if found]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(papers, ensure_ascii=False), encoding="utf-8")
    return papers


# ------------------------------------------------------------------ references

def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def cite_key(found: dict, taken) -> str:
    """A citation key such as smith2020sleep that is not in `taken`."""
    family = re.sub(r"[^a-z]", "", _ascii((found.get("authors") or ["anon"])[0].split()[-1]).lower()) or "anon"
    title = re.sub(r"[^\w\s]", " ", found.get("title", ""))           # a dash or a brace separates words
    word = next((w for w in re.findall(r"[a-z]+", _ascii(title).lower()) if len(w) > 3 and w not in STOPWORDS), "")
    base = f"{family}{found.get('year') or 'nd'}{word}"
    taken = set(taken)
    key, n = base, 0
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n)}" if n <= 26 else f"{base}{n}"
    return key


def bibtex(found: dict, key: str) -> str:
    """A BibTeX entry built from the API record."""
    def value(text: object) -> str:
        return re.sub(r"[{}]", "", " ".join(str(text).split()))

    fields = [("title", found.get("title", "")), ("author", " and ".join(found.get("authors") or [])),
              ("year", found.get("year") or ""), ("journal", found.get("venue", "")),
              ("doi", found.get("doi", "")), ("url", found.get("url", ""))]
    rows = [f"  {name} = {{{value(text)}}}," for name, text in fields if str(text).strip()]
    return "@article{" + key + ",\n" + "\n".join(rows) + "\n}\n"


def norm_doi(text: str) -> str:
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", str(text or "").strip().lower())


def title_key(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", str(text or "")).casefold() if ch.isalnum())


def library_key(bib: dict, found: dict) -> str:
    """The key under which a paper is already in refs/library.bib: matched by DOI, else by title. '' if it is not."""
    doi, title = norm_doi(found.get("doi", "")), title_key(found.get("title", ""))
    for key, fields in bib.items():
        if doi and norm_doi(fields.get("doi", "")) == doi:
            return key
    for key, fields in bib.items():
        if title and title_key(fields.get("title", "")) == title:
            return key
    return ""
'''

FILES['src/paperkit/evidence.py'] = r'''
"""Evidence search: what published studies say about the claims of a section, and how else a finding could be read.

The model proposes; code verifies; a person decides.
- A `literature` agent writes three searches for each claim: for support, for contradiction, for other explanations.
- Code runs them on Semantic Scholar, so every paper is a real record. The model never names a paper.
- The agent labels each paper from its abstract (supports, contradicts, mixed, unrelated) and must quote the
  sentence it relies on. Code keeps a label only if that quote is in the abstract.
- The agent also lists other interpretations of the finding that the study design cannot rule out.
- Nothing enters the paper by itself. You read the papers and accept or reject each suggestion. Accepted ones
  become claims in the claim table, which loses its approval, so you read and approve it again as usual.

Files: state/evidence/<section>.json (everything, with your decisions), build/evidence_<section>.md (to read),
refs/suggested.bib (accepted papers that are not in refs/library.bib yet), wiki/<key>.md (one page per accepted paper).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field

from . import agents, keys, orchestrator, scholar, zotero
from .schemas import Claim

KINDS = ("supporting", "contradicting", "alternative")
STANCES = ("supports", "contradicts", "mixed", "unclear", "not screened")
HEADINGS = {"supports": "Supports", "contradicts": "Contradicts", "mixed": "Mixed", "unclear": "Unclear from the abstract",
            "not screened": "Not screened: no abstract available"}
GROUPS = {"supports": "supports", "contradicts": "contradicts"}       # every other stance goes to "other"
LEADS = {"supports": "Earlier work agrees with our finding", "contradicts": "Earlier work disagrees with our finding",
         "other": "Earlier work bears on our finding"}
ORIGIN = "evidence search"
MIN_QUOTE_WORDS = 4

QUERIES = """You write literature searches for the claims of one section of a scientific paper.

For each claim in <claims> return three keyword searches for a scholarly search engine. Each is 3 to 8 words, with no quotation marks, no hyphens and no operators such as AND or OR:
- supporting: finds studies that report the same result
- contradicting: finds studies that report the opposite result or no such result, for example with the words null, no association, or failed to replicate
- alternative: finds studies on other explanations of such a result, for example confounding, reverse causation, selection or measurement

Use the terms of the field as they appear in <methods>. Name the variables and the population, not our study. Return one entry for every claim id."""

ASSESS = """You judge how published studies bear on ONE finding of a paper, from their abstracts only, and you list other ways that finding could be explained. You write no text for the paper.

Part 1, verdicts. For every paper in <papers> return:
- paper: its number
- stance: "supports" if it reports the same direction of result in a comparable setting; "contradicts" if it reports the opposite result or finds no such result; "mixed" if both, or only in some groups or conditions; "unrelated" if the abstract reports no result on this question
- quote: the one sentence of the abstract your verdict rests on, copied character for character. Empty for "unrelated".
- note: one sentence, with no digits, saying what that study found in relation to our finding, worded as it could be said in a Discussion. Empty for "unrelated".
Judge only from the abstract that is given. Do not use what you remember about a paper.

Part 2, alternatives. List up to four other interpretations of OUR finding that the design in <methods> cannot rule out: confounding, reverse direction, selection, measurement, chance, or another kind. For each:
- interpretation: one complete, hedged sentence with no digits, for example "The association may reflect ... rather than ..."
- kind: confounding, reverse direction, selection, measurement, chance or other
- papers: the numbers of the papers above that bear on it; may be empty
- check: one sentence on which analysis or data would tell it apart from our reading
Do not repeat what <limitations> already states. If there is no serious alternative, return an empty list."""


class Searches(BaseModel):
    claim_id: str = Field(description="The id of the claim, such as C2")
    supporting: str
    contradicting: str
    alternative: str


class SearchList(BaseModel):
    searches: list[Searches] = Field(default_factory=list)


class Verdict(BaseModel):
    paper: int = Field(description="The number of the paper in <papers>")
    stance: str = Field(description="supports, contradicts, mixed or unrelated")
    quote: str = Field(default="", description="One sentence of the abstract, copied character for character")
    note: str = Field(default="", description="One sentence with no digits")


class Alternative(BaseModel):
    interpretation: str = Field(description="One complete, hedged sentence with no digits")
    kind: str = Field(default="other", description="confounding, reverse direction, selection, measurement, chance or other")
    papers: list[int] = Field(default_factory=list, description="Numbers of papers in <papers> that bear on it")
    check: str = Field(default="", description="Which analysis or data would tell it apart")


class Assessment(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)


# ------------------------------------------------------------------ small helpers

def _key(text: str) -> str:
    """Letters and digits only, in lower case: what a quote is compared on."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", str(text or "")).casefold() if ch.isalnum())


def _line(text: object, limit: int = 0) -> str:
    text = " ".join(str(text or "").split())
    return text if not limit or len(text) <= limit else text[:limit - 1] + "…"


def _file(root: Path, sec_id: str) -> Path:
    return Path(root) / "state" / "evidence" / f"{sec_id}.json"


def load(root: str | Path, sec_id: str) -> dict:
    path = _file(Path(root), sec_id)
    if not path.is_file():
        return {"section": sec_id, "findings": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"state/evidence/{sec_id}.json is not valid JSON: {_line(exc, 120)}") from None
    data.setdefault("findings", [])
    return data


def save(root: str | Path, sec_id: str, data: dict) -> None:
    orchestrator._dump(_file(Path(root), sec_id), data)
    write_report(Path(root), sec_id, data)


def _cached(root: Path, kind: str, system: str, user: str, schema: type[BaseModel], fresh: bool) -> BaseModel:
    """One model call, answered from .cache/evidence/ when the same question was asked before."""
    name = hashlib.sha256(json.dumps([schema.__name__, system, user]).encode("utf-8")).hexdigest()[:24]
    cache = root / ".cache" / "evidence" / f"{name}.json"
    if cache.is_file() and not fresh:
        try:
            return schema.model_validate_json(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    answer = agents._ask(kind, system, user, schema)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(answer.model_dump_json(), encoding="utf-8")
    return answer


def targets(table) -> list[Claim]:
    """The claims that are searched: what the paper reports and what it concludes. Not the ones this step added."""
    return [c for c in table.claims if c.category in ("OBSERVED", "INFERRED") and c.origin != ORIGIN]


def _cite(found: dict) -> str:
    names = found.get("authors") or []
    who = ", ".join(names[:3]) + (" et al." if len(names) > 3 else "") or "Unknown authors"
    venue = f" {found['venue']}." if found.get("venue") else ""
    return f"{who} ({found.get('year') or 'n.d.'}). {found.get('title', '')}.{venue}"


# ------------------------------------------------------------------ search and screening

def _searches(root: Path, p, claims: list[Claim], fresh: bool) -> dict[str, dict[str, str]]:
    user = "\n\n".join([
        agents._tag("claims", json.dumps([{"id": c.id, "text": c.text} for c in claims], ensure_ascii=False, indent=1)),
        agents._tag("study_design", p.spec.design),
        agents._tag("methods", " ".join(p.inp("methods").split()[:800])),
    ])
    got = _cached(root, "literature", QUERIES, user, SearchList, fresh)
    out = {}
    for row in got.searches:
        out[row.claim_id.strip().upper()] = {kind: scholar.clean_query(getattr(row, kind)) for kind in KINDS}
    for claim in claims:                       # a claim the model skipped is searched with its own words
        have = out.setdefault(claim.id, {})
        have["supporting"] = have.get("supporting") or scholar.clean_query(claim.text)
        have["contradicting"] = have.get("contradicting") or scholar.clean_query(claim.text + " null no association", 16)
        have["alternative"] = have.get("alternative") or scholar.clean_query(claim.text + " confounding", 14)
    return out


def _assess(root: Path, p, claim: Claim, screened: list[dict], fresh: bool) -> Assessment:
    listing = "\n\n".join(f"[{n}] {found['title']} ({found.get('year') or 'n.d.'})\n{found['abstract']}"
                          for n, found in enumerate(screened, 1))
    user = "\n\n".join([
        agents._tag("finding", claim.text),
        agents._tag("study_design", p.spec.design),
        agents._tag("methods", " ".join(p.inp("methods").split()[:800])),
        agents._tag("limitations", p.inp("limitations")),
        agents._tag("papers", listing or "(no paper with an abstract was found)"),
    ])
    return _cached(root, "literature", ASSESS, user, Assessment, fresh)


def _verdicts(answer: Assessment, screened: list[dict]) -> dict[int, dict]:
    """Stance, quote and note for each screened paper, by position. A label whose quote is not in the abstract is not kept."""
    out: dict[int, dict] = {}
    for verdict in answer.verdicts:
        position = verdict.paper - 1
        if not 0 <= position < len(screened) or position in out:
            continue
        stance = verdict.stance.strip().lower()
        if stance == "unrelated":
            out[position] = {"stance": "unrelated", "quote": "", "note": ""}
            continue
        quote = _line(unicodedata.normalize("NFKC", verdict.quote))
        in_abstract = len(quote.split()) >= MIN_QUOTE_WORDS and _key(quote) in _key(screened[position]["abstract"])
        if stance not in ("supports", "contradicts", "mixed") or not in_abstract:
            out[position] = {"stance": "unclear", "quote": quote if in_abstract else "", "note": _line(verdict.note)}
        else:
            out[position] = {"stance": stance, "quote": quote, "note": _line(verdict.note)}
    return out


def search(root: str | Path, sec_id: str, fresh: bool = False, say=lambda text: None) -> dict:
    """Searches the literature for every reported and inferred claim of the section. Your earlier decisions are kept."""
    root = Path(root)
    p = orchestrator.Project(root)
    p.spec.section(sec_id)
    table = p.load_claims(sec_id)
    if table is None:
        raise ValueError(f"No claim table for '{sec_id}'. Plan the section first (menu 3, or: paperkit plan {sec_id}).")
    claims = targets(table)
    if not claims:
        raise ValueError(f"The claim table for '{sec_id}' has no OBSERVED or INFERRED claim to search for.")
    old = load(root, sec_id)
    before = {f.get("claim_id"): f for f in old["findings"]}
    limit = int(os.environ.get("PAPERKIT_SEARCH_RESULTS") or "5")
    cache_dir = root / ".cache" / "scholar"
    failed: list[str] = []

    say(f"evidence: writing searches for {len(claims)} claim(s) ...")
    searches = _searches(root, p, claims, fresh)
    number = {"E": 0, "A": 0}
    for finding in old["findings"]:
        for prefix, rows in (("E", finding.get("papers", [])), ("A", finding.get("alternatives", []))):
            for row in rows:
                found = re.fullmatch(rf"{prefix}(\d+)", str(row.get("id", "")))
                number[prefix] = max(number[prefix], int(found.group(1)) if found else 0)

    findings, search_down = [], False
    for position, claim in enumerate(claims, 1):
        earlier = before.get(claim.id, {})
        if search_down:                        # the search service stopped answering: keep what there was
            if earlier:
                findings.append(earlier)
            continue
        where = f"evidence: {claim.id} ({position} of {len(claims)})"
        queries = searches[claim.id]
        papers: dict[str, dict] = {}
        try:
            for kind in KINDS:
                if kind != "supporting" and queries[kind] in [queries[k] for k in KINDS[:KINDS.index(kind)]]:
                    continue
                for found in scholar.search(queries[kind], limit, cache_dir, fresh):
                    papers.setdefault(found["paper_id"], {**found, "found_by": []})["found_by"].append(kind)
        except scholar.SearchError as exc:
            failed.append(f"{claim.id}: {_line(exc, 300)}")
            search_down = True
            if earlier:
                findings.append(earlier)
            continue
        screened = [found for found in papers.values() if found["abstract"]]
        say(f"{where}: {len(papers)} paper(s) found, {len(screened)} with an abstract; asking the model ...")
        try:
            answer = _assess(root, p, claim, screened, fresh)
        except Exception as exc:               # a provider error: keep going, this claim is asked again next time
            failed.append(f"{claim.id}: {type(exc).__name__}: {_line(exc, 200)}")
            if earlier:
                findings.append(earlier)
            continue

        verdicts = _verdicts(answer, screened)
        decided = {row.get("paper_id"): row for row in earlier.get("papers", [])}
        rows, unrelated = [], 0
        for found in papers.values():
            verdict = (verdicts.get(screened.index(found), {"stance": "unclear", "quote": "", "note": ""})
                       if found["abstract"] else {"stance": "not screened", "quote": "", "note": ""})
            if verdict["stance"] == "unrelated":
                unrelated += 1
                continue
            kept = decided.get(found["paper_id"], {})
            rows.append({"id": kept.get("id", ""), **found, **verdict, "decision": kept.get("decision", ""),
                         "in_library": scholar.library_key(p.bib, found)})
        rows.sort(key=lambda row: (STANCES.index(row["stance"]), -row["citations"]))
        for row in rows:                       # numbered in the order they are shown; a paper seen before keeps its number
            if not row["id"]:
                number["E"] += 1
                row["id"] = f"E{number['E']}"

        known = {_key(row.get("interpretation")): row for row in earlier.get("alternatives", [])}
        others = []
        for alternative in answer.alternatives[:4]:
            text = _line(alternative.interpretation)
            if not text or _key(text) in [_key(row["interpretation"]) for row in others]:
                continue
            kept = known.get(_key(text), {})
            if not kept.get("id"):
                number["A"] += 1
            bearing = [screened[n - 1]["paper_id"] for n in alternative.papers if 0 < n <= len(screened)]
            others.append({"id": kept.get("id") or f"A{number['A']}", "interpretation": text,
                           "kind": _line(alternative.kind).lower() or "other", "check": _line(alternative.check),
                           "papers": [row["id"] for row in rows if row["paper_id"] in bearing],
                           "decision": kept.get("decision", ""), "claim": kept.get("claim", "")})
        findings.append({"claim_id": claim.id, "text": claim.text, "searches": queries, "papers": rows,
                         "alternatives": others, "unrelated": unrelated, "claims": earlier.get("claims", {})})

    data = {"section": sec_id, "searched": time.strftime("%Y-%m-%d"), "source": "Semantic Scholar", "findings": findings}
    save(root, sec_id, data)
    return {"data": data, "failed": failed}


# ------------------------------------------------------------------ the readable report

def _mark(row: dict) -> str:
    return {"accepted": "x", "rejected": "-"}.get(row.get("decision", ""), " ")


def write_report(root: Path, sec_id: str, data: dict) -> Path:
    lines = [f"# Evidence search: {sec_id}", "",
             f"Searched {data.get('source', 'Semantic Scholar')} on {data.get('searched', 'an earlier day')}. "
             "The labels come from abstracts only: read a paper before you accept it.",
             "[x] accepted, [-] rejected, [ ] not decided. Decide with: paperkit evidence review " + sec_id, ""]
    for finding in data.get("findings", []):
        lines += [f"## {finding['claim_id']}: {finding['text']}", "",
                  "Searches: " + "; ".join(f"{finding['searches'].get(kind, '')} ({kind})" for kind in KINDS), ""]
        if not finding["papers"]:
            lines += ["No related paper was found. That is not the same as there being none.", ""]
        for stance in STANCES:
            rows = [row for row in finding["papers"] if row["stance"] == stance]
            if not rows:
                continue
            lines += [f"### {HEADINGS[stance]} ({len(rows)})", ""]
            for row in rows:
                lines.append(f"- [{_mark(row)}] {row['id']}  {_cite(row)} Cited {row['citations']} times. {row['url']}"
                             + (f"  In your library as [@{row['in_library']}]." if row.get("in_library") else ""))
                if row["quote"]:
                    lines.append(f"  > \"{row['quote']}\"")
                if row["note"]:
                    lines.append(f"  {row['note']}")
            lines.append("")
        if finding.get("unrelated"):
            lines += [f"{finding['unrelated']} more paper(s) were found and judged unrelated.", ""]
        if finding["alternatives"]:
            lines += ["### Other interpretations", ""]
            for row in finding["alternatives"]:
                lines.append(f"- [{_mark(row)}] {row['id']}  ({row['kind']}) {row['interpretation']}"
                             + (f" Papers: {', '.join(row['papers'])}." if row["papers"] else ""))
                if row["check"]:
                    lines.append(f"  To tell them apart: {row['check']}")
            lines.append("")
    out = root / "build" / f"evidence_{sec_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return out


def counts(data: dict) -> dict:
    papers = [row for f in data.get("findings", []) for row in f["papers"]]
    others = [row for f in data.get("findings", []) for row in f["alternatives"]]
    return {"papers": len(papers), "accepted": sum(row["decision"] == "accepted" for row in papers),
            "open": sum(not row["decision"] for row in papers + others),
            "alternatives": len(others), "alternatives_accepted": sum(row["decision"] == "accepted" for row in others)}


# ------------------------------------------------------------------ your decisions

def show(finding: dict, row: dict) -> list[str]:
    if "interpretation" in row:
        rows = [f"{row['id']}  other interpretation ({row['kind']}): {row['interpretation']}"]
        if row["papers"]:
            rows.append(f"      Papers that bear on it: {', '.join(row['papers'])}")
        if row["check"]:
            rows.append(f"      To tell them apart: {row['check']}")
        return rows
    rows = [f"{row['id']}  {row['stance']}: {_cite(row)} Cited {row['citations']} times.", f"      {row['url']}"]
    if row["quote"]:
        rows.append(f"      \"{row['quote']}\"")
    if row["note"]:
        rows.append(f"      {row['note']}")
    if row.get("in_library"):
        rows.append(f"      Already in your library as [@{row['in_library']}].")
    return rows


def review(root: str | Path, sec_id: str, ask=input, out=print) -> int:
    """Walks through every suggestion that has no decision yet. Returns how many were accepted."""
    root = Path(root)
    data = load(root, sec_id)
    accepted = 0
    waiting = [(f, row) for f in data["findings"] for row in f["papers"] + f["alternatives"] if not row.get("decision")]
    try:
        for number, (finding, row) in enumerate(waiting, 1):
            out("")
            out(f"{number} of {len(waiting)}, for {finding['claim_id']}: {_line(finding['text'], 110)}")
            for text in show(finding, row):
                out(text)
            answer = keys.latin(keys.read(ask, "[y] accept  [n] reject  [l] later  [q] stop > ", out).strip().lower())[:1]
            if answer == "q":
                break
            if answer == "y":
                row["decision"] = "accepted"
                accepted += 1
            elif answer == "n":
                row["decision"] = "rejected"
    except EOFError:
        pass
    finally:
        save(root, sec_id, data)               # whatever was decided so far is kept
    return accepted


def decide(root: str | Path, sec_id: str, ids, decision: str) -> int:
    data = load(Path(root), sec_id)
    wanted = {str(i).upper() for i in ids}
    rows = [row for f in data["findings"] for row in f["papers"] + f["alternatives"] if row["id"].upper() in wanted]
    unknown = sorted(wanted - {row["id"].upper() for row in rows})
    if unknown:
        raise ValueError(f"No such suggestion: {', '.join(unknown)}. `paperkit evidence list {sec_id}` shows the ids.")
    for row in rows:
        row["decision"] = decision
    save(Path(root), sec_id, data)
    return len(rows)


# ------------------------------------------------------------------ accepted suggestions -> library, wiki, claim table

def _wiki_page(key: str, found: dict, uses: list[tuple[dict, dict]], sec_id: str) -> str:
    lines = [f"# {key}", "", f"{_cite(found)} {found['url']}", "",
             f"Added by the evidence search for the {sec_id} section. Everything below is from the abstract only:",
             "add what you find in the full text and correct what is wrong.", "",
             "## Question", "", "## Design and sample", "", "## Key findings", ""]
    lines += [f"- {row['note'] or 'See the abstract.'} ({row['stance']}, in relation to: {_line(finding['text'], 100)})"
              for finding, row in uses]
    lines += ["", "## Quotes", ""]
    lines += [f"> \"{quote}\" (abstract)" for quote in dict.fromkeys(row["quote"] for _, row in uses if row["quote"])]
    lines += ["", "## Limitations", "", "## Abstract", "", found["abstract"] or "(no abstract available)"]
    return "\n".join(lines) + "\n"


def apply(root: str | Path, sec_id: str, add_to_library: bool = False) -> dict:
    """Carries the accepted suggestions into the project. Safe to repeat: nothing is added twice.

    A paper has to be in refs/library.bib before a claim can cite it. Papers that are not there yet are written
    to refs/suggested.bib for you to import into Zotero. `add_to_library` appends them to refs/library.bib
    instead: use it only if Zotero does not write that file.
    """
    root = Path(root)
    data = load(root, sec_id)
    p = orchestrator.Project(root)
    table = p.load_claims(sec_id)
    if table is None:
        raise ValueError(f"No claim table for '{sec_id}'. Plan the section first (menu 3, or: paperkit plan {sec_id}).")
    bib_path = root / "refs" / "library.bib"
    bib = zotero.load_bib(bib_path)
    accepted = {}                              # paper id -> record, each paper once
    for finding in data["findings"]:
        for row in finding["papers"]:
            if row.get("decision") == "accepted":
                accepted.setdefault(row["paper_id"], row)

    missing = [row for row in accepted.values() if not scholar.library_key(bib, row)]
    suggested = root / "refs" / "suggested.bib"
    added_to_library: list[str] = []
    if missing:
        taken = set(bib)
        entries = []
        for row in missing:
            key = scholar.cite_key(row, taken)
            taken.add(key)
            entries.append(scholar.bibtex(row, key))
            added_to_library.append(key)
        if add_to_library:
            current = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
            bib_path.parent.mkdir(parents=True, exist_ok=True)
            bib_path.write_text(current.rstrip("\n") + "\n\n% Added by `paperkit evidence apply`\n" + "\n".join(entries),
                                encoding="utf-8")
            bib, missing = zotero.load_bib(bib_path), []
        else:
            suggested.write_text("% Papers accepted in the evidence search that are not in refs/library.bib yet.\n"
                                 "% Import this file into Zotero, then run: paperkit evidence apply " + sec_id + "\n\n"
                                 + "\n".join(entries), encoding="utf-8")
            added_to_library = []
    if not missing and suggested.exists():
        suggested.unlink()                     # everything in it has reached the library

    keys = {paper_id: scholar.library_key(bib, row) for paper_id, row in accepted.items()}
    for finding in data["findings"]:
        for row in finding["papers"]:
            row["in_library"] = scholar.library_key(bib, row)

    pages = []
    wiki_dir = root / "wiki"
    for paper_id, row in accepted.items():
        key = keys[paper_id]
        if not key or (wiki_dir / f"{key}.md").exists():
            continue
        uses = [(f, r) for f in data["findings"] for r in f["papers"]
                if r["paper_id"] == paper_id and r.get("decision") == "accepted"]
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / f"{key}.md").write_text(_wiki_page(key, row, uses, sec_id), encoding="utf-8")
        index = wiki_dir / "index.md"
        listed = index.read_text(encoding="utf-8") if index.exists() else "# Wiki index\n\n"
        if f"[[{key}]]" not in listed:
            index.write_text(listed.rstrip("\n") + f"\n- [[{key}]]: {_line(row['title'], 90)}\n", encoding="utf-8")
        pages.append(key)

    by_id = {c.id: c for c in table.claims}
    last = max([int(c.id[1:]) for c in table.claims if re.fullmatch(r"C\d+", c.id)] or [0])
    new, grown = [], []

    def carry(holder: dict, slot: str, text: str, category: str, cite_keys: list[str]) -> None:
        nonlocal last
        claim_id = holder.get(slot, "")
        if claim_id:                           # added before: only new sources are added, your wording stays
            claim = by_id.get(claim_id)
            fresh_keys = [k for k in cite_keys if claim and k not in claim.cite_keys]
            if fresh_keys:
                claim.cite_keys += fresh_keys
                grown.append(claim_id)
            return                             # a claim you deleted from the table is not added again
        last += 1
        claim = Claim(id=f"C{last}", text=text, category=category, cite_keys=cite_keys, origin=ORIGIN)
        table.claims.append(claim)
        by_id[claim.id] = claim
        holder[slot] = claim.id
        new.append(claim.id)

    for finding in data["findings"]:
        finding.setdefault("claims", {})
        ours = _line(finding["text"]).rstrip(".")
        for group in ("supports", "contradicts", "other"):
            rows = [row for row in finding["papers"] if row.get("decision") == "accepted"
                    and GROUPS.get(row["stance"], "other") == group and keys.get(row["paper_id"])]
            if not rows:
                continue
            notes = list(dict.fromkeys(row["note"] for row in rows if row["note"] and not re.search(r"\d", row["note"])))
            text = f"{LEADS[group]} ({ours})" + (": " + " ".join(notes) if notes else ".")
            carry(finding["claims"], group, text, "INFERRED", list(dict.fromkeys(keys[row["paper_id"]] for row in rows)))
        ids = {row["id"]: row for row in finding["papers"]}
        for other in finding["alternatives"]:
            if other.get("decision") != "accepted":
                continue
            cited = [keys.get(ids[i]["paper_id"], "") for i in other["papers"]
                     if i in ids and ids[i].get("decision") == "accepted"]
            carry(other, "claim", other["interpretation"], "SPECULATIVE", [k for k in dict.fromkeys(cited) if k])

    if new or grown:
        table.approved = False                 # the table changed: a person reads and approves it again
        p.save_claims(table)
        p.set_status(sec_id, "AWAITING_APPROVAL")
    save(root, sec_id, data)
    return {"new": new, "grown": grown, "pages": pages, "added_to_library": added_to_library,
            "waiting": [_line(row["title"], 90) for row in missing]}


def missing_from_library(root: str | Path, sec_id: str) -> int:
    """How many accepted papers are not in refs/library.bib yet."""
    root = Path(root)
    bib = zotero.load_bib(root / "refs" / "library.bib")
    rows = {row["paper_id"]: row for f in load(root, sec_id)["findings"] for row in f["papers"]
            if row.get("decision") == "accepted"}
    return sum(1 for row in rows.values() if not scholar.library_key(bib, row))


# ------------------------------------------------------------------ `paperkit evidence`

def _report_apply(done: dict, sec_id: str, out) -> None:
    if done["added_to_library"]:
        out(f"Added to refs/library.bib: {', '.join(done['added_to_library'])}")
    if done["pages"]:
        out(f"Wiki pages written (from the abstract: add what the full text says): {', '.join(done['pages'])}")
    if done["new"]:
        out(f"New claims in the claim table: {', '.join(done['new'])}")
    if done["grown"]:
        out(f"Sources added to claims: {', '.join(done['grown'])}")
    if done["new"] or done["grown"]:
        out(f"The claim table is no longer approved. Read it, correct the wording, then: paperkit approve {sec_id}")
    if done["waiting"]:
        out(f"{len(done['waiting'])} accepted paper(s) are not in refs/library.bib yet, so no claim cites them:")
        for title in done["waiting"]:
            out(f"  - {title}")
        out(f"Import refs/suggested.bib into Zotero, then run: paperkit evidence apply {sec_id}")
        out("If Zotero does not write refs/library.bib, add --add-to-library instead.")
    if not any(done.values()):
        out("Nothing to carry over: no accepted suggestion is waiting.")


def run(root: str | Path, action: str, sec_id: str, ids=(), fresh: bool = False, add_to_library: bool = False,
        out=print, ask=input) -> int:
    """search | list | review | accept | reject | apply. Exit code 1 if something failed."""
    root = Path(root)
    try:
        if action == "search":
            got = search(root, sec_id, fresh, out)
            found = counts(got["data"])
            out(f"evidence: {found['papers']} paper(s) and {found['alternatives']} other interpretation(s) for "
                f"{len(got['data']['findings'])} claim(s) -> build/evidence_{sec_id}.md")
            for row in got["failed"]:
                out(f"  failed: {row}")
            if got["failed"]:
                out("Run it again for what failed: answered searches and model calls are kept and are not repeated.")
            if not scholar.has_key() and not got["failed"]:
                out("Tip: " + scholar.KEY_HINT)
            if found["open"]:
                out(f"Nothing is used until you accept it: paperkit evidence review {sec_id}")
            return 1 if got["failed"] else 0
        data = load(root, sec_id)
        if not data["findings"]:
            out(f"No evidence search for '{sec_id}' yet. Run: paperkit evidence search {sec_id}")
            return 0 if action == "list" else 1
        if action == "list":
            for finding in data["findings"]:
                out(f"{finding['claim_id']}: {_line(finding['text'], 110)}")
                for row in finding["papers"] + finding["alternatives"]:
                    out(f"  [{_mark(row)}] " + show(finding, row)[0])
            found = counts(data)
            out(f"{found['accepted']} of {found['papers']} paper(s) and {found['alternatives_accepted']} of "
                f"{found['alternatives']} interpretation(s) accepted. Details: build/evidence_{sec_id}.md")
            return 0
        if action in ("accept", "reject"):
            if not ids:
                out(f"Name the suggestions, for example: paperkit evidence {action} {sec_id} E2 A1")
                return 1
            out(f"{decide(root, sec_id, ids, action + 'ed')} suggestion(s) {action}ed.")
        elif action == "review":
            out(f"{review(root, sec_id, ask, out)} suggestion(s) accepted.")
        _report_apply(apply(root, sec_id, add_to_library), sec_id, out)
        return 0
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        out(f"evidence: {type(exc).__name__}: {_line(exc, 300)}")
        return 1
'''

FILES['src/paperkit/__main__.py'] = r'''
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


def test_each_stage_is_reported_while_it_runs(project):
    flagged = [Issue(gate="overclaim", message="Too strong", excerpt="This suggests")]
    agents.LLM = fake_llm([BAD, GOOD, GOOD], [flagged, []])
    said = []
    orchestrator.plan(project, "discussion", said.append)
    assert said[0] == "discussion: planning, round 1 of 3" and "is building the claim table" in said[1]
    assert "3 claims" in said[2] and said[3] == "  check    passed"
    orchestrator.approve(project, "discussion")

    said.clear()
    assert orchestrator.run_section(project, "discussion", said.append) == "DONE"
    text = "\n".join(said)
    assert [row for row in said if row.startswith("discussion:")] == [f"discussion: round {n} of 3" for n in (1, 2, 3)]
    assert "is writing the draft" in said[1] and "-> drafts/discussion.r1.md" in said[2]
    assert "gates    13 problem(s), back to the writer:" in text and "[numbers]" in text     # round 1 stops at the gates
    assert "... and 8 more" in text
    assert "reviewer done in 0 s: 1 problem(s), back to the writer:" in text and "[review:overclaim] Too strong" in text
    assert said[-1].endswith("no problems -> drafts/discussion.md")
    assert text.index("is writing") < text.index("gates") < text.index("is reading the draft")

    agents.LLM = fake_llm([BAD, BAD, BAD], [])
    said.clear()
    assert orchestrator.run_section(project, "discussion", said.append) == "ESCALATED"
    assert "no rounds left" in "\n".join(said) and said[-1].endswith("-> state/reviews/discussion.open.json")


PAD = " ".join(["word"] * 60)
TOO_LONG = """## Principal findings

We observed an association between X and Y ({{F1}}) among {{F2}} participants. PAD <!-- C1 -->

We observed it again ({{F1}}) in order to be sure. PAD <!-- C1 -->

## Interpretation

This suggests that X tracks Y, consistent with earlier work [@smith2020]. PAD <!-- C2 -->

This reading assumes that measurement error was unrelated to Y, which we did not test. PAD <!-- C3 -->
""".replace("PAD", PAD)


def test_a_draft_that_is_too_long_gets_targets_and_the_report_says_where_to_shorten(project, tmp_path):
    prompts = []

    def llm(system, user, schema):
        if schema is ClaimList:
            return ClaimList(claims=CLAIMS)
        prompts.append(user)
        return Draft(markdown=TOO_LONG)                 # the writer never gets under the limit of 200 words

    agents.LLM = llm
    orchestrator.plan(project, "discussion")
    orchestrator.approve(project, "discussion")
    said = []
    assert orchestrator.run_section(project, "discussion", said.append) == "ESCALATED"
    assert "build/report.md" in said[-1]

    again = prompts[1]                                  # round 2: the writer is told how much to cut and where
    assert "Too long:" in again and "| cut " in again and "aim per heading: Principal findings" in again
    assert "say each claim once: C1 take more than one paragraph" in again

    (tmp_path / "inputs" / "discussion_draft.md").write_text(
        "<!-- how to use -->\n\n## Principal findings\n\n" + " ".join(["kept"] * 250) + " [KEEP]\n", encoding="utf-8")
    text = build.report(tmp_path, project.spec, project.status(), []).read_text(encoding="utf-8")
    assert "## Where to shorten: discussion" in text and "The latest draft (drafts/discussion.r3.md) has" in text
    assert "| Heading | Now | Target | Cut |" in text and "| Principal findings | " in text and "| Interpretation | " in text
    assert "The longest paragraphs:" in text and "- C1: 2 paragraphs, " in text
    assert "The claim table has 3 claims. At 200 words that is about 66 words per claim, less than one short" in text
    assert "marks about 250 words as [KEEP]" in text and "that alone is over the limit" in text
    assert "Your starting draft in inputs/discussion_draft.md has 252 words" in text
    assert 'Filler to delete: "in order to" (1).' in text

    (tmp_path / "drafts" / "discussion.md").write_text(GOOD, encoding="utf-8")      # a finished draft within the limit
    text = build.report(tmp_path, project.spec, {"discussion": "DONE"}, []).read_text(encoding="utf-8")
    assert "Where to shorten" not in text


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
FILES['src/paperkit/ingestion/rules_ingest.py'] = r'''
"""Writing guides -> writing rules.

PDF, .md or .txt files in .writing_guides/ (general/, journal/, reporting/) become rules for the writer and reviewer.
The model proposes; code verifies; a person approves:
- each guide is read page by page and sent to the `rules` agent a few pages at a time;
- a proposed rule is kept only if its quote is really in those pages (the same letters and digits in the same
  order), and its page is worked out here, never by the model;
- kept rules go to rules/candidates.json with approved set to false. Only approved rules, which are copied to
  rules/active_rules.json, ever reach the writer, the reviewer and the gate;
- every answered part is saved in .cache/guides/, so a run that failed half way continues where it stopped.

`check` is a separate step for after the guides are read. It drops rules that repeat another rule and marks
rules that contradict each other. Nothing is deleted: a dropped rule stays in rules/candidates.json with a note
of the rule it repeats, and `restore` brings it back.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .. import agents, keys
from ..ingestion_schemas import WritingRule

GUIDES = ".writing_guides"
SUFFIXES = (".pdf", ".md", ".txt")
CATEGORIES = ("structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting",
              "scientific_reasoning")
PRIORITIES = ("required", "recommended", "optional")
MIN_QUOTE_WORDS = 3
KEPT_BY_HAND = "none"           # duplicate_of of a rule a person restored: it is never dropped again
STRENGTH = {"required": 0, "recommended": 1, "optional": 2}
AUTHORITY = {"journal": 0, "reporting": 1, "general": 2}       # whose wording is kept when two guides say the same
NONE_YET = f"No rules yet. Put the guides in {GUIDES}/ and run: paperkit rules extract"

PROMPT = """You read part of a writing guide (a journal's instructions for authors, a reporting guideline or a style guide) and list the rules that say how the TEXT of a scientific paper must be written. You write no prose.

For each rule return:
- instruction: one short imperative sentence a writer can follow, in your own words. One rule per instruction.
- quote: the passage of the guide that states the rule, copied character for character. One continuous passage of 5 to 60 words: no "...", and never two places joined together.
- category: structure, argumentation, language, statistics, reporting, citations, formatting or scientific_reasoning.
- sections: the sections of a paper it applies to, in lower case, such as ["abstract"], ["methods"] or ["discussion"]; ["all"] if it applies everywhere. Prefer the names in <paper_sections>.
- priority: "required" if the guide says must, required, never or always; "recommended" if it says should; otherwise "optional".
- avoid_terms: only when the rule bans specific words or phrases, those words exactly as they appear in your quote; otherwise an empty list.

Leave out everything that is not about writing the text: submission and upload steps, fees, file formats and image resolution, cover letters, authorship and ethics forms, copyright, the review process, contact details.
Never invent a rule. If these pages hold no writing rule, return an empty list. Return at most 15 rules."""


class ProposedRule(BaseModel):
    instruction: str = Field(description="One short imperative sentence a writer can follow")
    quote: str = Field(description="The passage of the guide that states it, copied character for character")
    category: str = Field(default="language", description="One of: " + ", ".join(CATEGORIES))
    sections: list[str] = Field(default_factory=lambda: ["all"], description='Paper sections in lower case, or ["all"]')
    priority: str = Field(default="recommended", description="required, recommended or optional")
    avoid_terms: list[str] = Field(default_factory=list, description="Banned words or phrases, exactly as in the quote")


class RuleList(BaseModel):
    rules: list[ProposedRule] = Field(default_factory=list)


COMPARE = """You compare writing rules that were taken from several guides. You change no rule and you write no new one.

Each line of <rules> is: id [sections; priority; kind of guide] instruction.

Return:
- repeats: groups of rule ids that ask for the same thing, so that a text that follows one of them follows the others too. The same requirement in other words is a repeat. A stricter, narrower or more detailed version is NOT a repeat: leave it out. Put an id in one group at most.
- contradictions: pairs of rule ids that cannot both be followed in the same section, each with a one-sentence reason. Examples: two different word limits for the same section; one rule requires what the other forbids. Rules for different sections do not contradict each other. A general rule and a stricter rule on the same point do not contradict each other.

If there are none, return empty lists. Use only ids that are in <rules>."""


class Repeat(BaseModel):
    ids: list[str] = Field(description="Ids of rules that ask for the same thing")


class Clash(BaseModel):
    first: str = Field(description="A rule id")
    second: str = Field(description="The id of the rule it contradicts")
    reason: str = Field(default="", description="One sentence: why both cannot be followed")


class RuleCheck(BaseModel):
    repeats: list[Repeat] = Field(default_factory=list)
    contradictions: list[Clash] = Field(default_factory=list)


# ------------------------------------------------------------------ reading

def _key(text: str) -> str:
    """Letters and digits only, in lower case. Quotes are compared on this, so the line breaks, hyphens
    and quote marks of a PDF do not matter, but every word must be there in the same order."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _short(text: object, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def clean(text: str) -> str:
    """Page text as running text: a word split over a line break is joined, and lines become sentences."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
    blocks = (" ".join(block.split()) for block in re.split(r"\n[ \t]*\n", text))
    return "\n\n".join(block for block in blocks if block)


def guide_files(root: str | Path) -> list[Path]:
    folder = Path(root) / GUIDES
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)


def read_guide(path: Path) -> list[tuple[int, str]]:
    """(page number, text) for every page that has text. A .md or .txt file is one page unless it holds form feeds."""
    if path.suffix.lower() == ".pdf":
        try:
            from .pdf_parser import parse_pdf

            raw = [(page["page"], page["text"]) for page in parse_pdf(path)]
        except ImportError:
            raise RuntimeError("reading a PDF needs PyMuPDF: pip install pymupdf") from None
    else:
        raw = list(enumerate(path.read_text(encoding="utf-8-sig").split("\f"), 1))
    pages = [(number, clean(text)) for number, text in raw]
    return [(number, text) for number, text in pages if text]


def parts(pages: list[tuple[int, str]], limit: int) -> list[list[tuple[int, str]]]:
    """Consecutive pages grouped into parts of about `limit` words, so no request is long. A page is never cut."""
    out, current, size = [], [], 0
    for page in pages:
        words = len(page[1].split())
        if current and size + words > limit:
            out.append(current)
            current, size = [], 0
        current.append(page)
        size += words
    return out + ([current] if current else [])


def section_ids(root: str | Path) -> list[str]:
    try:
        raw = yaml.safe_load((Path(root) / "paper.yaml").read_text(encoding="utf-8")) or {}
        return [str(sec["id"]).lower() for sec in raw.get("sections", []) if isinstance(sec, dict) and sec.get("id")]
    except Exception:
        return []


# ------------------------------------------------------------------ the two rule files

def _file(root: str | Path, name: str) -> Path:
    return Path(root) / "rules" / f"{name}.json"


def load(root: str | Path, name: str = "candidates") -> list[WritingRule]:
    """rules/<name>.json as rules. A missing or empty file is an empty list; a broken one is an error."""
    path = _file(root, name)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.strip():
        return []
    try:
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError("it must be a list of rules")
        return [WritingRule.model_validate(item) for item in raw]
    except ValueError as exc:                  # also covers a JSON error and a rule that does not fit the schema
        raise ValueError(f"rules/{name}.json is not valid: {_short(exc)}") from None


def save(root: str | Path, rules: list[WritingRule]) -> None:
    """Writes rules/candidates.json, and rules/active_rules.json with the approved rules only."""
    for name, rows in (("candidates", rules), ("active_rules", [r for r in rules if r.approved])):
        path = _file(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([r.model_dump() for r in rows], ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def for_section(root: str | Path, sec_id: str, title: str = "") -> list[WritingRule]:
    """The approved rules that apply to one section: its own and those for all sections."""
    names = {"all", sec_id.lower(), title.lower()}
    return [r for r in load(root, "active_rules") if r.approved and names & {s.lower() for s in r.sections}]


def dropped(rule: WritingRule) -> bool:
    """True for a rule that `check` set aside because it repeats another rule."""
    return rule.duplicate_of not in ("", KEPT_BY_HAND)


def paper_sections(root: str | Path) -> set[str]:
    """The names a rule can use for a section of this paper: the ids and titles in paper.yaml, and "all"."""
    names = {"all"}
    try:
        raw = yaml.safe_load((Path(root) / "paper.yaml").read_text(encoding="utf-8")) or {}
        for sec in raw.get("sections", []):
            if isinstance(sec, dict):
                names |= {str(sec[k]).lower() for k in ("id", "title") if sec.get(k)}
    except Exception:
        pass
    return names


def relevant(rule: WritingRule, names: set[str]) -> bool:
    """True if the rule can apply to a section this paper has. Guides are full of rules for other sections
    (abstract, methods, references ...): those are kept but not compared, and you are not asked about them."""
    return len(names) == 1 or bool(names & {s.lower() for s in rule.sections})


def _number(rule: WritingRule) -> int:
    found = re.fullmatch(r"R(\d+)", rule.id)
    return int(found.group(1)) if found else 10 ** 9


def clashes(rules: list[WritingRule], approved_only: bool = False) -> list[tuple[str, str, str]]:
    """(id, id, reason) for every pair of rules marked as contradicting. With approved_only: both are in use."""
    live = {r.id: r for r in rules if not dropped(r) and (r.approved or not approved_only)}
    return [(r.id, other, reason) for r in sorted(live.values(), key=_number) for other, reason in r.conflicts.items()
            if other in live and _number(r) < _number(live[other])]


def state(root: str | Path) -> dict:
    try:
        rules = load(root)
    except ValueError:
        rules = []
    names = paper_sections(root)
    live = [r for r in rules if not dropped(r)]
    ours = [r for r in live if relevant(r, names)]
    return {"guides": len(guide_files(root)), "candidates": len(live), "relevant": len(ours),
            "approved": sum(r.approved for r in ours), "dropped": len(rules) - len(live), "conflicts": len(clashes(rules))}


# ------------------------------------------------------------------ checking a proposal

def _same(rule: WritingRule) -> tuple[str, str, str]:
    return rule.source_file, _key(rule.source_quote or ""), _key(rule.instruction)


def _page(quote: str, pages: list[tuple[int, str]]) -> int | None:
    """The page that holds the quote, or None if it is not in these pages."""
    wanted = _key(quote)
    keys = [(number, _key(text)) for number, text in pages]
    for number, key in keys:
        if wanted in key:
            return number
    for (number, first), (_, second) in zip(keys, keys[1:]):
        if wanted in first + second:
            return number                      # the passage runs over a page break
    return None


def verify(raw: dict, pages: list[tuple[int, str]], source: str, group: str) -> WritingRule | str:
    """A rule built from one proposal, or the reason it was left out. Nothing is taken on trust:
    the quote must be in the pages, and a banned term must be in the quote."""
    instruction = " ".join(str(raw.get("instruction") or "").split())
    quote = " ".join(unicodedata.normalize("NFKC", str(raw.get("quote") or "")).split())
    if not instruction:
        return "a proposal with no instruction"
    if len(quote.split()) < MIN_QUOTE_WORDS:
        return f"{_short(instruction, 90)} (its quote is too short to check)"
    page = _page(quote, pages)
    if page is None:
        return f"{_short(instruction, 90)} (its quote is not in the guide)"
    category = str(raw.get("category") or "").strip().lower().replace(" ", "_")
    priority = str(raw.get("priority") or "").strip().lower()
    priority = priority if priority in PRIORITIES else "recommended"
    sections = [" ".join(str(s).lower().split()) for s in raw.get("sections") or [] if str(s).strip()]
    terms: list[str] = []
    for term in raw.get("avoid_terms") or []:
        term = " ".join(unicodedata.normalize("NFKC", str(term)).split()).strip("\"'“”‘’.,;:")
        in_quote = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", quote, re.IGNORECASE) if term else None
        if len(term) >= 2 and len(term.split()) <= 6 and in_quote and term.lower() not in [t.lower() for t in terms]:
            terms.append(term)
    return WritingRule(
        id="", category=category if category in CATEGORIES else "language", instruction=instruction,
        sections=sections or ["all"], priority=priority, severity="blocking" if priority == "required" else "warning",
        validation_method="python" if terms else "ai", source_file=source, source_page=page, source_quote=quote,
        group=group, avoid_terms=terms, approved=False)


# ------------------------------------------------------------------ guides -> candidates

def extract(root: str | Path, fresh: bool = False, say=lambda text: None) -> dict:
    """Reads every guide, asks the model part by part and writes rules/candidates.json.

    A rule that is already a candidate is left exactly as it is, with its id, your edits and its approval.
    `fresh` asks the model again instead of using the answers saved in .cache/guides/.
    """
    root = Path(root)
    files = guide_files(root)
    if not files:
        raise ValueError(f"No guides found. Put PDF, .md or .txt files in {GUIDES}/journal, "
                         f"{GUIDES}/reporting or {GUIDES}/general.")
    old = load(root)
    sections = section_ids(root)
    limit = int(os.environ.get("PAPERKIT_GUIDE_WORDS") or "1500")
    agents.LOG_DIR = root / "state" / "log"
    found: list[WritingRule] = []
    seen: set[tuple[str, str, str]] = set()
    dropped: list[str] = []
    failed: list[str] = []
    unread: set[str] = set()                   # guides that were not read in full this time

    for path in files:
        source = path.relative_to(root).as_posix()
        inner = path.relative_to(root / GUIDES).parts
        group = inner[0] if len(inner) > 1 else "general"
        try:
            pages = read_guide(path)
        except Exception as exc:
            failed.append(f"{source}: {_short(exc)}")
            unread.add(source)
            continue
        if not pages:
            failed.append(f"{source}: no text in it (a scanned PDF needs OCR first)")
            continue
        chunks = parts(pages, limit)
        for number, chunk in enumerate(chunks, 1):
            span = f"page {chunk[0][0]}" if len(chunk) == 1 else f"pages {chunk[0][0]}-{chunk[-1][0]}"
            where = f"rules: {source}, part {number} of {len(chunks)} ({span})"
            text = "\n\n".join(f"[page {page}]\n{body}" for page, body in chunk)
            digest = hashlib.sha256(json.dumps([PROMPT, sections, text]).encode("utf-8")).hexdigest()[:24]
            cache = root / ".cache" / "guides" / f"{digest}.json"
            proposed = None
            if cache.is_file() and not fresh:
                try:
                    proposed = json.loads(cache.read_text(encoding="utf-8"))
                except ValueError:
                    proposed = None
            if proposed is not None:
                say(f"{where}: answer kept from an earlier run")
            else:
                say(f"{where}: asking the model, {len(text.split())} words ...")
                user = (agents._tag("paper_sections", ", ".join(sections) or "(none listed)") + "\n\n"
                        + agents._tag("guide", text))
                try:
                    proposed = [rule.model_dump() for rule in agents._ask("rules", PROMPT, user, RuleList).rules]
                except Exception as exc:       # a provider error: keep going, this part is asked again next time
                    failed.append(f"{source}, {span}: {type(exc).__name__}: {_short(exc)}")
                    unread.add(source)
                    continue
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(proposed, ensure_ascii=False), encoding="utf-8")
            for raw in proposed:
                rule = verify(raw, chunk, source, group) if isinstance(raw, dict) else "a proposal that is not a rule"
                if isinstance(rule, str):
                    dropped.append(f"{source}, {span}: {rule}")
                elif _same(rule) not in seen:
                    seen.add(_same(rule))
                    found.append(rule)

    by_rule = {_same(r): r for r in old}
    by_quote: dict[tuple[str, str], list[WritingRule]] = {}
    for rule in old:
        by_quote.setdefault((rule.source_file, _key(rule.source_quote or "")), []).append(rule)
    number = max([int(r.id[1:]) for r in old if re.fullmatch(r"R\d+", r.id)] or [0])
    reused: set[int] = set()
    already: dict[int, WritingRule] = {}       # position in `found` -> the candidate it already is
    for position, rule in enumerate(found):
        before = by_rule.get(_same(rule))
        if before is not None:
            reused.add(id(before))
            already[position] = before
    for position, rule in enumerate(found):    # the same passage with an instruction you have edited
        if position not in already:
            same_quote = [r for r in by_quote.get((rule.source_file, _key(rule.source_quote or "")), [])
                          if id(r) not in reused]
            if len(same_quote) == 1:
                reused.add(id(same_quote[0]))
                already[position] = same_quote[0]
    final: list[WritingRule] = []
    new = 0
    for position, rule in enumerate(found):
        if position in already:
            final.append(already[position])
        else:
            number, new = number + 1, new + 1
            rule.id = f"R{number}"
            final.append(rule)
    for rule in old:                           # rules you added by hand, and those of a guide not read in full
        by_hand = not rule.source_file.startswith(GUIDES + "/")
        if id(rule) not in reused and (by_hand or rule.source_file in unread):
            final.append(rule)
    final.sort(key=lambda r: int(r.id[1:]) if re.fullmatch(r"R\d+", r.id) else 10 ** 9)
    save(root, final)
    return {"files": len(files), "rules": final, "new": new, "dropped": dropped, "failed": failed}


# ------------------------------------------------------------------ repeats and contradictions

def _overlap(first: WritingRule, second: WritingRule) -> bool:
    """True if both rules can apply to the same section. Rules for different sections neither repeat nor contradict."""
    one, two = {s.lower() for s in first.sections}, {s.lower() for s in second.sections}
    return "all" in one or "all" in two or bool(one & two)


def check(root: str | Path, fresh: bool = False, say=lambda text: None) -> dict:
    """Drops rules that repeat another rule and marks rules that contradict each other. Run it after `extract`.

    Only rules for the sections this paper has are compared. Word-for-word repeats are found by code. Repeats in
    other words and contradictions are proposed by the model, one category of rules at a time, and code accepts
    them only between rules it showed the model that can apply to the same section. Of a group of repeats one
    rule is kept: an approved one first, then the journal's guide before a reporting guideline before a general
    style guide. It takes over the widest scope and the strictest priority of the group.
    """
    root = Path(root)
    rules = load(root)
    names = paper_sections(root)
    live = [r for r in rules if not dropped(r)]
    compared = [r for r in live if relevant(r, names)]
    if len(compared) < 2:
        raise ValueError("There are fewer than two rules for this paper's sections to compare. "
                         "Read the guides first: paperkit rules extract")
    for rule in rules:
        rule.conflicts = {}                    # worked out again from scratch every time
    everyone = {r.id.upper(): r for r in rules}

    groups: list[list[WritingRule]] = []
    word_for_word: dict[str, list[WritingRule]] = {}
    for rule in compared:
        word_for_word.setdefault(_key(rule.instruction), []).append(rule)
    groups += [group for group in word_for_word.values() if len(group) > 1]

    # the model sees one category at a time, at most PAPERKIT_CHECK_RULES rules per request
    limit = max(2, int(os.environ.get("PAPERKIT_CHECK_RULES") or "80"))
    by_category: dict[str, list[WritingRule]] = {}
    for rule in compared:
        by_category.setdefault(rule.category, []).append(rule)
    batches: list[tuple[str, list[WritingRule]]] = []
    for category in sorted(by_category):
        rows = sorted(by_category[category], key=lambda r: (sorted(x.lower() for x in r.sections), _number(r)))
        batches += [(category, rows[i:i + limit]) for i in range(0, len(rows), limit) if len(rows[i:i + limit]) > 1]

    agents.LOG_DIR = root / "state" / "log"
    answers: list[tuple[list[WritingRule], RuleCheck]] = []
    failed: list[str] = []
    for number, (category, part) in enumerate(batches, 1):
        listing = "\n".join(f"{r.id} [{', '.join(r.sections)}; {r.priority}; {r.group or 'general'}] {r.instruction}"
                            for r in part)
        digest = hashlib.sha256(json.dumps([COMPARE, listing]).encode("utf-8")).hexdigest()[:24]
        cache = root / ".cache" / "guides" / f"check-{digest}.json"
        where = f"rules: {category} rules, group {number} of {len(batches)} ({len(part)} rules)"
        answer = None
        if cache.is_file() and not fresh:
            try:
                answer = RuleCheck.model_validate_json(cache.read_text(encoding="utf-8"))
                say(f"{where}: answer kept from an earlier run")
            except ValueError:
                answer = None
        if answer is None:
            say(f"{where}: asking the model ...")
            try:
                answer = agents._ask("rules", COMPARE, agents._tag("rules", listing), RuleCheck)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(answer.model_dump_json(), encoding="utf-8")
            except Exception as exc:           # a provider error: the other groups still count
                failed.append(f"{category} rules: {type(exc).__name__}: {_short(exc)}")
                continue
        answers.append((part, answer))

    grouped = {id(r) for group in groups for r in group}
    for part, answer in answers:
        shown = {r.id.upper(): r for r in part}
        for repeat in answer.repeats:
            members: list[WritingRule] = []
            for raw in repeat.ids:
                rule = shown.get(str(raw).strip().upper())
                if (rule is not None and id(rule) not in grouped and rule not in members
                        and all(_overlap(rule, other) for other in members)):
                    members.append(rule)
            if len(members) > 1:
                groups.append(members)
                grouped |= {id(r) for r in members}

    removed: list[tuple[WritingRule, WritingRule]] = []
    for group in groups:
        group = [r for r in group if r.duplicate_of != KEPT_BY_HAND]         # a person kept these: never dropped
        if len(group) < 2:
            continue
        kept = min(group, key=lambda r: (not r.approved, AUTHORITY.get(r.group, 3), STRENGTH.get(r.priority, 3), _number(r)))
        sections = list(dict.fromkeys(x for r in group for x in r.sections))
        kept.sections = ["all"] if "all" in [x.lower() for x in sections] else sections
        kept.priority = min((r.priority for r in group), key=lambda name: STRENGTH.get(name, 3))
        kept.severity = "blocking" if kept.priority == "required" else kept.severity
        for rule in group:
            if rule is kept:
                continue
            kept.avoid_terms += [t for t in rule.avoid_terms if t.lower() not in [k.lower() for k in kept.avoid_terms]]
            rule.duplicate_of, rule.approved = kept.id, False
            removed.append((kept, rule))
        if kept.avoid_terms:
            kept.validation_method = "python"

    found: list[tuple[WritingRule, WritingRule, str]] = []
    for part, answer in answers:
        shown = {r.id.upper(): r for r in part}
        for clash in answer.contradictions:
            pair = []
            for raw in (clash.first, clash.second):
                rule = shown.get(str(raw).strip().upper())
                if rule is not None and dropped(rule):     # it was dropped: the rule it repeats stands in for it
                    rule = everyone.get(rule.duplicate_of.upper())
                pair.append(rule)
            first, second = pair
            if first is None or second is None or first is second or dropped(first) or dropped(second):
                continue
            if not _overlap(first, second) or second.id in first.conflicts:
                continue
            reason = _short(clash.reason) or "They cannot both be followed."
            first.conflicts[second.id] = second.conflicts[first.id] = reason
            found.append((first, second, reason) if _number(first) < _number(second) else (second, first, reason))
    save(root, rules)
    return {"checked": len(compared), "others": len(live) - len(compared), "dropped": removed, "clashes": found,
            "failed": failed}


def restore(root: str | Path, ids) -> list[WritingRule]:
    """Brings back rules that `check` dropped. They become candidates again and are never dropped a second time."""
    rules = load(root)
    wanted = {str(i).upper() for i in ids}
    unknown = sorted(wanted - {r.id.upper() for r in rules})
    if unknown:
        raise ValueError(f"No such rule: {', '.join(unknown)}. `paperkit rules list` shows the ids.")
    back = [r for r in rules if r.id.upper() in wanted and dropped(r)]
    for rule in back:
        rule.duplicate_of = KEPT_BY_HAND
    save(root, rules)
    return back


# ------------------------------------------------------------------ approval

def set_approved(root: str | Path, ids, value: bool) -> list[WritingRule]:
    rules = load(root)
    wanted = {str(i).upper() for i in ids}
    unknown = sorted(wanted - {r.id.upper() for r in rules})
    if unknown:
        raise ValueError(f"No such rule: {', '.join(unknown)}. `paperkit rules list` shows the ids.")
    gone = [r for r in rules if value and r.id.upper() in wanted and dropped(r)]
    if gone:
        raise ValueError(f"{gone[0].id} was dropped because it repeats {gone[0].duplicate_of}. "
                         f"To use it after all: paperkit rules restore {gone[0].id}")
    for rule in rules:
        if rule.id.upper() in wanted:
            rule.approved = value
    save(root, rules)
    return [r for r in rules if r.id.upper() in wanted]


def show(rule: WritingRule) -> list[str]:
    where = rule.source_file + (f", p. {rule.source_page}" if rule.source_page else "")
    mark = "=" if dropped(rule) else "x" if rule.approved else " "
    rows = [f"[{mark}] {rule.id}  {rule.priority}, {', '.join(rule.sections)}: {rule.instruction}",
            f'      "{_short(rule.source_quote or "", 220)}"  ({where})']
    if rule.avoid_terms:
        rows.append(f"      code will flag: {', '.join(rule.avoid_terms)}")
    if dropped(rule):
        rows.append(f"      dropped: it repeats {rule.duplicate_of} (to use it after all: paperkit rules restore {rule.id})")
    for other, reason in rule.conflicts.items():
        rows.append(f"      CONTRADICTS {other}: {reason}")
    return rows


def review(root: str | Path, ask=input, out=print) -> int:
    """Walks through the candidates that are not approved yet. Returns how many were approved."""
    rules = load(root)
    names = paper_sections(root)
    waiting = [r for r in rules if not r.approved and not dropped(r) and relevant(r, names)]
    elsewhere = [r for r in rules if not r.approved and not dropped(r) and not relevant(r, names)]
    if elsewhere:
        other = sorted({x.lower() for r in elsewhere for x in r.sections})
        out(f"{len(elsewhere)} rule(s) are for sections that paper.yaml does not have ({', '.join(other[:8])}"
            f"{', ...' if len(other) > 8 else ''}): you are not asked about them. `paperkit rules list` shows them.")
    count = 0
    try:
        for number, rule in enumerate(waiting, 1):
            out("")
            out(f"Rule {number} of {len(waiting)}")
            for row in show(rule):
                out(row)
            answer = keys.latin(keys.read(
                ask, "[y] approve  [n] leave out  [a] approve this and all the rest  [q] stop > ", out).strip().lower())[:1]
            if answer == "a":
                for rest in waiting[number - 1:]:
                    rest.approved = True
                count += len(waiting) - number + 1
                break
            if answer == "q":
                break
            if answer == "y":
                rule.approved = True
                count += 1
    except EOFError:
        pass
    finally:
        save(root, rules)                      # whatever was decided so far is kept
    return count


# ------------------------------------------------------------------ `paperkit rules`

def run(root: str | Path, action: str = "list", ids=(), everything: bool = False, fresh: bool = False,
        out=print, ask=input) -> int:
    """extract | check | list | approve | reject | restore. Exit code 1 if something failed."""
    root = Path(root)
    try:
        if action == "extract":
            got = extract(root, fresh, out)
            approved = sum(r.approved for r in got["rules"])
            out(f"rules: {len(got['rules'])} candidate(s) from {got['files']} guide file(s) -> rules/candidates.json "
                f"({got['new']} new, {approved} approved)")
            for row in got["dropped"][:10]:
                out(f"  left out: {row}")
            if len(got["dropped"]) > 10:
                out(f"  ... and {len(got['dropped']) - 10} more left out")
            for row in got["failed"]:
                out(f"  failed: {row}")
            if got["failed"]:
                out("Run it again for what failed: finished parts are kept and are not asked again.")
            if len(got["rules"]) > 1:
                out("Next, drop repeated rules and find contradictions: paperkit rules check")
            if len(got["rules"]) > approved:
                out("Nothing is used until you approve it: paperkit rules approve")
            return 1 if got["failed"] else 0

        if action == "check":
            got = check(root, fresh, out)
            out(f"rules: {got['checked']} rule(s) compared."
                + (f" {got['others']} more are for sections that paper.yaml does not have: they were left alone."
                   if got["others"] else ""))
            out(f"Repeats dropped: {len(got['dropped'])}")
            for kept in dict.fromkeys(k.id for k, _ in got["dropped"]):
                first = next(k for k, _ in got["dropped"] if k.id == kept)
                out(f"  {first.id} kept ({first.source_file}, {first.priority}, {', '.join(first.sections)}): {first.instruction}")
                for _, gone in [pair for pair in got["dropped"] if pair[0].id == kept]:
                    out(f"      dropped {gone.id} ({gone.source_file}): {gone.instruction}")
            if got["dropped"]:
                out("  A dropped rule stays in rules/candidates.json. To use one after all: paperkit rules restore <id>")
            out(f"Contradictions: {len(got['clashes'])}" + ("   <- settle these" if got["clashes"] else ""))
            for first, second, reason in got["clashes"]:
                for rule in (first, second):
                    where = rule.source_file + (f", p. {rule.source_page}" if rule.source_page else "")
                    out(f"  {rule.id} ({where}, {rule.priority}{', approved' if rule.approved else ''}): {rule.instruction}")
                out(f"      why: {reason}")
            if got["clashes"]:
                out("  Use one rule of each pair. Take the other out with: paperkit rules reject <id>")
            for row in got["failed"]:
                out(f"  failed: {row}")
            if got["failed"]:
                out("  Those rules were only checked for word-for-word repeats. Run it again: finished groups are kept.")
            in_use = clashes(load(root), approved_only=True)
            for first_id, second_id, _ in in_use:
                out(f"WARNING: {first_id} and {second_id} contradict each other and both are approved.")
            return 1 if got["failed"] or in_use else 0

        rules = load(root)
        if action == "list":
            if not rules:
                out(NONE_YET)
                return 0
            for rule in rules:
                for row in show(rule):
                    out(row)
            live = [r for r in rules if not dropped(r)]
            out(f"{sum(r.approved for r in live)} of {len(live)} approved. Approved rules are in rules/active_rules.json."
                + (f" {len(rules) - len(live)} dropped as repeats [=]." if len(rules) > len(live) else "")
                + (f" {len(clashes(rules))} contradiction(s) to settle." if clashes(rules) else ""))
            return 0
        if not rules:
            out(NONE_YET)
            return 1
        if action == "restore":
            if not ids:
                out("Name the dropped rules to bring back, for example: paperkit rules restore R7")
                return 1
            back = restore(root, ids)
            out(f"{len(back)} rule(s) brought back as candidates" + (f": {', '.join(r.id for r in back)}." if back else "."))
            return 0
        if action == "reject":
            if not ids:
                out("Name the rules to take out, for example: paperkit rules reject R3 R7")
                return 1
            out(f"{len(set_approved(root, ids, False))} rule(s) taken out.")
        elif everything:
            live = [r for r in rules if not dropped(r)]
            for rule in live:
                rule.approved = True
            save(root, rules)
            out(f"All {len(live)} rule(s) approved.")
        elif ids:
            out(f"{len(set_approved(root, ids, True))} rule(s) approved.")
        else:
            out(f"{review(root, ask, out)} rule(s) approved.")
        active = len(load(root, "active_rules"))
        out(f"{active} rule(s) in rules/active_rules.json: the writer and reviewer get the ones for their section.")
        for first_id, second_id, reason in clashes(load(root), approved_only=True):
            out(f"WARNING: {first_id} and {second_id} contradict each other and both are approved: {reason} "
                f"Take one of them out: paperkit rules reject <id>")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        out(f"rules: {type(exc).__name__}: {_short(exc, 300)}")
        return 1
'''
FILES['src/paperkit/ingestion/facts_ingest.py'] = '\n"""Reserved for manifest-driven fact extraction and approval; not implemented yet."""\n'
FILES['src/paperkit/validators/writing_rules.py'] = r'''
"""Writing rules: approved rules that ban specific words or phrases are checked here, in code.

The other approved rules are for the writer and the reviewer, who get them with the section.
"""
from __future__ import annotations

import re

from ..schemas import Issue
from .common import COMMENT, GateContext, paragraphs, short


def check(draft: str, ctx: GateContext) -> list[Issue]:
    rules = [rule for rule in ctx.rules if rule.avoid_terms]
    issues: list[Issue] = []
    if not rules:
        return issues
    for raw, _ in paragraphs(draft):
        text = COMMENT.sub("", raw)
        for term in ctx.spec.term_whitelist:
            text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
        for rule in rules:
            for term in rule.avoid_terms:
                if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
                    issues.append(Issue(gate="rules", severity=rule.severity, excerpt=short(text),
                                        message=f"{rule.id}: avoid '{term}' ({rule.instruction})"))
    return issues
'''

FILES['src/paperkit/ingestion_schemas.py'] = '\n"""Additional schemas for ingestion. Not yet connected to the original pipeline."""\nfrom typing import Literal\nfrom pydantic import BaseModel, Field\nfrom decimal import Decimal\n\n\nclass ScientificFact(BaseModel):\n    id: str\n    text: str\n    analysis: str | None = None\n    outcome: str | None = None\n    predictor: str | None = None\n    modality: str | None = None\n    model: str | None = None\n    sample: str | None = None\n    fold: str | None = None\n    metric: str\n    value: Decimal\n    ci_lower: Decimal | None = None\n    ci_upper: Decimal | None = None\n    confidence_level: Decimal | None = None\n    n: int | None = None\n    unit: str | None = None\n    source_file: str\n    source_row: int | None = None\n    source_column: str | None = None\n    source_sha256: str | None = None\n    approved: bool = False\n\n\nclass MetricSpec(BaseModel):\n    column: str\n    meaning: str\n    unit: str | None = None\n\n\nclass TableSpec(BaseModel):\n    id: str\n    file: str\n    title: str\n    analysis: str\n    grouping_columns: list[str] = Field(default_factory=list)\n    metrics: list[MetricSpec] = Field(default_factory=list)\n\n\nclass TableManifest(BaseModel):\n    tables: list[TableSpec] = Field(default_factory=list)\n\n\nclass SourceDocument(BaseModel):\n    path: str\n    sha256: str\n    citation_key: str | None = None\n    doi: str | None = None\n\n\nclass EvidenceItem(BaseModel):\n    id: str\n    citation_key: str\n    statement: str\n    quotation: str\n    page: int | None = None\n    section: str | None = None\n    verified: bool = False\n\n\nclass LiteratureRecord(BaseModel):\n    source: SourceDocument\n    question: str = ""\n    study_design: str = ""\n    population: str = ""\n    methods: str = ""\n    limitations: list[str] = Field(default_factory=list)\n    evidence: list[EvidenceItem] = Field(default_factory=list)\n\n\nclass ConceptRecord(BaseModel):\n    name: str\n    synthesis: str\n    supporting_evidence_ids: list[str] = Field(default_factory=list)\n    contradicting_evidence_ids: list[str] = Field(default_factory=list)\n    unresolved_questions: list[str] = Field(default_factory=list)\n\n\nclass WritingRule(BaseModel):\n    id: str\n    category: Literal["structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting", "scientific_reasoning"]\n    instruction: str\n    rationale: str = ""\n    sections: list[str] = Field(default_factory=lambda: ["all"])\n    study_designs: list[str] = Field(default_factory=lambda: ["all"])\n    priority: Literal["required", "recommended", "optional"]\n    severity: Literal["blocking", "warning"]\n    validation_method: Literal["python", "ai", "human", "hybrid"]\n    source_file: str\n    source_page: int | None = None\n    source_quote: str | None = None\n    group: str = ""\n    avoid_terms: list[str] = Field(default_factory=list)\n    duplicate_of: str = ""\n    conflicts: dict[str, str] = Field(default_factory=dict)\n    approved: bool = False\n\n\nclass RuleSet(BaseModel):\n    name: str\n    version: str = "1.0"\n    rules: list[WritingRule] = Field(default_factory=list)\n\n\nclass AgentConfig(BaseModel):\n    provider: str = "anthropic"\n    model: str | None = None\n    max_tokens: int = 8000\n\n\nclass AgentRun(BaseModel):\n    agent: str\n    model: str\n    status: str\n    input_tokens: int | None = None\n    output_tokens: int | None = None\n'
FILES['docs/ingestion.md'] = '\n# Extended ingestion layout\n\nPlace literature PDFs in `.papers/` and writing guides in `.writing_guides/`.\nUse CSV/TSV tables in `inputs/tables/` and describe them in `manifest.yaml`.\nThe new schemas live in `ingestion_schemas.py`; the existing schemas.py re-exports them for fresh projects.\nExisting projects can import directly from ingestion_schemas without modifying schemas.py.\nCandidate facts go in facts/candidates.json; the original facts/facts.json and inputs/facts.csv remain compatible with the existing CLI.\nThe new registries are templates, not automatically populated. The PDF and table readers are basic utilities; agent ingestion, approvals, configuration loading and new CLI commands are not implemented, with one exception: writing guides are read by `paperkit rules extract` (see the README).\nThe original wiki reads wiki/<citation-key>.md; wiki/sources and wiki/concepts are reserved for future migration.\nInstall PDF parsing support with python -m pip install pymupdf.\n'

FILES['src/paperkit/schemas.py'] += "\n# Extended ingestion schemas\nfrom .ingestion_schemas import (ScientificFact, MetricSpec, TableSpec, TableManifest, SourceDocument, EvidenceItem, LiteratureRecord, ConceptRecord, WritingRule, RuleSet, AgentConfig, AgentRun)\n"

# ----------------------------------------------------------------------------
# Interactive start screen: input checklist, guided fill-in, menu, dry run
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# src/paperkit/env.py
# ----------------------------------------------------------------------------
FILES['src/paperkit/keys.py'] = r'''
"""Answers typed at a prompt, whatever the keyboard layout, and without crashing on bytes the terminal garbled."""
from __future__ import annotations

RUSSIAN = str.maketrans("йцукенгшщзфывапролдячсмить", "qwertyuiopasdfghjklzxcvbnm")
YES = ("н", "д", "да")          # "н" is the Y key on the Russian layout; "да" is yes


def latin(answer: str) -> str:
    """The same keys read as Latin letters, so a menu letter typed on the Russian layout still works."""
    return answer.translate(RUSSIAN)


def is_yes(answer: str) -> bool:
    answer = answer.strip().lower()
    return answer.startswith("y") or answer in YES


def read(ask, prompt: str, out=print, tries: int = 5) -> str:
    """One answer from `ask`. If the terminal hands over bytes that are not text, the question is asked again.

    That happens when a non-Latin letter is typed and then deleted: the terminal removes only half of the
    letter, and the half that is left cannot be read as text.
    """
    for _ in range(tries):
        try:
            return ask(prompt)
        except UnicodeDecodeError:
            out("That could not be read: a deleted non-Latin letter left a stray byte behind. Please type it again.")
    raise EOFError("no readable answer")
'''

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
from .ingestion import rules_ingest
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
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
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
    for line in HTML_COMMENT.sub("", path.read_text(encoding="utf-8")).splitlines():
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


def _section_ids(root: Path) -> list[str]:
    try:
        raw = yaml.safe_load((root / "paper.yaml").read_text(encoding="utf-8")) or {}
        return [sec["id"] for sec in raw.get("sections", []) if isinstance(sec, dict) and sec.get("id")]
    except Exception:
        return []


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
    if (root / rules_ingest.GUIDES).is_dir():
        found = rules_ingest.state(root)
        detail = ("none" if not found["guides"] and not found["candidates"]
                  else f"{found['guides']} file(s), no rules yet: run `paperkit rules extract`" if not found["candidates"]
                  else f"{found['guides']} file(s), {found['approved']} of {found['relevant']} rule(s) approved"
                  + (f", {found['candidates'] - found['relevant']} for other sections"
                     if found["candidates"] > found["relevant"] else "")
                  + (f", {found['conflicts']} contradiction(s) to settle" if found["conflicts"] else ""))
        checks.append(Check("guides", ".writing_guides/", "Writing guides", "optional", found["approved"] > 0, detail,
                            "the journal's guide for authors and reporting guidelines, as PDF; then `paperkit rules extract`"))
    for sec_id in _section_ids(root):
        draft = root / "inputs" / f"{sec_id}_draft.md"
        if draft.is_file():
            lines = len(content_lines(draft))
            checks.append(Check(f"{sec_id}_draft", f"inputs/{sec_id}_draft.md", f"{sec_id.capitalize()} draft", "optional",
                                lines > 0, f"{lines} line(s): the model starts from it" if lines else "empty: written from scratch",
                                "your own draft, with [KEEP], [CHANGE: ...] and [WRITE: ...] marks"))
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
    return f"  {status}{check.path:<28}{check.label:<21}{check.detail}"


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

from . import agents, build, dryrun, env, evidence, extract, facts, keys, orchestrator, preflight, zotero
from .ingestion import rules_ingest
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
    "f": "Draft facts.csv from the Results section           (calls the API)",
    "k": "Draft key_messages.md from the Results section     (calls the API)",
    "r": "Writing rules: read the guides, check, approve     (reading and checking call the API)",
    "e": "Search the literature for a section's claims       (calls the API and Semantic Scholar)",
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
            answer = keys.read(self._ask, prompt, self.out)       # a garbled answer is asked for again
        except (EOFError, KeyboardInterrupt, StopIteration):
            raise Quit from None
        return answer.strip() if strip else answer.rstrip("\r\n")

    def text(self, prompt: str, default: str = "") -> str:
        return self.ask(f"{prompt}{f' [{default}]' if default else ''}: ") or default

    def confirm(self, prompt: str, default: bool = True) -> bool:
        answer = self.ask(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").lower()
        return default if not answer else keys.is_yes(answer)

    def choose(self, prompt: str, options: dict[str, str], default: str = "") -> str:
        self.out(prompt)
        for key, label in options.items():
            self.out(f"  [{key}] {label}")
        while True:
            answer = self.ask(f"> [{default}] " if default else "> ").lower() or default
            if answer not in options and keys.latin(answer) in options:
                answer = keys.latin(answer)                        # the right key on the Russian layout
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
            return keys.read(self._secret, prompt, self.out).strip()
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
                 f"assumes: {'; '.join(c.assumptions)}" if c.assumptions else "",
                 "added by the evidence search" if c.origin else ""]
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
    table, issues = orchestrator.plan(p, sec_id, ui.out)
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
    status = orchestrator.run_section(p, sec_id, ui.out)
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


def act_rules(ui: UI, root: Path) -> None:
    found = rules_ingest.state(root)
    ui.out(f"{found['guides']} guide file(s) in {rules_ingest.GUIDES}/. {found['relevant']} rule(s) for this paper's "
           f"sections ({found['candidates'] - found['relevant']} more for other sections): {found['approved']} approved, "
           f"{found['dropped']} dropped as repeats, {found['conflicts']} contradiction(s) to settle.")
    choice = ui.choose("What now?", {"x": "read the guides and propose rules (calls the API)",
                                     "c": "check the rules: drop repeats, flag contradictions (calls the API)",
                                     "a": "go through the rules that are not approved yet",
                                     "l": "list all rules", "b": "back"}, default="b")
    if choice == "x" and _confirm_api(ui, "rules"):
        rules_ingest.run(root, "extract", out=ui.out)
    elif choice == "c" and _confirm_api(ui, "rules"):
        rules_ingest.run(root, "check", out=ui.out)
    elif choice == "a":
        rules_ingest.run(root, "approve", out=ui.out, ask=ui.ask)
    elif choice == "l":
        rules_ingest.run(root, "list", out=ui.out)


def act_evidence(ui: UI, root: Path) -> None:
    p = _project(ui, root)
    if p is None:
        return
    sec_id = _section(ui, p)
    found = evidence.counts(evidence.load(root, sec_id))
    ui.out(f"{sec_id}: {found['papers']} suggested paper(s), {found['accepted']} accepted; {found['alternatives']} other "
           f"interpretation(s), {found['alternatives_accepted']} accepted; {found['open']} not decided.")
    choice = ui.choose("What now?", {
        "x": "search the literature for this section's claims (calls the API and Semantic Scholar)",
        "a": "go through the suggestions that have no decision yet",
        "p": "carry the accepted suggestions into the claim table",
        "l": "list all suggestions", "b": "back"}, default="b")
    if choice == "x" and _confirm_api(ui, "literature"):
        evidence.run(root, "search", sec_id, out=ui.out)
    elif choice == "a":
        evidence.run(root, "review", sec_id, out=ui.out, ask=ui.ask)
    elif choice == "p":
        add = evidence.missing_from_library(root, sec_id) > 0 and ui.confirm(
            "Some accepted papers are not in refs/library.bib. Add them to that file now? "
            "Say no if Zotero writes it: import refs/suggested.bib into Zotero instead.", False)
        evidence.run(root, "apply", sec_id, add_to_library=add, out=ui.out)
    elif choice == "l":
        evidence.run(root, "list", sec_id, out=ui.out)


def _draft_from_results(ui: UI, root: Path, what: str) -> None:
    """Menu f and k: the same drafting step that the input checklist offers, reachable at any time."""
    name = "inputs/facts.csv" if what == "facts" else "inputs/key_messages.md"
    untouched = extract.facts_are_default(root) if what == "facts" else extract.messages_are_default(root)
    if not untouched and not ui.confirm(f"{name} already has content and will be replaced. Continue?", False):
        return
    draft_with_model(ui, root, what)


def act_facts(ui: UI, root: Path) -> None:
    _draft_from_results(ui, root, "facts")


def act_key_messages(ui: UI, root: Path) -> None:
    _draft_from_results(ui, root, "key-messages")


ACTIONS = {"1": act_inputs, "2": act_dry_run, "3": act_plan, "4": act_approve,
           "5": act_run, "6": act_validate, "7": act_build, "8": act_status, "9": act_models,
           "f": act_facts, "k": act_key_messages, "r": act_rules, "e": act_evidence}


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


def test_a_long_results_text_is_sent_in_parts_and_the_facts_are_merged(fresh, monkeypatch):
    paragraphs = [f"Paragraph {i} reports a finding with value v{i} = {i}.{i} in the sample. " + "word " * 40
                  for i in range(1, 9)]
    (fresh / "inputs" / "results.md").write_text("# Results\n\n" + "\n\n".join(paragraphs), encoding="utf-8")
    monkeypatch.setenv("PAPERKIT_CHUNK_WORDS", "100")
    seen, said = [], []

    def llm(system, user, schema):
        seen.append(user)
        wanted = [f"v{i} = {i}.{i}" for i in range(1, 9) if f"v{i} = {i}.{i}" in user]
        return extract.FactList(facts=wanted)

    agents.LLM = llm
    got = extract.extract_facts(fresh, say=said.append)
    assert len(seen) > 2 and len(said) == len(seen)                      # several short requests, each announced
    assert max(len(u.split()) for u in seen) < 160                      # none carries the whole text
    assert [r["text"] for r in got["rows"]] == [f"v{i} = {i}.{i}" for i in range(1, 9)]
    assert [r["id"] for r in got["rows"]] == [f"F{i}" for i in range(1, 9)]


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


def test_a_garbled_or_russian_layout_answer_does_not_stop_the_menu(fresh):
    from paperkit import keys

    def typed(*answers):
        feed = iter(answers)

        def ask(prompt=""):
            item = next(feed)
            if isinstance(item, bytes):                               # what a half-deleted Cyrillic letter leaves behind
                item.decode("utf-8")
            return item
        return ask

    printed = []
    ui = wizard.UI(ask=typed(b"\xd0r", "к"), out=printed.append, color=False)
    assert ui.choose("What next?", {"r": "rules", "q": "quit"}) == "r"         # asked again, then the R key in Russian
    assert any("could not be read" in row for row in printed)
    ui = wizard.UI(ask=typed("н", "да", "нет", "т", "", "Y"), out=printed.append, color=False)
    assert [ui.confirm("Go on?", False) for _ in range(6)] == [True, True, False, False, False, True]
    assert keys.latin("й") == "q" and keys.latin("r") == "r"
    ui = wizard.UI(ask=typed(*[b"\xd0"] * 5), out=printed.append, color=False)
    with pytest.raises(wizard.Quit):                                           # never readable: leave, do not loop
        ui.ask("> ")


def test_menu_drafts_facts_and_key_messages_and_asks_before_replacing(fresh):
    assert set(wizard.MENU) == set(wizard.ACTIONS) | {"q"}               # every menu line has its action
    (fresh / "inputs" / "results.md").write_text(RESULTS_TEXT, encoding="utf-8")
    agents.LLM = fake_model(facts=["n = 412"], messages=["Y varies by age group."])
    ui, printed = scripted(["y"])                                        # the files are placeholders: only the API question
    wizard.ACTIONS["f"](ui, fresh)
    ui, printed_k = scripted(["y"])
    wizard.ACTIONS["k"](ui, fresh)
    assert status(fresh)["facts"] is True and status(fresh)["key_messages"] is True
    assert any("F1   n = 412" in row for row in printed) and any("Y varies by age group." in row for row in printed_k)

    agents.LLM = fake_model(facts=["r = 0.29"], messages=["X is associated with Y."])
    ui, printed = scripted(["n"])                                        # real content now: asked first, and "no" keeps it
    wizard.ACTIONS["f"](ui, fresh)
    assert "n = 412" in (fresh / "inputs" / "facts.csv").read_text(encoding="utf-8")
    ui, printed = scripted(["y", "y"])                                   # yes to replacing, yes to the API call
    wizard.ACTIONS["f"](ui, fresh)
    assert "r = 0.29" in (fresh / "inputs" / "facts.csv").read_text(encoding="utf-8")


DRAFT_EMPTY = "<!--\nHOW TO USE\n[WRITE: an example inside the comment]\n-->\n\n## Principal findings\n\n## Limitations\n"
DRAFT_REAL = ("<!--\nHOW TO USE\n-->\n\n## Principal findings\n\nX tracks Y ({{F1}}). [KEEP]\n\n"
              "[WRITE: one paragraph on age differences]\n\nThis is not hedged. [CHANGE: hedge this]\n")


def spy_on_prompts(seen):
    def llm(system, user, schema):
        seen.append((schema.__name__, user))
        return dryrun.stand_in(system, user, schema)
    return llm


def test_default_draft_file_counts_as_empty_and_is_not_sent(fresh):
    path = fresh / "inputs" / "discussion_draft.md"
    path.write_text(DRAFT_EMPTY, encoding="utf-8")
    check = next(c for c in preflight.check_inputs(fresh) if c.key == "discussion_draft")
    assert not check.ok and "written from scratch" in check.detail and check.level == "optional"
    assert orchestrator.Project(fresh).draft("discussion") == ""


def test_the_starting_draft_reaches_planner_and_writer_without_its_comment(fresh):
    fill_all(fresh)
    (fresh / "inputs" / "discussion_draft.md").write_text(DRAFT_REAL, encoding="utf-8")
    check = next(c for c in preflight.check_inputs(fresh) if c.key == "discussion_draft")
    assert check.ok and "starts from it" in check.detail
    seen = []
    agents.LLM = spy_on_prompts(seen)
    p = orchestrator.Project(fresh)
    orchestrator.plan(p, "discussion")
    assert orchestrator.approve(p, "discussion") == []
    assert orchestrator.run_section(p, "discussion") == "DONE"
    for name in ("ClaimList", "Draft"):
        prompt = next(user for schema, user in seen if schema == name)
        assert "<starting_draft>" in prompt and "[CHANGE: hedge this]" in prompt and "HOW TO USE" not in prompt


def test_without_a_draft_file_nothing_is_added_to_the_prompts(fresh):
    fill_all(fresh)
    seen = []
    agents.LLM = spy_on_prompts(seen)
    orchestrator.plan(orchestrator.Project(fresh), "discussion")
    assert all("starting_draft" not in user for _, user in seen)


def test_an_action_marker_left_in_a_draft_is_blocked(fresh):
    fill_all(fresh)
    agents.LLM = dryrun.stand_in
    p = orchestrator.Project(fresh)
    table, _ = orchestrator.plan(p, "discussion")
    draft = "## Principal findings\n\nWe observed an association ({{F1}}). [WRITE: more] <!-- C1 -->\n"
    issues = run_gates(draft, p.ctx("discussion", table))
    assert any(i.gate == "structure" and "Action marker" in i.message and i.excerpt == "[WRITE: more]" for i in issues)

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
- the hosted gateway drops a connection that is silent for 300 s (HTTP 504), and a reasoning model
  thinks for longer than that before a plain answer starts, so answers are streamed: bytes flow
  while the model thinks. PAPERKIT_REASONING sets how much it thinks;
- open models do not always honour a JSON schema, so every answer is validated here and the model
  gets a chance to repair it. Schema-guided decoding is requested first and dropped for a model
  whose endpoint rejects it.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ValidationError

BASE_URL = "https://integrate.api.nvidia.com/v1"    # override with NVIDIA_BASE_URL for a local NIM
REPAIRS = 2                     # extra attempts when an answer does not fit the schema
BACKOFF = (2, 5, 15, 30)        # seconds to wait after HTTP 429 or 5xx, one entry per retry
TIMEOUT = 300                   # seconds without any bytes from the server; PAPERKIT_TIMEOUT overrides
STALL_RETRIES = 1               # a request that got no answer (timeout, HTTP 504, broken stream) is sent once more
RETRYABLE = {429, 500, 502, 503}
STALLED = ("The free endpoint is busy or this model is down: try again later, set PAPERKIT_REASONING=low, "
           "or use another model (`paperkit ping` tests each one)")
HINTS = {
    401: "the key was rejected: check NVIDIA_API_KEY",
    403: "this key has no access to the model",
    404: "model not found: copy the model ID from its page on build.nvidia.com",
    429: "rate limit reached: wait a minute and try again",
}
_NO_GUIDED: set[str] = set()    # models whose endpoint rejected nvext.guided_json


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}" if status else detail)
        self.status, self.detail = status, detail


class Stalled(Exception):
    """The stream ended before the model finished. The gateway does this after 300 s of silence."""


def read_answer(response) -> dict:
    """The answer as one chat completion, whether the server sent plain JSON or a stream of events."""
    if "text/event-stream" not in (response.headers.get("Content-Type") or ""):
        return json.loads(response.read().decode("utf-8"))
    content, reasoning, finish = [], [], None
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue                                    # blank separators and ": keep-alive" comments
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("error") or (event.get("detail") and not event.get("choices")):
            error = event.get("error") or event
            detail = error.get("message") or error.get("detail") if isinstance(error, dict) else error
            status = event.get("status") or (error.get("code") if isinstance(error, dict) else 0)
            raise ApiError(int(status) if str(status).isdigit() else 0, " ".join(str(detail or event).split())[:300])
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            content.append(delta.get("content") or "")
            reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            finish = choice.get("finish_reason") or finish
    if finish is None:
        raise Stalled()
    message = {"role": "assistant", "content": "".join(content), "reasoning_content": "".join(reasoning)}
    return {"choices": [{"message": message, "finish_reason": finish}]}


def reasoning() -> dict:
    """Request fields for PAPERKIT_REASONING: low, high or max set how much the model thinks, off stops it.

    GLM-5.3 always thinks and takes reasoning_effort (its default is max, the slowest).
    Models with a thinking switch (GLM-4.7 to GLM-5.2 and others) take enable_thinking.
    """
    level = (os.environ.get("PAPERKIT_REASONING") or "").strip().lower()
    if not level:
        return {}
    if level in ("off", "none", "false", "0"):
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {"reasoning_effort": level}


def post(url: str, key: str, body: dict) -> dict:
    """POSTs JSON and returns one chat completion. Retries rate limits, server errors and a request that stalled."""
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Accept": "text/event-stream" if body.get("stream") else "application/json"}
    timeout = float(os.environ.get("PAPERKIT_TIMEOUT") or TIMEOUT)
    stalls = 0
    for wait in (*BACKOFF, None):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return read_answer(response)
        except urllib.error.HTTPError as exc:
            detail = " ".join(exc.read().decode("utf-8", "replace").split())[:300]
            if exc.code != 504:
                if exc.code in RETRYABLE and wait is not None:
                    asked = exc.headers.get("Retry-After", "")
                    time.sleep(min(float(asked), 60) if asked.replace(".", "", 1).isdigit() else wait)
                    continue
                raise ApiError(exc.code, detail) from None
            why = "HTTP 504, the gateway got no answer from the model"
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, TimeoutError):
                raise ApiError(0, f"cannot reach {url}: {exc.reason}") from None
            why = f"no connection in {timeout:.0f} s"
        except TimeoutError:
            why = f"no bytes from the server for {timeout:.0f} s"
        except (Stalled, ConnectionError, http.client.HTTPException):
            why = "the answer stopped half way"
        stalls += 1
        if stalls > STALL_RETRIES:
            raise ApiError(0, f"{why}, {stalls} times. {STALLED}") from None
        print(f"  {body.get('model', 'model')}: {why}, trying once more", file=sys.stderr)
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
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2,
                "stream": os.environ.get("PAPERKIT_STREAM", "1") != "0", **reasoning()}
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
        message = choice.get("message") or {}
        text = message.get("content") or message.get("reasoning_content") or ""   # some servers put guided JSON there
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
                 "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "PAPERKIT_GUIDED_JSON", "PAPERKIT_ENV_FILE",
                 "PAPERKIT_REASONING", "PAPERKIT_STREAM", "PAPERKIT_TIMEOUT", "PAPERKIT_MAX_TOKENS"]:
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
    assert body["model"] == "nvidia/some-model" and body["max_tokens"] == 123 and body["stream"] is True
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


def test_post_retries_a_read_timeout_then_gives_a_clean_error(project, monkeypatch):
    import time
    from http.server import ThreadingHTTPServer
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            hits.append(1)
            if len(hits) == 1 or self.path.endswith("/never/chat/completions"):
                time.sleep(1.5)                                  # longer than the 0.3 s timeout
                return
            payload = json.dumps(answer('{"markdown": "slow but fine"}')).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("PAPERKIT_TIMEOUT", "0.3")
        monkeypatch.setenv("NVIDIA_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1/")
        assert nvidia.call("s", "u", Draft, "nvidia/model").markdown == "slow but fine"
        assert len(hits) == 2                                    # one timeout, one retry
        monkeypatch.setenv("NVIDIA_BASE_URL", f"http://127.0.0.1:{server.server_port}/never/")
        hits.clear()
        with pytest.raises(RuntimeError, match="no bytes from the server.*2 times.*free endpoint is busy"):
            nvidia.call("s", "u", Draft, "nvidia/model")
        assert len(hits) == 2                                    # sent once more, then given up
    finally:
        server.shutdown()


def delta(content="", reasoning="", finish=None):
    """One event of a streamed chat completion."""
    return {"choices": [{"delta": {"content": content, "reasoning_content": reasoning}, "finish_reason": finish}]}


def events(*items, done=True):
    rows = [f"data: {json.dumps(item)}\n\n" for item in items] + (["data: [DONE]\n\n"] if done else [])
    return (": keep-alive\n\n" + "".join(rows)).encode()


def test_answers_are_streamed_and_a_stalled_request_is_sent_only_once_more(project, monkeypatch, capsys):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((body, self.headers["Accept"]))
            if self.path.startswith("/gateway/") or (self.path.startswith("/once/") and len(seen) == 1):
                self.send_response(504)                          # what the hosted gateway sends after 300 s of silence
                self.end_headers()
                return
            if not body["stream"]:
                kind, payload = "application/json", json.dumps(answer('{"markdown": "in one piece"}')).encode()
            elif self.path.startswith("/error/"):
                kind, payload = "text/event-stream", events({"error": {"message": "model is overloaded", "code": 503}})
            else:
                cut = self.path.startswith("/cut/")              # the stream just ends: no finish_reason, no [DONE]
                parts = [delta(reasoning="thinking {not the answer}"), delta(content='{"markdown": '),
                         delta(content='"streamed"}')] + ([] if cut else [delta(finish="stop")])
                kind, payload = "text/event-stream", events(*parts, done=not cut)
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def ask(base):
        seen.clear()
        monkeypatch.setenv("NVIDIA_BASE_URL", f"http://127.0.0.1:{server.server_port}/{base}/")
        return nvidia.call("s", "u", Draft, "nvidia/model").markdown

    try:
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        assert ask("v1") == "streamed"                                   # pieces joined, the thinking left out
        body, accept = seen[0]
        assert body["stream"] is True and accept == "text/event-stream"
        assert "reasoning_effort" not in body and "chat_template_kwargs" not in body

        monkeypatch.setenv("PAPERKIT_REASONING", "low")
        assert ask("v1") == "streamed" and seen[0][0]["reasoning_effort"] == "low"
        monkeypatch.setenv("PAPERKIT_REASONING", "off")
        assert ask("v1") == "streamed" and seen[0][0]["chat_template_kwargs"] == {"enable_thinking": False}
        assert "reasoning_effort" not in seen[0][0]
        monkeypatch.setenv("PAPERKIT_REASONING", "")

        monkeypatch.setenv("PAPERKIT_STREAM", "0")
        assert ask("v1") == "in one piece" and seen[0] == (seen[0][0], "application/json")
        assert seen[0][0]["stream"] is False
        monkeypatch.setenv("PAPERKIT_STREAM", "")

        assert ask("once") == "streamed" and len(seen) == 2              # one 504, then the answer
        assert "trying once more" in capsys.readouterr().err
        with pytest.raises(RuntimeError, match="HTTP 504.*2 times.*PAPERKIT_REASONING=low"):
            ask("gateway")
        assert len(seen) == 2                                            # not five rounds of five minutes
        with pytest.raises(RuntimeError, match="the answer stopped half way, 2 times"):
            ask("cut")
        with pytest.raises(RuntimeError, match="HTTP 503: model is overloaded"):
            ask("error")
    finally:
        server.shutdown()


def test_json_that_arrives_in_the_reasoning_field_is_still_read(project, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    reply = {"choices": [{"message": {"content": "", "reasoning_content": '{"markdown": "from reasoning"}'},
                          "finish_reason": "stop"}]}
    monkeypatch.setattr(nvidia, "post", lambda url, key, body: reply)
    assert nvidia.call("s", "u", Draft, "nvidia/model").markdown == "from reasoning"


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
    assert "(planner, writer, facts, rules, literature): ok" in out and "other/model  (reviewer): ok" in out

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
import os
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


def _chunks(text: str, limit: int) -> list[str]:
    """The text cut between paragraphs into pieces of about `limit` words, so no request is long."""
    pieces, current, size = [], [], 0
    for block in re.split(r"\n\s*\n", text):
        words = len(block.split())
        if current and size + words > limit:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += words
    if current:
        pieces.append("\n\n".join(current))
    return [p for p in pieces if p.strip()]


def extract_facts(root: str | Path, force: bool = False, say=lambda text: None) -> dict:
    """inputs/facts.csv and facts/facts.json from the Results and Methods text, a few paragraphs per request."""
    root = Path(root)
    if not force and not facts_are_default(root):
        raise Skip("inputs/facts.csv already has facts (repeat with --force to replace them)")
    _results(root)
    texts = {name: _read(root, name) for name, _ in SOURCES}
    limit = int(os.environ.get("PAPERKIT_CHUNK_WORDS") or "500")
    pieces = [(name, piece) for name, _ in SOURCES for piece in _chunks(texts[name], limit)]
    proposed = []
    for number, (name, piece) in enumerate(pieces, 1):
        say(f"facts: part {number} of {len(pieces)} ({name}, {len(piece.split())} words)")
        proposed += _ask(root, "facts", FACTS, agents._tag(name, piece), FactList).facts
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
            got = extract_facts(root, force, out)
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


# ----------------------------------------------------------------------------
# tests/test_rules.py
# ----------------------------------------------------------------------------
FILES['tests/test_rules.py'] = r'''
"""Writing guides -> rules: reading, checking, approval and use in the pipeline.

No network: the model is replaced by a function that returns prepared answers.
"""
import json

import pytest

from paperkit import agents, orchestrator, preflight, wizard
from paperkit.__main__ import main
from paperkit.ingestion import rules_ingest
from paperkit.ingestion.rules_ingest import Clash, ProposedRule, Repeat, RuleCheck, RuleList
from paperkit.schemas import Claim, ClaimList, Draft, Review
from paperkit.validators import blocking

SPEC = """title: Test paper
design: observational
max_rounds: 3
sections:
  - id: introduction
    title: Introduction
    max_words: 200
    required_headings: [Background]
  - id: discussion
    title: Discussion
    max_words: 200
    required_headings: [Principal findings, Interpretation]
"""
PAGE_1 = ("Instructions for authors\n\nManuscripts are submitted through the online portal. "
          "The fee is paid on accept-\nance of the paper.")
PAGE_2 = ("Discussion\n\nThe Discussion should begin with a brief summary\nof the main findings. "
          "Authors must not use the words “novel” or “paradigm shift” anywhere in the text.\n\n"
          "Limitations of the study must be stated in a separate paragraph.")
SUMMARY = ProposedRule(instruction="Open the Discussion with a short summary of the main findings.",
                       quote="The Discussion should begin with a brief summary of the main findings.",
                       category="structure", sections=["discussion"], priority="recommended")
BANNED = ProposedRule(instruction="Do not use the words novel or paradigm shift.",
                      quote='Authors must not use the words "novel" or "paradigm shift" anywhere in the text',
                      category="language", sections=["all"], priority="required",
                      avoid_terms=["novel", "paradigm shift", "groundbreaking"])      # the last one is invented
LIMITS = ProposedRule(instruction="State the limitations in their own paragraph.",
                      quote="Limitations of the study must be stated", category="odd", sections=["Discussion"],
                      priority="MUST")
INVENTED = ProposedRule(instruction="Keep the abstract under 250 words.",
                        quote="The abstract must not exceed 250 words.", sections=["abstract"])
TOO_SHORT = ProposedRule(instruction="Mention the main findings.", quote="main findings")
FEE = ProposedRule(instruction="Pay the fee when the paper is accepted.",
                   quote="The fee is paid on acceptance of the paper.")

FACTS = {"F1": {"text": "r = 0.31", "source": "Table 2"}, "F2": {"text": "412", "source": "Methods"}}
BIB = "@article{smith2020,\n  title = {A study},\n  author = {Smith, A.},\n  year = {2020},\n}\n"
CLAIMS = [
    Claim(id="C1", text="X is associated with Y.", category="OBSERVED", fact_ids=["F1", "F2"]),
    Claim(id="C2", text="X tracks Y.", category="INFERRED", cite_keys=["smith2020"]),
]
GOOD = """## Principal findings

We observed an association between X and Y ({{F1}}) among {{F2}} participants. <!-- C1 -->

## Interpretation

This suggests that X tracks Y, consistent with earlier work [@smith2020]. <!-- C2 -->
"""
WITH_BANNED_TERM = GOOD.replace("consistent with earlier work", "a paradigm shift consistent with earlier work")


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ["PAPERKIT_GUIDE_WORDS", "PAPERKIT_PROVIDER", "PAPERKIT_MODEL", "ANTHROPIC_API_KEY", "PAPERKIT_ENV_FILE"]:
        monkeypatch.setenv(name, "")
    root = tmp_path / "repo" / "project"
    for folder in ["facts", "refs", "inputs", "wiki", "rules", ".writing_guides/journal"]:
        (root / folder).mkdir(parents=True)
    (root / "paper.yaml").write_text(SPEC, encoding="utf-8")
    (root / "facts" / "facts.json").write_text(json.dumps(FACTS), encoding="utf-8")
    (root / "refs" / "library.bib").write_text(BIB, encoding="utf-8")
    (root / "rules" / "candidates.json").write_text("\n[]\n", encoding="utf-8")       # as the scaffold leaves them
    (root / "rules" / "active_rules.json").write_text("\n[]\n", encoding="utf-8")
    (root / ".writing_guides" / "journal" / ".gitkeep").touch()
    (root / ".writing_guides" / "journal" / "authors.txt").write_text(PAGE_1 + "\f" + PAGE_2, encoding="utf-8")
    yield root
    agents.LLM = None
    agents.CONFIG = {}


def proposes(*rules, calls=None):
    """A model that proposes the same rules for every part of a guide."""
    def llm(system, user, schema):
        assert schema is RuleList
        if calls is not None:
            calls.append(user)
        return RuleList(rules=list(rules))
    return llm


def never(system, user, schema):
    raise AssertionError("the model must not be called")


def stored(root, name="candidates"):
    return json.loads((root / "rules" / f"{name}.json").read_text(encoding="utf-8"))


def test_a_rule_is_kept_only_if_its_quote_is_in_the_guide(project):
    agents.LLM = proposes(SUMMARY, BANNED, INVENTED, LIMITS, TOO_SHORT, FEE)
    got = rules_ingest.extract(project)
    rules = {r["id"]: r for r in stored(project)}
    assert list(rules) == ["R1", "R2", "R3", "R4"] and got["new"] == 4
    assert all(r["source_file"] == ".writing_guides/journal/authors.txt" and r["group"] == "journal"
               and r["approved"] is False for r in rules.values())
    assert rules["R1"]["source_page"] == 2 and rules["R1"]["sections"] == ["discussion"]    # the page comes from code
    assert rules["R2"]["avoid_terms"] == ["novel", "paradigm shift"]                        # the invented term is gone
    assert rules["R2"]["severity"] == "blocking" and rules["R2"]["validation_method"] == "python"
    assert (rules["R3"]["priority"], rules["R3"]["category"], rules["R3"]["sections"]) == ("recommended", "language", ["discussion"])
    assert rules["R4"]["source_page"] == 1                         # "accept-ance" over a line break is still found
    assert len(got["dropped"]) == 2 and "its quote is not in the guide" in got["dropped"][0]
    assert "too short to check" in got["dropped"][1]
    assert stored(project, "active_rules") == []                   # nothing is used before a person approves it


def test_a_second_run_asks_nothing_again_and_keeps_ids_edits_and_approvals(project):
    calls = []
    agents.LLM = proposes(SUMMARY, BANNED, calls=calls)
    rules_ingest.extract(project)
    assert len(calls) == 1
    assert main(["--root", str(project), "rules", "approve", "r1"]) == 0
    edited = stored(project)
    edited[1]["instruction"] = "Never write novel or paradigm shift."                       # a correction by hand
    (project / "rules" / "candidates.json").write_text(json.dumps(edited), encoding="utf-8")

    agents.LLM = never                                             # the saved answer is used
    said = []
    got = rules_ingest.extract(project, say=said.append)
    assert "answer kept from an earlier run" in said[0] and got["new"] == 0
    after = stored(project)
    assert [(r["id"], r["approved"]) for r in after] == [("R1", True), ("R2", False)]
    assert after[1]["instruction"] == "Never write novel or paradigm shift."
    assert [r["id"] for r in stored(project, "active_rules")] == ["R1"]

    agents.LLM = proposes(SUMMARY, LIMITS, calls=calls)             # --fresh asks again
    got = rules_ingest.extract(project, fresh=True)
    assert len(calls) == 2 and got["new"] == 1
    assert [(r["id"], r["approved"]) for r in stored(project)] == [("R1", True), ("R3", False)]


def test_a_failed_part_is_reported_and_only_that_part_is_asked_again(project, monkeypatch, capsys):
    monkeypatch.setenv("PAPERKIT_GUIDE_WORDS", "10")                # every page becomes its own part
    calls = []

    def flaky(system, user, schema):
        calls.append(user)
        if "[page 2]" in user:
            raise RuntimeError("NVIDIA API, model x: HTTP 504")
        return RuleList(rules=[FEE])

    agents.LLM = flaky
    assert main(["--root", str(project), "rules", "extract"]) == 1
    out = capsys.readouterr().out
    assert "part 1 of 2 (page 1)" in out and "failed: .writing_guides/journal/authors.txt, page 2: RuntimeError" in out
    assert "1 candidate(s) from 1 guide file(s)" in out and [r["id"] for r in stored(project)] == ["R1"]

    calls.clear()
    agents.LLM = proposes(SUMMARY, calls=calls)
    assert main(["--root", str(project), "rules", "extract"]) == 0
    assert len(calls) == 1 and "[page 2]" in calls[0]              # page 1 was not asked again
    assert [r["id"] for r in stored(project)] == ["R1", "R2"]


def test_approve_reject_and_list(project, capsys):
    assert main(["--root", str(project), "rules", "list"]) == 0 and "No rules yet" in capsys.readouterr().out
    agents.LLM = proposes(SUMMARY, BANNED, LIMITS)
    assert main(["--root", str(project), "rules", "extract"]) == 0
    assert "Nothing is used until you approve it" in capsys.readouterr().out

    assert main(["--root", str(project), "rules", "approve", "R1", "r2"]) == 0
    assert [r["id"] for r in stored(project, "active_rules")] == ["R1", "R2"]
    assert main(["--root", str(project), "rules", "reject", "R2"]) == 0
    assert [r["id"] for r in stored(project, "active_rules")] == ["R1"]
    assert main(["--root", str(project), "rules", "approve", "R9"]) == 1
    assert "No such rule: R9" in capsys.readouterr().out
    assert main(["--root", str(project), "rules", "list"]) == 0
    out = capsys.readouterr().out
    assert "[x] R1  recommended, discussion:" in out and "[ ] R2  required, all:" in out
    assert "code will flag: novel, paradigm shift" in out and "(.writing_guides/journal/authors.txt, p. 2)" in out
    assert main(["--root", str(project), "rules", "approve", "--all"]) == 0
    assert len(stored(project, "active_rules")) == 3


def test_review_asks_about_each_rule_that_is_not_approved_yet(project):
    agents.LLM = proposes(SUMMARY, BANNED, LIMITS)
    rules_ingest.extract(project)
    answers, printed = iter(["y", "n", "y"]), []
    assert rules_ingest.run(project, "approve", ask=lambda prompt: next(answers), out=printed.append) == 0
    assert [r["id"] for r in stored(project, "active_rules")] == ["R1", "R3"]
    assert "Rule 1 of 3" in printed and "2 rule(s) approved." in printed

    answers = iter(["a"])                                           # one rule is left: approve the rest
    assert rules_ingest.run(project, "approve", ask=lambda prompt: next(answers), out=printed.append) == 0
    assert len(stored(project, "active_rules")) == 3


def pipeline_model(drafts, seen):
    drafts = iter(drafts)

    def llm(system, user, schema):
        seen.append((schema.__name__, user))
        if schema is ClaimList:
            return ClaimList(claims=CLAIMS)
        if schema is Draft:
            return Draft(markdown=next(drafts))
        if schema is Review:
            return Review(issues=[])
        raise AssertionError(schema)
    return llm


def test_approved_rules_reach_the_writer_the_reviewer_and_the_gate(project):
    agents.LLM = proposes(SUMMARY, BANNED, LIMITS)
    rules_ingest.extract(project)
    p = orchestrator.Project(project)
    assert p.rules("discussion") == []                              # candidates alone change nothing
    assert main(["--root", str(project), "rules", "approve", "R1", "R2"]) == 0
    assert [r.id for r in p.rules("discussion")] == ["R1", "R2"]
    assert [r.id for r in p.rules("introduction")] == ["R2"]        # R1 is for the Discussion only

    seen, said = [], []
    agents.LLM = pipeline_model([WITH_BANNED_TERM, GOOD], seen)
    orchestrator.plan(p, "discussion")
    orchestrator.approve(p, "discussion")
    assert orchestrator.run_section(p, "discussion", said.append) == "DONE"
    text = "\n".join(said)
    assert "discussion: 2 approved writing rule(s) apply" in text
    assert "gates    1 problem(s), back to the writer:" in text and "[rules] R2: avoid 'paradigm shift'" in text

    writer = next(user for name, user in seen if name == "Draft")
    reviewer = next(user for name, user in seen if name == "Review")
    for prompt in (writer, reviewer):
        assert "<writing_rules>" in prompt and "Open the Discussion with a short summary" in prompt
        assert "State the limitations" not in prompt                # R3 was never approved
    planner = next(user for name, user in seen if name == "ClaimList")
    assert "<writing_rules>" not in planner

    bad = project / "bad.md"
    bad.write_text(WITH_BANNED_TERM, encoding="utf-8")
    issues = blocking(orchestrator.validate(p, "discussion", bad))
    assert [i.gate for i in issues] == ["rules"] and "R2" in issues[0].message
    assert main(["--root", str(project), "rules", "reject", "R2"]) == 0
    assert orchestrator.validate(orchestrator.Project(project), "discussion", bad) == []


def test_a_real_pdf_is_read_page_by_page(project):
    pymupdf = pytest.importorskip("pymupdf")
    (project / ".writing_guides" / "journal" / "authors.txt").unlink()
    doc = pymupdf.open()
    for text in (PAGE_1, PAGE_2.replace("“", '"').replace("”", '"')):
        page = doc.new_page(width=300, height=500)                  # narrow, so sentences wrap over lines
        page.insert_textbox(pymupdf.Rect(30, 30, 270, 470), text, fontsize=10)
    (project / ".writing_guides" / "reporting").mkdir()
    doc.save(project / ".writing_guides" / "reporting" / "checklist.pdf")

    pages = rules_ingest.read_guide(project / ".writing_guides" / "reporting" / "checklist.pdf")
    assert [number for number, _ in pages] == [1, 2] and "brief summary of the main findings" in pages[1][1]
    agents.LLM = proposes(SUMMARY, BANNED, INVENTED)
    got = rules_ingest.extract(project)
    assert [(r.id, r.source_page, r.group) for r in got["rules"]] == [("R1", 2, "reporting"), ("R2", 2, "reporting")]
    assert got["rules"][0].source_file == ".writing_guides/reporting/checklist.pdf" and len(got["dropped"]) == 1


def test_no_guides_and_a_broken_rule_file_are_said_plainly(project, capsys):
    (project / ".writing_guides" / "journal" / "authors.txt").unlink()
    agents.LLM = never
    assert main(["--root", str(project), "rules", "extract"]) == 1
    assert "No guides found. Put PDF, .md or .txt files in .writing_guides/journal" in capsys.readouterr().out
    (project / "rules" / "candidates.json").write_text("{not json", encoding="utf-8")
    assert main(["--root", str(project), "rules", "list"]) == 1
    assert "rules/candidates.json is not valid" in capsys.readouterr().out


STYLE = ("Style guide\n\nGive the limitations of the study a paragraph of their own. "
         "Authors may describe findings as novel when they are. "
         "The Discussion should begin with a brief summary of the main findings.")
G_LIMITS = ProposedRule(instruction="State the limitations in their own paragraph.",       # word for word as LIMITS
                        quote="Give the limitations of the study a paragraph of their own.", priority="optional")
G_NOVEL = ProposedRule(instruction="You may call a finding novel.", priority="optional",
                       quote="Authors may describe findings as novel when they are.")
G_SUMMARY = ProposedRule(instruction="Begin the Discussion by summarising the main findings.", sections=["discussion"],
                         quote="The Discussion should begin with a brief summary of the main findings.", priority="required",
                         category="structure")
IN_METHODS = ProposedRule(instruction="Describe payment in the Methods.", sections=["methods"],
                          quote="The fee is paid on acceptance of the paper.")
WHY = "One allows the word novel and the other bans it."
COMPARED = RuleCheck(
    repeats=[Repeat(ids=["R3", "r4", "R99"]),              # the same point in other words; R99 does not exist
             Repeat(ids=["R4", "R3"])],                    # the same group named twice: both are taken already
    contradictions=[Clash(first="R2", second="R5", reason=WHY), Clash(first="R5", second="R2", reason="said twice"),
                    Clash(first="R7", second="R4", reason="R7 is for the Methods: it was never shown to the model"),
                    Clash(first="R3", second="R4", reason="a rule cannot clash with its own repeat")])


def two_guides(project, compared=COMPARED):
    """Rules from two guides: R1-R3 from general/style.txt, R4-R7 from journal/authors.txt."""
    (project / ".writing_guides" / "general").mkdir()
    (project / ".writing_guides" / "general" / "style.txt").write_text(STYLE, encoding="utf-8")

    def llm(system, user, schema):
        if schema is RuleList:
            return RuleList(rules=[G_LIMITS, G_NOVEL, G_SUMMARY] if "Style guide" in user
                            else [SUMMARY, BANNED, LIMITS, IN_METHODS])
        if schema is RuleCheck:
            if compared is None:
                raise RuntimeError("NVIDIA API, model x: HTTP 504")
            return compared
        raise AssertionError(schema)

    agents.LLM = llm
    rules_ingest.extract(project)
    return {r["id"]: r for r in stored(project)}


def test_check_drops_repeats_and_flags_contradictions(project, capsys):
    before = two_guides(project)
    assert [r["instruction"] for r in before.values()][:3] == [G_LIMITS.instruction, G_NOVEL.instruction, G_SUMMARY.instruction]
    feed, printed = iter(["c", "y"]), []                              # menu: check the rules, and yes to the API call
    ui = wizard.UI(ask=lambda prompt="": next(feed), out=lambda text="": printed.append(str(text)), color=False)
    wizard.act_rules(ui, project)
    text = "\n".join(printed)
    assert "Repeats dropped: 2" in text and "Contradictions: 1   <- settle these" in text
    assert "R6 kept (.writing_guides/journal/authors.txt, recommended, all)" in text and "dropped R1 (" in text
    assert f"why: {WHY}" in text and "paperkit rules restore <id>" in text

    rules = {r["id"]: r for r in stored(project)}
    assert rules["R1"]["duplicate_of"] == "R6" and rules["R6"]["sections"] == ["all"]      # the journal's wording, the wider scope
    assert rules["R3"]["duplicate_of"] == "R4"
    assert (rules["R4"]["priority"], rules["R4"]["severity"]) == ("required", "blocking")   # the stricter of the two
    assert rules["R2"]["conflicts"] == {"R5": WHY} and rules["R5"]["conflicts"] == {"R2": WHY}
    assert rules["R7"]["conflicts"] == {} and rules["R4"]["conflicts"] == {}
    assert "rules: 6 rule(s) compared. 1 more are for sections that paper.yaml does not have" in text
    assert "language rules, group 1 of 2 (4 rules)" in text and "structure rules, group 2 of 2 (2 rules)" in text
    assert rules_ingest.state(project) == {"guides": 2, "candidates": 5, "relevant": 4, "approved": 0, "dropped": 2,
                                           "conflicts": 1}
    check = next(c for c in preflight.check_inputs(project) if c.key == "guides")
    assert "0 of 4 rule(s) approved, 1 for other sections, 1 contradiction(s) to settle" in check.detail
    asked = []
    assert rules_ingest.review(project, ask=lambda prompt: "q", out=asked.append) == 0      # R7 is not asked about
    assert "1 rule(s) are for sections that paper.yaml does not have (methods)" in asked[0] and "Rule 1 of 4" in asked

    assert main(["--root", str(project), "rules", "list"]) == 0
    out = capsys.readouterr().out
    assert "[=] R1  optional, all:" in out and "dropped: it repeats R6" in out and f"CONTRADICTS R5: {WHY}" in out
    assert "2 dropped as repeats [=]. 1 contradiction(s) to settle." in out

    assert main(["--root", str(project), "rules", "approve", "R1"]) == 1          # a dropped rule cannot be approved
    assert "R1 was dropped because it repeats R6" in capsys.readouterr().out
    assert main(["--root", str(project), "rules", "approve", "--all"]) == 0
    out = capsys.readouterr().out
    assert "All 5 rule(s) approved." in out and "WARNING: R2 and R5 contradict each other and both are approved" in out
    assert [r["id"] for r in stored(project, "active_rules")] == ["R2", "R4", "R5", "R6", "R7"]
    assert main(["--root", str(project), "rules", "check"]) == 1                  # two rules in use contradict: exit code 1

    said = []
    p = orchestrator.Project(project)
    agents.LLM = pipeline_model([GOOD], [])
    orchestrator.plan(p, "discussion")
    orchestrator.approve(p, "discussion")
    assert orchestrator.run_section(p, "discussion", said.append) == "DONE"
    assert any("warning: writing rules R2 and R5 contradict each other" in row for row in said)

    capsys.readouterr()
    assert main(["--root", str(project), "rules", "reject", "R2"]) == 0
    assert "WARNING" not in capsys.readouterr().out
    assert main(["--root", str(project), "rules", "restore", "R1"]) == 0
    assert "1 rule(s) brought back as candidates: R1." in capsys.readouterr().out
    two = COMPARED                                                    # the same answer again: R1 is not dropped twice
    agents.LLM = lambda system, user, schema: two
    assert main(["--root", str(project), "rules", "check", "--fresh"]) == 0
    rules = {r["id"]: r for r in stored(project)}
    assert rules["R1"]["duplicate_of"] == "none" and rules["R1"]["approved"] is False
    assert rules["R3"]["duplicate_of"] == "R4" and rules["R5"]["conflicts"] == {"R2": WHY}


def test_check_still_drops_word_for_word_repeats_when_the_model_fails(project, capsys):
    two_guides(project, compared=None)
    assert main(["--root", str(project), "rules", "check"]) == 1
    out = capsys.readouterr().out
    assert "Repeats dropped: 1" in out and "dropped R1 (" in out and "Contradictions: 0" in out
    assert "failed: language rules: RuntimeError: NVIDIA API, model x: HTTP 504" in out
    assert "failed: structure rules: RuntimeError" in out and "finished groups are kept" in out
    (project / "rules" / "candidates.json").write_text("[]", encoding="utf-8")
    assert main(["--root", str(project), "rules", "check"]) == 1
    assert "fewer than two rules for this paper's sections to compare" in capsys.readouterr().out


def test_checklist_and_menu_show_the_guides(project):
    check = next(c for c in preflight.check_inputs(project) if c.key == "guides")
    assert not check.ok and check.level == "optional" and "1 file(s), no rules yet" in check.detail

    feed, printed = iter(["x", "y"]), []                            # read the guides, and yes to the API call
    ui = wizard.UI(ask=lambda prompt="": next(feed), out=lambda text="": printed.append(str(text)), color=False)
    agents.LLM = proposes(SUMMARY, BANNED)
    wizard.act_rules(ui, project)
    assert any("2 candidate(s) from 1 guide file(s)" in row for row in printed)

    feed = iter(["a", "y", "n"])                                    # review: approve the first, leave out the second
    wizard.act_rules(ui, project)
    assert [r["id"] for r in stored(project, "active_rules")] == ["R1"]
    check = next(c for c in preflight.check_inputs(project) if c.key == "guides")
    assert check.ok and "1 of 2 rule(s) approved" in check.detail
'''


# ----------------------------------------------------------------------------
# tests/test_evidence.py
# ----------------------------------------------------------------------------
FILES['tests/test_evidence.py'] = r'''
"""Evidence search: Semantic Scholar client, screening, your decisions, and what reaches the claim table.

No network: the search service and the model are replaced.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from paperkit import agents, evidence, orchestrator, scholar, wizard, zotero
from paperkit.__main__ import main
from paperkit.evidence import Alternative, Assessment, SearchList, Searches, Verdict
from paperkit.schemas import Claim, ClaimList, ClaimTable
from paperkit.validators import blocking, check_claims

SPEC = """title: Test paper
design: observational
max_rounds: 3
sections:
  - id: discussion
    title: Discussion
    max_words: 400
    required_headings: [Principal findings, Interpretation]
"""
FACTS = {"F1": {"text": "r = 0.31", "source": "Table 2"}}
BIB = ("@article{lee2019,\n  title = {A known paper on sleep},\n  author = {Lee, C.},\n  year = {2019},\n"
       "  doi = {10.1000/KNOWN},\n}\n")
CLAIMS = [
    Claim(id="C1", text="Longer sleep was associated with better memory.", category="OBSERVED", fact_ids=["F1"]),
    Claim(id="C2", text="Sleep may support memory consolidation in adolescents.", category="INFERRED"),
    Claim(id="C3", text="Sleep diaries measured sleep without bias.", category="ASSUMED"),
]


def record(paper_id, title, abstract, doi="", year=2020, authors=("Ana Smith", "Bo Jones"), citations=10):
    return {"paper_id": paper_id, "title": title, "authors": list(authors), "year": year, "venue": "Journal of Sleep",
            "doi": doi, "url": f"https://doi.org/{doi}" if doi else f"https://example.org/{paper_id}",
            "abstract": abstract, "citations": citations}


SUPPORT = record("p1", "Sleep and memory in adolescents",
                 "We studied 300 adolescents. Longer sleep was associated with better memory scores. Effects were stable.",
                 "10.1000/sleep.1", citations=152)
AGAINST = record("p2", "No link between sleep and memory in adults",
                 "In 900 adults we found no association between sleep duration and memory performance.",
                 "10.1000/sleep.2", year=2021, authors=("Dae Kim",))
NO_ABSTRACT = record("p3", "Sleep and recall: a cohort study", "", "10.1000/sleep.3")
OFF_TOPIC = record("p4", "Sleep in fruit flies", "Fruit flies sleep at night. We describe their rest in detail.")
KNOWN = record("p5", "A known paper on sleep", "Sleep matters for many outcomes across the life span.", "10.1000/known",
               year=2019, authors=("Chen Lee",))
INTERPRETATION = "The association may reflect family income rather than sleep itself."


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ["PAPERKIT_PROVIDER", "PAPERKIT_MODEL", "ANTHROPIC_API_KEY", "PAPERKIT_ENV_FILE",
                 "SEMANTIC_SCHOLAR_API_KEY", "SEMANTIC_SCHOLAR_BASE_URL", "PAPERKIT_SEARCH_RESULTS"]:
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(scholar, "PAUSE", 0)
    monkeypatch.setattr(scholar, "BACKOFF", (0, 0))
    root = tmp_path / "repo" / "project"
    for folder in ["facts", "refs", "inputs", "wiki", "state"]:
        (root / folder).mkdir(parents=True)
    (root / "paper.yaml").write_text(SPEC, encoding="utf-8")
    (root / "facts" / "facts.json").write_text(json.dumps(FACTS), encoding="utf-8")
    (root / "refs" / "library.bib").write_text(BIB, encoding="utf-8")
    (root / "inputs" / "methods.md").write_text("# Methods\n\nA cross-sectional survey of adolescents.\n", encoding="utf-8")
    (root / "inputs" / "limitations.md").write_text("# Limitations\n\n- Cross-sectional\n", encoding="utf-8")
    p = orchestrator.Project(root)
    p.save_claims(ClaimTable(section_id="discussion", approved=True, claims=[c.model_copy() for c in CLAIMS]))
    p.set_status("discussion", "APPROVED")
    yield root
    agents.LLM = None
    agents.CONFIG = {}


def fake_search(queries):
    """Stands in for scholar.search: the same five papers for every query, and a note of what was asked."""
    def search(query, limit=5, cache_dir=None, fresh=False):
        queries.append(query)
        return [dict(found) for found in (SUPPORT, AGAINST, NO_ABSTRACT, OFF_TOPIC, KNOWN)]
    return search


def model(calls=None):
    """A model that writes searches for C1 only, and judges papers by their titles."""
    def llm(system, user, schema):
        if calls is not None:
            calls.append(schema.__name__)
        if schema is SearchList:
            return SearchList(searches=[Searches(claim_id="C1", supporting="sleep duration memory adolescents",
                                                 contradicting="sleep memory no-association null",
                                                 alternative="sleep memory confounding income")])
        assert schema is Assessment
        numbers = {title: int(n) for n, title in re.findall(r"^\[(\d+)\] (.+?) \(", user, re.M)}
        verdicts = [
            Verdict(paper=numbers[SUPPORT["title"]], stance="supports", note="A cohort of adolescents showed the same pattern.",
                    quote="Longer sleep was associated with better memory scores."),
            Verdict(paper=numbers[AGAINST["title"]], stance="Contradicts", note="A large adult sample showed no such link.",
                    quote="we found no association between sleep duration and memory performance"),
            Verdict(paper=numbers[OFF_TOPIC["title"]], stance="unrelated"),
            Verdict(paper=numbers[KNOWN["title"]], stance="supports", note="It agrees.",
                    quote="Sleep strongly improves memory in every age group."),             # not in the abstract
            Verdict(paper=99, stance="supports", quote="made up", note="made up"),
        ]
        return Assessment(verdicts=verdicts, alternatives=[Alternative(
            interpretation=INTERPRETATION, kind="Confounding", papers=[numbers[SUPPORT["title"]], 99],
            check="Adjusting for household income would separate the two readings.")])
    return llm


def never(system, user, schema):
    raise AssertionError("the model must not be called")


def stored(root):
    return json.loads((root / "state" / "evidence" / "discussion.json").read_text(encoding="utf-8"))


def searched(root, monkeypatch, queries=None):
    monkeypatch.setattr(scholar, "search", fake_search(queries if queries is not None else []))
    agents.LLM = model()
    return evidence.search(root, "discussion")


def test_a_label_is_kept_only_if_its_quote_is_in_the_abstract(project, monkeypatch):
    queries = []
    got = searched(project, monkeypatch, queries)
    assert got["failed"] == []
    findings = stored(project)["findings"]
    assert [f["claim_id"] for f in findings] == ["C1", "C2"]                 # the ASSUMED claim is not searched
    first = findings[0]
    assert [(row["id"], row["paper_id"], row["stance"]) for row in first["papers"]] == [
        ("E1", "p1", "supports"), ("E2", "p2", "contradicts"), ("E3", "p5", "unclear"), ("E4", "p3", "not screened")]
    assert first["papers"][0]["quote"] == "Longer sleep was associated with better memory scores."
    assert first["papers"][2]["quote"] == "" and first["papers"][2]["in_library"] == "lee2019"   # found by its DOI
    assert first["unrelated"] == 1 and all(row["decision"] == "" for row in first["papers"])
    assert first["alternatives"] == [{"id": "A1", "interpretation": INTERPRETATION, "kind": "confounding",
                                      "check": "Adjusting for household income would separate the two readings.",
                                      "papers": ["E1"], "decision": "", "claim": ""}]
    assert [row["id"] for row in findings[1]["papers"]] == ["E5", "E6", "E7", "E8"]

    assert queries[:3] == ["sleep duration memory adolescents", "sleep memory no association null",
                           "sleep memory confounding income"]                # as cleaned: no hyphen
    assert queries[3] == "Sleep may support memory consolidation in adolescents."     # C2: the model wrote no search

    report = (project / "build" / "evidence_discussion.md").read_text(encoding="utf-8")
    assert "### Supports (1)" in report and "### Contradicts (1)" in report and "### Other interpretations" in report
    assert "### Not screened: no abstract available (1)" in report and "In your library as [@lee2019]" in report
    assert "- [ ] E1  Ana Smith, Bo Jones (2020). Sleep and memory in adolescents. Journal of Sleep." in report


def test_no_claim_table_and_a_dead_search_service_are_said_plainly(project, monkeypatch, capsys):
    def down(query, limit=5, cache_dir=None, fresh=False):
        raise scholar.SearchError("Semantic Scholar is not answering (HTTP 429, 3 tries). " + scholar.KEY_HINT)

    monkeypatch.setattr(scholar, "search", down)
    agents.LLM = model()
    assert main(["--root", str(project), "evidence", "search", "discussion"]) == 1
    out = capsys.readouterr().out
    assert "failed: C1: Semantic Scholar is not answering" in out and "SEMANTIC_SCHOLAR_API_KEY" in out
    assert out.count("  failed: ") == 1                               # it did not go on to hammer the service for C2

    (project / "state" / "claims" / "discussion.json").unlink()
    assert main(["--root", str(project), "evidence", "search"]) == 1          # one section: its name can be left out
    assert "No claim table for 'discussion'. Plan the section first" in capsys.readouterr().out


def test_accepted_suggestions_reach_the_claim_table_only_through_the_library(project, monkeypatch, capsys):
    searched(project, monkeypatch)
    answers = iter(["y", "y", "n", "l", "y", "q"])                    # E1, E2 accepted; E3 rejected; E4 later; A1 accepted
    printed = []
    assert evidence.run(project, "review", "discussion", ask=lambda prompt: next(answers), out=printed.append) == 0
    text = "\n".join(printed)
    assert "1 of 10, for C1:" in text and "3 suggestion(s) accepted." in text
    rows = {row["id"]: row for f in stored(project)["findings"] for row in f["papers"] + f["alternatives"]}
    assert [rows[i]["decision"] for i in ("E1", "E2", "E3", "E4", "A1", "E5")] == [
        "accepted", "accepted", "rejected", "", "accepted", ""]

    # the two accepted papers are not in the library yet: a .bib file to import, and no claim cites them
    suggested = (project / "refs" / "suggested.bib").read_text(encoding="utf-8")
    assert "@article{smith2020sleep," in suggested and "@article{kim2021link," in suggested
    assert "2 accepted paper(s) are not in refs/library.bib yet" in text and "New claims in the claim table: C4" in text
    p = orchestrator.Project(project)
    table = p.load_claims("discussion")
    assert [(c.id, c.category, c.cite_keys, c.origin) for c in table.claims[3:]] == [
        ("C4", "SPECULATIVE", [], "evidence search")] and table.claims[3].text == INTERPRETATION
    assert table.approved is False and p.status()["discussion"] == "AWAITING_APPROVAL"
    assert BIB == (project / "refs" / "library.bib").read_text(encoding="utf-8")       # the library was not touched

    # Zotero exports the same papers under its own keys: they are found by DOI
    (project / "refs" / "library.bib").write_text(
        BIB + "@article{smithSleepMemory2020,\n  title = {Sleep and memory in adolescents},\n  doi = {10.1000/sleep.1},\n}\n"
        "@article{kimNoLink2021,\n  title = {No link between sleep and memory in adults},\n"
        "  doi = {https://doi.org/10.1000/SLEEP.2},\n}\n", encoding="utf-8")
    assert main(["--root", str(project), "evidence", "apply", "discussion"]) == 0
    out = capsys.readouterr().out
    assert "New claims in the claim table: C5, C6" in out and "Sources added to claims: C4" in out
    assert "Wiki pages written" in out and "paperkit approve discussion" in out
    table = orchestrator.Project(project).load_claims("discussion")
    added = {c.id: c for c in table.claims[3:]}
    assert added["C4"].cite_keys == ["smithSleepMemory2020"]          # the paper its interpretation rests on
    assert added["C5"].cite_keys == ["smithSleepMemory2020"] and added["C5"].category == "INFERRED"
    assert added["C5"].text == ("Earlier work agrees with our finding (Longer sleep was associated with better memory): "
                                "A cohort of adolescents showed the same pattern.")
    assert added["C6"].cite_keys == ["kimNoLink2021"] and added["C6"].text.startswith("Earlier work disagrees with our finding")
    p = orchestrator.Project(project)
    assert blocking(check_claims(table, p.facts, set(p.bib))) == []
    page = (project / "wiki" / "smithSleepMemory2020.md").read_text(encoding="utf-8")
    assert "## Key findings" in page and '> "Longer sleep was associated with better memory scores." (abstract)' in page
    assert "[[kimNoLink2021]]" in (project / "wiki" / "index.md").read_text(encoding="utf-8")
    assert not (project / "refs" / "suggested.bib").exists()

    assert main(["--root", str(project), "evidence", "apply", "discussion"]) == 0      # repeating it adds nothing
    assert "Nothing to carry over" in capsys.readouterr().out
    table.claims = [c for c in table.claims if c.id != "C6"]          # you delete a claim: it does not come back
    p.save_claims(table)
    assert main(["--root", str(project), "evidence", "apply", "discussion"]) == 0
    assert [c.id for c in orchestrator.Project(project).load_claims("discussion").claims] == ["C1", "C2", "C3", "C4", "C5"]


def test_accept_by_id_can_add_the_paper_to_a_library_kept_by_hand(project, monkeypatch, capsys):
    searched(project, monkeypatch)
    assert main(["--root", str(project), "evidence", "accept", "E1", "--add-to-library"]) == 0     # section left out
    out = capsys.readouterr().out
    assert "1 suggestion(s) accepted." in out and "Added to refs/library.bib: smith2020sleep" in out
    bib = zotero.load_bib(project / "refs" / "library.bib")
    assert bib["smith2020sleep"]["doi"] == "10.1000/sleep.1" and bib["smith2020sleep"]["author"] == "Ana Smith and Bo Jones"
    assert "lee2019" in bib
    table = orchestrator.Project(project).load_claims("discussion")
    assert table.claims[-1].cite_keys == ["smith2020sleep"] and (project / "wiki" / "smith2020sleep.md").exists()
    assert main(["--root", str(project), "evidence", "reject", "discussion", "E99"]) == 1
    assert "No such suggestion: E99" in capsys.readouterr().out
    assert main(["--root", str(project), "evidence", "list", "discussion"]) == 0
    out = capsys.readouterr().out
    assert "[x] E1  supports: Ana Smith, Bo Jones (2020)" in out and "1 of 8 paper(s) and 0 of 2 interpretation(s) accepted" in out


def test_a_second_search_asks_the_model_nothing_and_keeps_your_decisions(project, monkeypatch):
    searched(project, monkeypatch)
    evidence.decide(project, "discussion", ["E2", "A1"], "accepted")
    before = stored(project)
    agents.LLM = never                                                # every answer comes from .cache/evidence/
    said = []
    evidence.search(project, "discussion", say=said.append)
    after = stored(project)
    assert [[(r["id"], r["decision"]) for r in f["papers"] + f["alternatives"]] for f in after["findings"]] == \
           [[(r["id"], r["decision"]) for r in f["papers"] + f["alternatives"]] for f in before["findings"]]
    calls = []
    agents.LLM = model(calls)
    evidence.search(project, "discussion", fresh=True)                # --fresh asks again
    assert calls == ["SearchList", "Assessment", "Assessment"]


def test_claims_added_by_the_search_are_not_searched_and_the_planner_cannot_fake_their_mark(project, monkeypatch):
    table = orchestrator.Project(project).load_claims("discussion")
    table.claims.append(Claim(id="C4", text="Earlier work agrees.", category="INFERRED", origin="evidence search"))
    assert [c.id for c in evidence.targets(table)] == ["C1", "C2"]
    agents.LLM = lambda system, user, schema: ClaimList(claims=[c.model_copy(update={"origin": "evidence search"}) for c in CLAIMS])
    planned, _ = orchestrator.plan(orchestrator.Project(project), "discussion")
    assert [c.origin for c in planned.claims] == ["", "", ""]


def api_record(found):
    return {"paperId": found["paper_id"], "title": found["title"], "abstract": found["abstract"] or None,
            "year": found["year"], "venue": found["venue"], "citationCount": found["citations"],
            "url": f"https://www.semanticscholar.org/paper/{found['paper_id']}",
            "externalIds": {"DOI": found["doi"].upper(), "CorpusId": 1} if found["doi"] else {"CorpusId": 1},
            "authors": [{"authorId": "1", "name": name} for name in found["authors"]]}


def test_the_client_paces_retries_caches_and_reads_the_api_format(project, monkeypatch, tmp_path):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            seen.append((url.path, parse_qs(url.query), self.headers.get("x-api-key")))
            status = 403 if url.path.startswith("/denied/") else 429 if url.path.startswith("/busy/") or len(seen) == 1 else 200
            body = json.dumps({"total": 2, "offset": 0, "data": [api_record(SUPPORT), api_record(NO_ABSTRACT),
                                                                   {"paperId": None, "title": "no id"}]}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body if status == 200 else b'{"message": "Too Many Requests"}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setenv("SEMANTIC_SCHOLAR_BASE_URL", base + "/graph/v1/")
        monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-key")
        papers = scholar.search('"sleep-duration" AND memory', 7, tmp_path / "cache")
        assert [p["paper_id"] for p in papers] == ["p1", "p3"]                # the record with no id is dropped
        assert papers[0] == SUPPORT and papers[1]["abstract"] == ""            # same shape, DOI in lower case
        assert len(seen) == 2 and seen[0][0] == "/graph/v1/paper/search"       # one 429, then the answer
        assert seen[1][1]["query"] == ["sleep duration AND memory"] and seen[1][1]["limit"] == ["7"]
        assert "abstract" in seen[1][1]["fields"][0] and seen[1][2] == "s2-key"
        assert scholar.search('"sleep-duration" AND memory', 7, tmp_path / "cache") == papers and len(seen) == 2    # from the cache

        monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
        monkeypatch.setenv("SEMANTIC_SCHOLAR_BASE_URL", base + "/busy/")
        with pytest.raises(scholar.SearchError, match="not answering .HTTP 429, 3 tries.. Without a key"):
            scholar.search("sleep memory")
        assert seen[-1][2] is None                                             # no key, no header
        monkeypatch.setenv("SEMANTIC_SCHOLAR_BASE_URL", base + "/denied/")
        with pytest.raises(scholar.SearchError, match="rejected the key"):
            scholar.search("sleep memory")
    finally:
        server.shutdown()


def test_keys_and_entries_for_new_references(project):
    found = record("p9", "The Sleep–Memory Link {revisited}", "", "10.1/x", authors=("José Álvarez-García",))
    assert scholar.cite_key(found, []) == "alvarezgarcia2020sleep"
    assert scholar.cite_key(found, ["alvarezgarcia2020sleep"]) == "alvarezgarcia2020sleepa"
    entry = scholar.bibtex(found, "alvarezgarcia2020sleep")
    assert "title = {The Sleep–Memory Link revisited}," in entry and entry.endswith("\n}\n")
    assert scholar.library_key({"k1": {"title": "the sleep memory link revisited"}}, {**found, "doi": ""}) == "k1"
    assert scholar.library_key({"k1": {"title": "Something else"}}, found) == ""


def test_menu_entry_searches_reviews_and_carries_over(project, monkeypatch):
    monkeypatch.setattr(scholar, "search", fake_search([]))
    agents.LLM = model()
    assert "e" in wizard.MENU and set(wizard.MENU) == set(wizard.ACTIONS) | {"q"}
    feed, printed = iter(["x", "y"]), []                                       # search, and yes to the API call
    ui = wizard.UI(ask=lambda prompt="": next(feed), out=lambda text="": printed.append(str(text)), color=False)
    wizard.act_evidence(ui, project)
    assert any("8 paper(s) and 2 other interpretation(s) for 2 claim(s)" in row for row in printed)

    feed = iter(["a", "y", "q"])                                               # review: accept E1, then stop
    wizard.act_evidence(ui, project)
    feed = iter(["p", "y"])                                                    # carry over, adding the paper to library.bib
    wizard.act_evidence(ui, project)
    assert any("Added to refs/library.bib: smith2020sleep" in row for row in printed)
    table = orchestrator.Project(project).load_claims("discussion")
    assert table.claims[-1].origin == "evidence search" and table.approved is False
    shown = []
    wizard.show_claims(wizard.UI(out=shown.append, color=False), table)
    assert any("added by the evidence search" in row for row in shown)
'''


ENV_TEXT = """# GitHub (used by publish.sh)
GITHUB_USER=
GITHUB_TOKEN=
VISIBILITY=private

# Model providers (used by paperkit)
NVIDIA_API_KEY=
ANTHROPIC_API_KEY=

# Literature search (paperkit evidence). Free key: semanticscholar.org/product/api. Works without, but is often refused.
SEMANTIC_SCHOLAR_API_KEY=

# Optional: one provider and model for every agent, instead of config/models.yaml
# PAPERKIT_PROVIDER=nvidia
# PAPERKIT_MODEL=z-ai/glm-5.3

# Optional, NVIDIA only: how much a reasoning model thinks (low, high, max, or off). Low is the fastest.
# PAPERKIT_REASONING=low
# PAPERKIT_MAX_TOKENS=16000
"""

# Repository-wide ignore rules. A rule without a leading slash applies at any depth.
IGNORE_RULES = [
    ".env", ".venv/", "__pycache__/", "*.egg-info/", ".pytest_cache/",
    ".DS_Store", "Thumbs.db", "~$*",
    "build/", "state/log/", ".papers/", ".writing_guides/", ".cache/",
    "inputs/", "drafts/", "state/", "facts/",                # your inputs and everything the pipeline writes
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
            is_code = rel.startswith(("src/", "tests/", "docs/")) or rel == "README.md"    # code and its documentation
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