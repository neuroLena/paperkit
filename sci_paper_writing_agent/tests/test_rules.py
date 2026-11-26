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
