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
