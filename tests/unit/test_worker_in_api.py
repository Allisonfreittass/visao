"""The worker as a thread of the API (docs/research/execucao_local.md, etapa 2)."""

import threading

from fastapi.testclient import TestClient

import apps.api.main as api_main
import apps.worker.main as worker_main
from apps.api.settings import Settings


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_the_loop_stops_when_asked_and_survives_a_failed_iteration(monkeypatch):
    stop = threading.Event()
    calls = []

    def run_once(_factory, _handlers, _worker_id):
        calls.append("run")
        if len(calls) == 1:
            raise RuntimeError("database away for a moment")
        stop.set()
        return "idle"

    monkeypatch.setattr(worker_main, "get_sessionmaker", lambda: _FakeSession)
    monkeypatch.setattr(worker_main, "build_handlers", lambda _settings: {})
    monkeypatch.setattr(worker_main, "schedule", lambda *_args: None)
    monkeypatch.setattr(worker_main, "run_once", run_once)
    monkeypatch.setattr(worker_main, "IDLE_SLEEP_SECONDS", 0.01)
    beats = []
    monkeypatch.setattr(worker_main, "beat", lambda: beats.append(1))

    worker_main.serve(stop, Settings())

    assert calls == ["run", "run"]  # the failure did not end the loop
    assert beats == [1]  # only the iteration that worked moved the heartbeat


def test_the_api_starts_the_worker_and_stops_it_on_shutdown(monkeypatch):
    started, stopped = threading.Event(), threading.Event()

    def serve(stop, _settings):
        started.set()
        stop.wait(5)
        stopped.set()

    monkeypatch.setattr(worker_main, "serve", serve)
    monkeypatch.setattr(api_main, "get_settings", lambda: Settings(worker_in_api=True))
    app = api_main.create_app()
    with TestClient(app):
        assert started.wait(2)
        assert app.state.worker_thread.name == "visao-worker"
        assert app.state.worker_thread.is_alive()
    assert stopped.is_set()
    assert not app.state.worker_thread.is_alive()


def test_without_the_option_the_api_runs_alone(monkeypatch):
    monkeypatch.setattr(api_main, "get_settings", lambda: Settings(worker_in_api=False))
    app = api_main.create_app()
    with TestClient(app):
        assert app.state.worker_thread is None
