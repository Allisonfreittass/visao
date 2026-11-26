"""`visao iniciar | parar | estado` (apps/visao_cli.py): what it keeps in ~/.visao and how it
answers when nothing is running."""

import os

import apps.visao_cli as cli


def test_state_is_kept_and_a_stale_one_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.setenv("VISAO_HOME", str(tmp_path))
    cli.write_state(os.getpid(), 8123)
    assert cli.running() == {**cli.read_state(), "pid": os.getpid(), "port": 8123}
    # A process that no longer exists: the state goes.
    cli.write_state(2**22 + 12345, 8123)
    assert cli.running() is None
    assert not cli.state_file().exists()


def test_clearing_only_removes_its_own_state(tmp_path, monkeypatch):
    monkeypatch.setenv("VISAO_HOME", str(tmp_path))
    cli.write_state(111, 8000)
    cli.clear_state(222)  # a newer start replaced it: leave it
    assert cli.read_state()["pid"] == 111
    cli.clear_state(111)
    assert cli.read_state() is None


def test_with_nothing_running_stop_and_status_say_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VISAO_HOME", str(tmp_path))
    assert cli.main(["parar"]) == 0
    assert cli.main(["estado"]) == 1
    out = capsys.readouterr().out
    assert "não está rodando" in out and "Parado." in out


def test_starting_without_the_web_build_says_how_to_make_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VISAO_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "WEB_DIR", tmp_path / "sem-build")
    assert cli.main(["iniciar"]) == 1
    assert "npm --prefix apps/web run build" in capsys.readouterr().err


def test_the_database_label_never_shows_the_password():
    assert cli._database_label("postgresql+psycopg://visao:segredo@db.exemplo.com:5432/visao") == (
        "db.exemplo.com:5432/visao"
    )
    assert cli._database_label("sqlite:///./dev.db") == "./dev.db"


def test_a_config_of_its_own_with_a_new_key_and_the_database_outside_the_code(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("VISION_SECRET_KEY=\nVISION_DATABASE_URL=sqlite:///./dev.db\nOUTRA=1\n")
    target = tmp_path / "home" / ".env"
    cli.criar_config(example, target, tmp_path / "home" / "dados" / "visao.db")
    lines = target.read_text().splitlines()
    assert len(lines[0]) > len("VISION_SECRET_KEY=") + 40
    assert lines[1] == f"VISION_DATABASE_URL=sqlite:///{tmp_path}/home/dados/visao.db"
    assert lines[2] == "OUTRA=1"
    assert target.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "home" / "dados").is_dir()


def test_frozen_in_the_app_it_keeps_the_config_in_its_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VISAO_HOME", str(tmp_path / ".visao"))
    environ: dict[str, str] = {}
    cli._frozen_config(environ)
    assert environ["VISION_ENV_FILE"] == str(tmp_path / ".visao" / ".env")
    written = (tmp_path / ".visao" / ".env").read_text()
    assert f"sqlite:///{tmp_path}/.visao/dados/visao.db" in written
    cli._frozen_config(environ)  # the second start keeps it
    assert (tmp_path / ".visao" / ".env").read_text() == written


def test_it_runs_itself_again_with_or_without_python(monkeypatch):
    assert cli.self_command()[1:] == ["-m", "apps.visao_cli"]
    monkeypatch.setattr(cli, "FROZEN", True)
    assert cli.self_command() == [cli.sys.executable]


def test_the_apps_server_stops_when_its_parent_is_gone(monkeypatch):
    import signal

    from apps import visao_cli

    parents = iter([4242, 4242, 1])
    killed = []
    monkeypatch.setattr(visao_cli.os, "getppid", lambda: next(parents, 1))
    monkeypatch.setattr(visao_cli.os, "kill", lambda pid, sig: killed.append(sig))
    monkeypatch.setattr(visao_cli.time, "sleep", lambda s: None)
    import time as real_time

    visao_cli.watch_parent(every=0)

    deadline = real_time.monotonic() + 2
    while not killed and real_time.monotonic() < deadline:
        real_time.sleep(0.01)
    assert killed == [signal.SIGTERM]


def test_a_server_without_a_parent_is_not_watched(monkeypatch):
    from apps import visao_cli

    started = []
    monkeypatch.setattr(visao_cli.os, "getppid", lambda: 1)
    monkeypatch.setattr("threading.Thread.start", lambda self: started.append(self))
    visao_cli.watch_parent()
    assert started == []
