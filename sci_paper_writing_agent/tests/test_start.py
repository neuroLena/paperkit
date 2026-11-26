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


def test_a_line_added_to_env_while_the_menu_is_open_counts_for_the_next_step(fresh, monkeypatch):
    monkeypatch.setattr(env, "_FROM_FILE", {})
    for name in ("SEMANTIC_SCHOLAR_API_KEY", "PAPERKIT_MAX_TOKENS", "NVIDIA_API_KEY"):
        monkeypatch.setenv(name, "")
    env_file = fresh.parent / ".env"
    env_file.write_text("PAPERKIT_MAX_TOKENS=8000\n", encoding="utf-8")
    assert env.load_env(fresh) == ["PAPERKIT_MAX_TOKENS"]                 # what paperkit reads when it starts

    seen = []
    monkeypatch.setitem(wizard.ACTIONS, "8", lambda ui, root: seen.append(
        (os.environ.get("SEMANTIC_SCHOLAR_API_KEY"), os.environ.get("PAPERKIT_MAX_TOKENS"), os.environ.get("NVIDIA_API_KEY"))))
    monkeypatch.setenv("NVIDIA_API_KEY", "from-the-shell")
    answers = iter(["8", "8", "q"])

    def ask(prompt=""):
        if not seen:                                                      # you edit .env with the menu still open
            env_file.write_text("PAPERKIT_MAX_TOKENS=16000\nSEMANTIC_SCHOLAR_API_KEY=s2-key\nNVIDIA_API_KEY=from-the-file\n",
                                encoding="utf-8")
        return next(answers)

    assert wizard.menu(wizard.UI(ask=ask, out=lambda text="": None, color=False), fresh) == 0
    assert seen == [("s2-key", "16000", "from-the-shell")] * 2            # new line and changed value seen; the shell still wins


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

