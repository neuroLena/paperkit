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
