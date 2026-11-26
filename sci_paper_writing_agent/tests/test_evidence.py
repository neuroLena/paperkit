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
    def search(query, limit=5, cache_dir=None, fresh=False, notify=None):
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
    def down(query, limit=5, cache_dir=None, fresh=False, notify=None):
        raise scholar.SearchError("Semantic Scholar is not answering (HTTP 429, 3 tries). " + scholar.KEY_HINT)

    monkeypatch.setattr(scholar, "search", down)
    agents.LLM = model()
    assert main(["--root", str(project), "evidence", "search", "discussion"]) == 1
    out = capsys.readouterr().out
    assert "failed: C1: Semantic Scholar is not answering" in out and "SEMANTIC_SCHOLAR_API_KEY" in out
    assert f"No SEMANTIC_SCHOLAR_API_KEY was found. paperkit looked in {project.parent / '.env'} and in the shell" in out
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


def test_planning_again_brings_accepted_suggestions_back_and_never_touches_the_wrong_claim(project, monkeypatch, capsys):
    searched(project, monkeypatch)
    assert main(["--root", str(project), "evidence", "accept", "discussion", "E1", "A1", "--add-to-library"]) == 0
    p = orchestrator.Project(project)
    first = p.load_claims("discussion")
    assert [(c.id, c.origin) for c in first.claims[3:]] == [("C4", "evidence search"), ("C5", "evidence search")]

    # planned again with the same claims: C4 is now a new claim of the planner's, and the two added claims are gone
    again = [c.model_copy() for c in CLAIMS] + [Claim(id="C4", text="A new point of the planner.", category="INFERRED")]
    p.save_claims(ClaimTable(section_id="discussion", approved=True, claims=again))
    capsys.readouterr()
    assert main(["--root", str(project), "evidence", "apply", "discussion"]) == 0
    assert "New claims in the claim table: C6, C7" in capsys.readouterr().out      # an id is never used twice
    table = orchestrator.Project(project).load_claims("discussion")
    assert table.claims[3].text == "A new point of the planner." and table.claims[3].cite_keys == []    # left alone
    assert [(c.id, c.origin, c.cite_keys) for c in table.claims[4:]] == [
        ("C6", "evidence search", ["smith2020sleep"]), ("C7", "evidence search", ["smith2020sleep"])]
    assert table.approved is False

    # planned again with C1 reworded: what was accepted for the old C1 is not carried into the new table
    changed = [Claim(id="C1", text="Short sleep went with worse attention.", category="OBSERVED", fact_ids=["F1"])] + \
              [c.model_copy() for c in CLAIMS[1:]]
    p.save_claims(ClaimTable(section_id="discussion", approved=True, claims=changed))
    assert main(["--root", str(project), "evidence", "apply", "discussion"]) == 0
    out = capsys.readouterr().out
    assert "2 accepted suggestion(s) belong to claims that are no longer in the claim table" in out
    assert "paperkit evidence search discussion" in out and "New claims" not in out
    assert [c.id for c in orchestrator.Project(project).load_claims("discussion").claims] == ["C1", "C2", "C3"]

    evidence.search(project, "discussion")                            # searched again: old decisions do not move to the new C1
    rows = {f["claim_id"]: f["papers"] + f["alternatives"] for f in stored(project)["findings"]}
    assert all(row["decision"] == "" for row in rows["C1"])


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
        waits = []
        papers = scholar.search('"sleep-duration" AND memory', 7, tmp_path / "cache", notify=waits.append)
        assert waits == ["Semantic Scholar says wait (HTTP 429): trying again in 0 s, try 2 of 3"]
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
