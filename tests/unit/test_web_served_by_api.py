"""The web app served by the API itself, with /api for the API (apps/api/web.py)."""

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.settings import Settings


@pytest.fixture
def site(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>VISAO</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "manifest.webmanifest").write_text("{}")
    (tmp_path / "segredo.txt").write_text("fora do build")
    monkeypatch.setattr(api_main, "get_settings", lambda: Settings(web_dir=str(dist)))
    return TestClient(api_main.create_app())


def test_the_site_and_the_api_share_one_address(site):
    page = site.get("/", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "VISAO" in page.text
    assert page.headers["cache-control"] == "no-cache"
    asset = site.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert site.get("/manifest.webmanifest").status_code == 200
    assert site.get("/api/health").json() == {"status": "ok"}
    assert site.get("/health").json() == {"status": "ok"}  # the arm and the tests still use these


def test_a_screen_reloaded_gets_the_app_but_the_api_keeps_its_404(site):
    screen = site.get("/rotinas", headers={"Accept": "text/html"})
    assert screen.status_code == 200 and "VISAO" in screen.text
    missing = site.get("/api/nao-existe", headers={"Accept": "application/json"})
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}
    assert site.get("/assets/nao-existe.js").status_code == 404


def test_other_methods_go_through_the_prefix_to_the_api(site):
    # /health only answers GET: a POST through /api reaches the API's route and is refused there.
    assert site.post("/api/health").status_code == 405


def test_nothing_outside_the_build_is_served(site):
    for path in ("/../segredo.txt", "/%2e%2e/segredo.txt", "/assets/../../segredo.txt"):
        reply = site.get(path)
        assert "fora do build" not in reply.text


def test_without_the_build_it_says_how_to_make_it(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "get_settings", lambda: Settings(web_dir=str(tmp_path)))
    with pytest.raises(FileNotFoundError, match="npm --prefix apps/web run build"):
        api_main.create_app()
