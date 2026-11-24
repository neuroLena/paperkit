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
3. `paperkit facts` builds `facts/facts.json` from `inputs/facts.csv`.
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



## Extended ingestion layout

See [docs/ingestion.md](docs/ingestion.md) for new input folders and current implementation limits.
