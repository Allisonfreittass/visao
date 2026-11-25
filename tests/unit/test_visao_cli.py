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
