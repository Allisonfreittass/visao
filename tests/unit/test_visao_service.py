"""`visao servico instalar | remover` (apps/visao_servico.py, etapa 5): the file it writes for the
system, the commands it gives the service manager, and how `iniciar` and `parar` defer to it."""

import plistlib
import sys

import pytest

import apps.visao_cli as cli
from apps import visao_servico as servico


@pytest.fixture
def system(tmp_path, monkeypatch):
    """A home of its own and a service manager that only writes down what it was asked."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VISAO_HOME", str(tmp_path / ".visao"))
    monkeypatch.delenv("VISAO_SERVICO_NOME", raising=False)
    monkeypatch.delenv("VISAO_SERVICO", raising=False)
    calls: list[list[str]] = []
    codes: dict[str, int] = {}

    def run(command: list[str]) -> int:
        calls.append(command)
        return codes.get(command[1] if command[0] == "launchctl" else command[2], 0)

    monkeypatch.setattr(servico, "run", run)

    def use(name: str):
        monkeypatch.setattr(servico.platform, "system", lambda: name)
        return calls, codes

    return use


def test_the_mac_gets_a_launch_agent_that_starts_at_login_and_comes_back(system, tmp_path):
    calls, _ = system("Darwin")
    assert cli.main(["servico", "instalar", "--porta", "8123"]) == 0
    target = tmp_path / "Library" / "LaunchAgents" / "digital.visao.app.plist"
    plist = plistlib.loads(target.read_bytes())
    assert plist["Label"] == "digital.visao.app"
    assert plist["ProgramArguments"] == [
        sys.executable,
        "-m",
        "apps.visao_cli",
        "iniciar",
        "--porta",
        "8123",
    ]
    assert plist["WorkingDirectory"] == str(cli.ROOT)
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] is True
    assert plist["EnvironmentVariables"]["VISAO_SERVICO"] == "1"
    assert plist["StandardOutPath"] == str(tmp_path / ".visao" / "visao.log")
    uid = f"gui/{servico.os.getuid()}"
    assert calls == [
        ["launchctl", "bootout", f"{uid}/digital.visao.app"],
        ["launchctl", "bootstrap", uid, str(target)],
    ]


def test_linux_gets_a_systemd_user_unit(system, tmp_path, capsys):
    calls, _ = system("Linux")
    assert cli.main(["servico", "instalar"]) == 0
    unit = (tmp_path / ".config" / "systemd" / "user" / "visao.service").read_text()
    assert f"ExecStart={sys.executable} -m apps.visao_cli iniciar --porta 8000" in unit
    assert f"WorkingDirectory={cli.ROOT}" in unit
    assert "Environment=VISAO_SERVICO=1" in unit
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "visao.service"],
        ["systemctl", "--user", "restart", "visao.service"],
    ]
    assert "enable-linger" in capsys.readouterr().out


def test_a_service_that_does_not_come_up_is_reported(system, capsys):
    _, codes = system("Linux")
    codes["enable"] = 1
    assert cli.main(["servico", "instalar"]) == 1
    assert "não ligou" in capsys.readouterr().err


def test_removing_turns_it_off_and_deletes_the_file(system):
    calls, _ = system("Linux")
    cli.main(["servico", "instalar"])
    calls.clear()
    assert cli.main(["servico", "remover"]) == 0
    assert not servico.installed()
    assert calls == [
        ["systemctl", "--user", "disable", "--now", "visao.service"],
        ["systemctl", "--user", "daemon-reload"],
    ]
    assert cli.main(["servico", "remover"]) == 0  # nothing left: says so, no error


def test_another_name_for_a_second_install(system, tmp_path, monkeypatch):
    system("Linux")
    monkeypatch.setenv("VISAO_SERVICO_NOME", "visao-teste")
    cli.main(["servico", "instalar"])
    assert (tmp_path / ".config" / "systemd" / "user" / "visao-teste.service").is_file()


def test_on_the_mac_starting_an_agent_already_loaded_kicks_it(system):
    calls, codes = system("Darwin")
    codes["bootstrap"] = 5  # launchd: already loaded
    assert servico.start() == 0
    assert calls[-1][:2] == ["launchctl", "kickstart"]


def test_with_the_service_installed_start_hands_it_to_the_system(system, monkeypatch, tmp_path):
    calls, _ = system("Linux")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html>")
    monkeypatch.setattr(cli, "WEB_DIR", tmp_path / "web")
    cli.main(["servico", "instalar"])
    calls.clear()
    waited = []
    monkeypatch.setattr(cli, "_wait_up", lambda port, died, how: waited.append(how) or 0)
    assert cli.main(["iniciar"]) == 0
    assert calls == [["systemctl", "--user", "start", "visao.service"]]
    assert waited == ["pelo serviço"]


def test_with_the_service_installed_stop_asks_the_system_not_a_signal(system, monkeypatch):
    calls, _ = system("Linux")
    cli.main(["servico", "instalar"])
    calls.clear()
    cli.write_state(4242, 8000)
    alive = iter([True, False, False])
    monkeypatch.setattr(cli, "alive", lambda pid: next(alive, False))
    monkeypatch.setattr(cli.os, "kill", lambda *a: pytest.fail("a SIGTERM would be restarted"))
    assert cli.main(["parar"]) == 0
    assert calls == [["systemctl", "--user", "stop", "visao.service"]]


def test_status_says_whether_the_service_is_there(system, capsys):
    system("Linux")
    cli.main(["estado"])
    assert "Serviço: não instalado (systemd)" in capsys.readouterr().out
    cli.main(["servico", "instalar"])
    capsys.readouterr()
    cli.main(["estado"])
    assert "Serviço: instalado (systemd)" in capsys.readouterr().out
