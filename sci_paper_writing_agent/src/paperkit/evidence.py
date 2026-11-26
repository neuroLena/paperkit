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

from . import agents, env, keys, orchestrator, scholar, zotero
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
        if earlier and _key(earlier.get("text")) != _key(claim.text):
            earlier = {}                       # the table was planned again: this id is a different claim now
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
    new, grown = [], []
    planned = {c.id: c for c in table.claims if c.origin != ORIGIN}
    mine = {c.id for c in table.claims if c.origin == ORIGIN}

    # A note of an added claim is dropped when that id is no longer a claim of this step: the table was planned
    # again (nothing of ours is left), or the id now belongs to a claim of the planner's.
    noted: list[str] = []
    for finding in data["findings"]:
        slots = finding.setdefault("claims", {})
        for slot, claim_id in list(slots.items()):
            noted.append(claim_id)
            if not mine or (claim_id in by_id and claim_id not in mine):
                del slots[slot]
        for other in finding["alternatives"]:
            claim_id = other.get("claim", "")
            noted.append(claim_id)
            if claim_id and (not mine or (claim_id in by_id and claim_id not in mine)):
                other["claim"] = ""
    # new ids start above every id in the table and every id ever noted, so an id is never used twice
    last = max([int(i[1:]) for i in [*by_id, *noted] if re.fullmatch(r"C\d+", i)] or [0])

    def carry(holder: dict, slot: str, text: str, category: str, cite_keys: list[str]) -> None:
        nonlocal last
        claim_id = holder.get(slot, "")
        if claim_id:
            claim = by_id.get(claim_id)
            if claim is None:
                return                         # you deleted this one claim from the table: it is not added again
            fresh_keys = [k for k in cite_keys if k not in claim.cite_keys]
            if fresh_keys:                     # added before: only new sources are added, your wording stays
                claim.cite_keys += fresh_keys
                grown.append(claim_id)
            return
        last += 1                              # never added, or the table was planned again since then
        claim = Claim(id=f"C{last}", text=text, category=category, cite_keys=cite_keys, origin=ORIGIN)
        table.claims.append(claim)
        by_id[claim.id] = claim
        holder[slot] = claim.id
        new.append(claim.id)

    stale = 0
    for finding in data["findings"]:
        finding.setdefault("claims", {})
        claim_now = planned.get(finding.get("claim_id"))
        if claim_now is None or _key(claim_now.text) != _key(finding.get("text")):
            # the claim this was found for is gone or reworded (the table was planned again or edited)
            stale += sum(row.get("decision") == "accepted" for row in finding["papers"] + finding["alternatives"])
            continue
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
            "waiting": [_line(row["title"], 90) for row in missing], "stale": stale}


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
    if done["stale"]:
        out(f"{done['stale']} accepted suggestion(s) belong to claims that are no longer in the claim table "
            "(it was planned again or edited), so they were left out.")
        out(f"Search again for the claims as they are now: paperkit evidence search {sec_id}")
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
            if got["failed"] and not scholar.has_key():
                out(f"No SEMANTIC_SCHOLAR_API_KEY was found. paperkit looked in {env.env_path(root)} and in the shell: "
                    "check that the line is in that file, is spelled this way and has no # in front.")
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
