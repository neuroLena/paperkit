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
