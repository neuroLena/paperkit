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
