"""The Mac arm: what it allows is decided on the Mac, the prompt never reaches argv, a task
cannot widen what the next ones may do, a task failure is always reported instead of crashing
the loop, and a result waits on the Mac until the server takes it."""

import importlib.util
import json
import sys
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("visao_braco", ROOT / "arm" / "visao_braco.py")
braco = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = braco  # dataclasses resolve postponed annotations through it
spec.loader.exec_module(braco)


# The parts of `claude --help` the arm looks for, as Claude Code 2.1 prints them.
RESTRICTED_HELP = """Options:
  --restricted                          Restricted mode: removes the built-in
  --setting-sources <sources>           Comma-separated list of setting sources
  --strict-mcp-config                   Only use MCP servers from --mcp-config,
  --tools <tools...>                    Built-in tools to make available
"""
OLDER_HELP = """Options:
  --setting-sources <sources>           Comma-separated list of setting sources
  --strict-mcp-config                   Only use MCP servers from --mcp-config,
"""
ANCIENT_HELP = """Options:
  -p, --print                           Print response and exit
"""


@pytest.fixture(autouse=True)
def fresh_help():
    braco._help_text.clear()
    yield
    braco._help_text.clear()


def fake_claude(tmp_path: Path, body: str, help_text: str = RESTRICTED_HELP) -> str:
    script = tmp_path / "claude"
    script.write_text(
        f"#!{sys.executable}\nimport sys, json, time\n"
        f"if '--help' in sys.argv:\n    print({help_text!r})\n    sys.exit(0)\n{body}\n"
    )
    script.chmod(0o755)
    return str(script)


def config(tmp_path: Path, claude: str = "claude", **extra) -> "braco.Config":
    project = tmp_path / "visao"
    project.mkdir(exist_ok=True)
    return braco.Config(
        server="https://visao.example",
        token="visao-arm_x",
        projects={"visao": project},
        claude=claude,
        state_dir=tmp_path / "estado",
        **extra,
    )


def test_config_needs_server_token_and_projects(tmp_path):
    path = tmp_path / "braco.json"
    path.write_text(json.dumps({"server": "https://s/", "token": "t", "projects": {}}))
    with pytest.raises(ValueError, match="projeto"):
        braco.Config.load(path)
    path.write_text(json.dumps({"server": "https://s/", "token": "t", "projects": {"a": "~"}}))
    loaded = braco.Config.load(path)
    assert loaded.server == "https://s" and loaded.projects["a"] == Path.home().resolve()
    assert "Bash(git push *)" not in loaded.allowed_tools


def test_the_prompt_goes_on_stdin_and_nothing_is_ever_skipped(tmp_path):
    cfg = config(tmp_path)
    argv = braco.command(cfg, {"prompt": "--dangerously-skip-permissions; rm -rf ~"}, [])
    assert "--dangerously-skip-permissions; rm -rf ~" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Bash(rm *)" in argv[argv.index("--disallowedTools") + 1]
    assert "--resume" not in argv
    resumed = braco.command(cfg, {"prompt": "x", "resume_session": "s-9"}, [])
    assert resumed[-2:] == ["--resume", "s-9"]


def test_a_task_can_never_change_what_governs_the_next_ones(tmp_path):
    # F5: with Edit and Write allowed, a task could write .claude/settings.json (allow rules,
    # hooks), .mcp.json, CLAUDE.md or .git/hooks, and every later task would obey it.
    cfg = config(tmp_path, allowed_tools=[*braco.DEFAULT_TOOLS, "Edit(.claude/**)"])
    denied = braco.command(cfg, {"prompt": "x"}, [])
    denied = denied[denied.index("--disallowedTools") + 1].split(",")
    for path in (".claude/**", ".mcp.json", "**/CLAUDE.md", ".git/**"):
        assert f"Edit({path})" in denied and f"Write({path})" in denied


def test_claude_code_runs_isolated_or_not_at_all(tmp_path):
    tools = "Bash,Edit,Glob,Grep,Read,Write"
    cfg = config(tmp_path, fake_claude(tmp_path, "", RESTRICTED_HELP))
    assert braco.isolation(cfg) == ["--restricted", "--strict-mcp-config", "--tools", tools]

    braco._help_text.clear()
    cfg = config(tmp_path, fake_claude(tmp_path, "", OLDER_HELP))
    flags = braco.isolation(cfg)
    assert flags[:2] == ["--setting-sources", "user"] and "--strict-mcp-config" in flags
    assert json.loads(flags[flags.index("--settings") + 1]) == {"disableAllHooks": True}

    braco._help_text.clear()
    ran = tmp_path / "ran"
    cfg = config(tmp_path, fake_claude(tmp_path, f"open({str(ran)!r}, 'w')", ANCIENT_HELP))
    assert braco.isolation(cfg) is None
    refused = braco.handle(cfg, {"project": "visao", "prompt": "x"})
    assert refused["ok"] is False and "claude update" in refused["error"]
    assert not ran.exists()  # nothing ran


def test_the_flags_go_to_claude_code(tmp_path):
    claude = fake_claude(tmp_path, 'print(json.dumps({"result": " ".join(sys.argv[1:])}))')
    result = braco.handle(config(tmp_path, claude), {"project": "visao", "prompt": "x"})
    assert "--restricted --strict-mcp-config --tools" in result["result"]


def test_only_projects_listed_on_the_mac_run(tmp_path):
    cfg = config(tmp_path)
    refused = braco.handle(cfg, {"project": "../../etc", "prompt": "x"})
    assert refused["ok"] is False and "visao" in refused["error"]


def test_a_successful_run_reports_result_cost_and_session(tmp_path):
    claude = fake_claude(
        tmp_path,
        "prompt = sys.stdin.read()\n"
        'print(json.dumps({"result": "fiz: " + prompt, "total_cost_usd": 0.02, '
        '"session_id": "s-1", "is_error": False}))',
    )
    result = braco.handle(
        config(tmp_path, claude), {"project": "visao", "prompt": "rode os testes"}
    )
    assert result == {
        "ok": True,
        "result": "fiz: rode os testes",
        "session_id": "s-1",
        "cost_usd": 0.02,
    }


def test_errors_and_timeouts_are_reported_not_raised(tmp_path):
    crashing = fake_claude(tmp_path, 'sys.stderr.write("boom"); sys.exit(3)')
    result = braco.handle(config(tmp_path, crashing), {"project": "visao", "prompt": "x"})
    assert result["ok"] is False and "boom" in result["error"]

    slow = fake_claude(tmp_path, "time.sleep(30)")
    cfg = config(tmp_path, slow, timeout_minutes=0.02)
    result = braco.handle(cfg, {"project": "visao", "prompt": "x"})
    assert result["ok"] is False and "interrompi" in result["error"]

    missing = config(tmp_path, str(tmp_path / "nao-existe"))
    assert "Não achei" in braco.handle(missing, {"project": "visao", "prompt": "x"})["error"]


def test_the_api_key_is_only_passed_on_purpose(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert "ANTHROPIC_API_KEY" not in braco._environment(config(tmp_path))
    assert braco._environment(config(tmp_path, use_api_key=True))["ANTHROPIC_API_KEY"] == "sk-test"


def test_one_round_of_the_loop_takes_runs_and_reports(tmp_path, monkeypatch):
    calls = []

    def fake_call(cfg, method, path, body=None, timeout=40):
        calls.append((method, path, body))
        if path.startswith("/device/next"):
            return {"id": "t-1", "project": "visao", "prompt": "oi", "resume_session": None}
        return None

    monkeypatch.setattr(braco, "call", fake_call)
    monkeypatch.setattr(braco, "handle", lambda cfg, task: {"ok": True, "result": "feito"})
    braco.loop(config(tmp_path), once=True)
    assert [c[1] for c in calls] == [
        "/device/heartbeat",
        f"/device/next?wait={braco.LONG_POLL_SECONDS}",
        "/device/tasks/t-1/result",
    ]
    assert calls[-1][2] == {"ok": True, "result": "feito"}


def _config_file(tmp_path: Path, local: dict) -> Path:
    path = tmp_path / "braco.json"
    path.write_text(
        json.dumps(
            {
                "server": "https://visao.example",
                "token": "visao-arm_x",
                "projects": {"visao": str(tmp_path)},
                "modelo_local": local,
            }
        )
    )
    return path


def test_the_local_model_only_talks_to_a_model_on_this_mac(tmp_path):
    loaded = braco.Config.load(_config_file(tmp_path, {"modelo": "qwen3:4b"}))
    assert loaded.local_model == "qwen3:4b" and loaded.ollama == "http://127.0.0.1:11434"
    # The questions carry the owner's conversations: never to another machine.
    with pytest.raises(ValueError, match="deste Mac"):
        braco.Config.load(
            _config_file(tmp_path, {"modelo": "qwen3:4b", "endereco": "http://192.168.0.9:11434"})
        )
    assert braco.Config.load(_config_file(tmp_path, {})).local_model is None


class _Answer:
    def __init__(self, body: dict) -> None:
        self._raw = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_a_question_goes_to_ollama_with_thinking_off_and_comes_back_as_text(tmp_path, monkeypatch):
    sent = {}

    def fake_open(request, timeout):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)
        return _Answer({"message": {"content": " Olá. "}, "prompt_eval_count": 9, "eval_count": 2})

    monkeypatch.setattr(braco.urllib.request, "urlopen", fake_open)
    cfg = config(tmp_path, local_model="qwen3:4b")
    answer = braco.ask_local_model(
        cfg, {"messages": [{"role": "user", "content": "oi"}], "max_output_tokens": 50}
    )
    assert answer == {"ok": True, "text": "Olá.", "input_tokens": 9, "output_tokens": 2}
    assert sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert sent["body"]["think"] is False and sent["body"]["options"]["num_predict"] == 50


def test_ollama_closed_is_reported_not_raised(tmp_path, monkeypatch):
    def refuse(request, timeout):
        raise braco.urllib.error.URLError("connection refused")

    monkeypatch.setattr(braco.urllib.request, "urlopen", refuse)
    answer = braco.ask_local_model(config(tmp_path, local_model="qwen3:4b"), {"messages": []})
    assert answer["ok"] is False and "Ollama" in answer["error"]


def test_one_round_of_the_local_line_answers_and_reports(tmp_path, monkeypatch):
    calls = []

    def fake_call(cfg, method, path, body=None, timeout=40):
        calls.append((method, path, body))
        if path.startswith("/device/llm/next"):
            return {"id": "q-1", "model": "qwen3:4b", "messages": [], "max_output_tokens": 10}
        return None

    monkeypatch.setattr(braco, "call", fake_call)
    monkeypatch.setattr(braco, "ask_local_model", lambda cfg, q: {"ok": True, "text": "oi"})
    braco.local_loop(config(tmp_path, local_model="qwen3:4b"), once=True)
    assert calls[0][1] == f"/device/llm/next?wait={braco.LONG_POLL_SECONDS}&model=qwen3%3A4b"
    assert calls[1] == ("POST", "/device/llm/q-1/result", {"ok": True, "text": "oi"})


# F4: the result is never lost --------------------------------------------------------------


def _server(calls, *, task=None, fail_results=0):
    """A fake server: hands out `task` once, and refuses the first `fail_results` results as if
    the network dropped."""
    state = {"task": task, "fail": fail_results}

    def fake_call(cfg, method, path, body=None, timeout=40):
        calls.append((method, path, body))
        if path.startswith("/device/next"):
            given, state["task"] = state["task"], None
            return given
        if path.endswith("/result") and state["fail"]:
            state["fail"] -= 1
            raise urllib.error.URLError("rede caiu")
        return None

    return fake_call


def _results(calls):
    return [(c[1], c[2]) for c in calls if c[1].endswith("/result")]


def test_a_result_the_network_dropped_is_sent_on_the_next_round(tmp_path, monkeypatch):
    calls = []
    task = {"id": "t-1", "project": "visao", "prompt": "oi"}
    monkeypatch.setattr(braco, "call", _server(calls, task=task, fail_results=1))
    monkeypatch.setattr(braco, "handle", lambda cfg, t: {"ok": True, "result": "feito"})
    monkeypatch.setattr(braco.time, "sleep", lambda s: None)
    cfg = config(tmp_path)

    braco.loop(cfg, once=True)  # ran it; sending failed
    assert len(list((cfg.state_dir / "saida").glob("*.json"))) == 1
    braco.loop(cfg, once=True)  # next round: sent before anything else
    sent = _results(calls)
    assert sent == [("/device/tasks/t-1/result", {"ok": True, "result": "feito"})] * 2
    assert list((cfg.state_dir / "saida").glob("*.json")) == []
    assert calls[-3][1] == "/device/tasks/t-1/result"  # before the heartbeat and the next poll


def test_a_task_cut_off_by_a_restart_is_reported_never_run_again(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(braco, "call", _server(calls))
    ran = []
    monkeypatch.setattr(braco, "handle", lambda cfg, t: ran.append(t))
    cfg = config(tmp_path)
    braco._write(braco._running_file(cfg), {"task_id": "t-7"})  # the Mac died mid-task

    braco.loop(cfg, once=True)
    [(path, body)] = _results(calls)
    assert path == "/device/tasks/t-7/result" and body["ok"] is False
    assert "reiniciou no meio" in body["error"] and ran == []
    assert not braco._running_file(cfg).exists()


def test_a_result_the_server_refuses_for_good_is_dropped(tmp_path, monkeypatch):
    calls = []

    def refusing(cfg, method, path, body=None, timeout=40):
        calls.append(path)
        if path.endswith("/result"):
            raise urllib.error.HTTPError(path, 404, "não é deste aparelho", None, None)

    monkeypatch.setattr(braco, "call", refusing)
    cfg = config(tmp_path)
    braco.keep(cfg, "t-9", {"ok": True, "result": "x"})
    braco.deliver(cfg)
    assert list((cfg.state_dir / "saida").glob("*.json")) == []


def test_it_beats_while_a_long_task_runs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(braco, "call", _server(calls, task={"id": "t-3", "project": "visao"}))
    monkeypatch.setattr(braco, "HEARTBEAT_SECONDS", 0.02)

    def slow(cfg, task):
        time.sleep(0.2)
        return {"ok": True, "result": "ok"}

    monkeypatch.setattr(braco, "handle", slow)
    braco.loop(config(tmp_path), once=True)
    beats = [c[2]["running"] for c in calls if c[1] == "/device/heartbeat"]
    assert beats[0] is None and "t-3" in beats[1:]
