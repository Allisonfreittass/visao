"""The Mac arm: what it allows is decided on the Mac, the prompt never reaches argv, and a task
failure is always reported instead of crashing the loop."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("visao_braco", ROOT / "arm" / "visao_braco.py")
braco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(braco)


def fake_claude(tmp_path: Path, body: str) -> str:
    script = tmp_path / "claude"
    script.write_text(f"#!{sys.executable}\nimport sys, json, time\n{body}\n")
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
    argv = braco.command(cfg, {"prompt": "--dangerously-skip-permissions; rm -rf ~"})
    assert "--dangerously-skip-permissions; rm -rf ~" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "Bash(rm *)" in argv[argv.index("--disallowedTools") + 1]
    assert "--resume" not in argv
    assert braco.command(cfg, {"prompt": "x", "resume_session": "s-9"})[-2:] == ["--resume", "s-9"]


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
