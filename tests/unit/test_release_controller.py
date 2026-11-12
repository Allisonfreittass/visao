"""Release must verify the actual API revision and roll back a failed candidate."""

import json
from unittest.mock import Mock

import pytest

from infrastructure.deployment import release


def setup(monkeypatch):
    monkeypatch.setenv("VISAO_DEPLOY_TARGET", "cloudflare")
    monkeypatch.setattr(release, "git", lambda *args: "a" * 40)
    monkeypatch.setattr(release, "current_main", lambda: "a" * 40)
    monkeypatch.setattr(release, "code_id_at_head", lambda: None)
    monkeypatch.setattr(release, "request_json", lambda path: {"revision": "old"})
    calls = []

    def cli(*args, capture=False):
        calls.append(args)
        return (
            json.dumps(
                [
                    {
                        "created_on": "2026-10-31",
                        "versions": [{"version_id": "old-worker", "percentage": 100}],
                    }
                ]
            )
            if capture
            else None
        )

    monkeypatch.setattr(release, "wrangler", cli)
    return calls


def test_success_verifies_the_deployed_sha(monkeypatch):
    calls = setup(monkeypatch)
    health = Mock(return_value=True)
    monkeypatch.setattr(release, "wait_healthy", health)
    release.main()
    assert (
        "deploy",
        "--var",
        "VISION_BUILD_SHA:" + "a" * 40,
        "--durable-objects-code-update-mode",
        "deferred 30s",
    ) in calls
    health.assert_called_once_with("a" * 40)
    assert not any(c[0] == "rollback" for c in calls)


def test_failed_revision_is_rolled_back_and_verified(monkeypatch):
    calls = setup(monkeypatch)
    health = Mock(side_effect=[False, True])
    monkeypatch.setattr(release, "wait_healthy", health)
    with pytest.raises(RuntimeError, match="Previous version restored"):
        release.main()
    assert any(c[:2] == ("rollback", "old-worker") for c in calls)
    assert health.call_args_list[-1].args == ("old",)


def test_stale_ci_cannot_publish_over_new_main(monkeypatch):
    calls = setup(monkeypatch)
    monkeypatch.setattr(release, "current_main", lambda: "b" * 40)
    release.main()
    assert calls == []


def test_controller_identifies_itself_to_the_public_api(monkeypatch):
    from io import BytesIO

    seen = []

    def open_request(request, **kwargs):
        seen.append(request)
        return BytesIO(b'{"revision":"test"}')

    monkeypatch.setattr(release.urllib.request, "urlopen", open_request)
    assert release.request_json("/api/release") == {"revision": "test"}
    assert seen[0].get_header("User-agent") == "visao-release-controller/1.0"


def lightsail(monkeypatch, running="b" * 40):
    monkeypatch.setenv("VISAO_DEPLOY_TARGET", "lightsail")
    monkeypatch.setattr(release, "git", lambda *args: "a" * 40)
    monkeypatch.setattr(release, "current_main", lambda: "a" * 40)
    monkeypatch.setattr(release, "code_id_at_head", lambda: None)

    def running_revision(path):
        if running is None:
            raise OSError("server not answering yet")
        return {"revision": running}

    monkeypatch.setattr(release, "request_json", running_revision)
    commands, uploads = [], []
    monkeypatch.setattr(release, "remote", lambda *cmd: commands.append(cmd))
    monkeypatch.setattr(release, "upload", lambda *paths: uploads.append(paths))
    return commands, uploads


def test_lightsail_ships_image_web_and_deploy_files_then_activates(monkeypatch):
    commands, uploads = lightsail(monkeypatch)
    monkeypatch.setattr(release, "wait_healthy", Mock(return_value=True))
    release.main()
    names = [path.name for path in uploads[0]]
    sha = "a" * 40
    assert names[:2] == [f"visao-{sha}.tar.gz", f"web-{sha}.tar.gz"]
    assert {"docker-compose.yml", "Caddyfile", "activate.sh"} <= set(names)
    assert commands == [(f"sh /opt/visao/incoming/activate.sh {sha}",)]


def test_lightsail_rolls_back_to_the_release_that_was_running(monkeypatch):
    commands, _ = lightsail(monkeypatch)
    health = Mock(side_effect=[False, True])
    monkeypatch.setattr(release, "wait_healthy", health)
    with pytest.raises(RuntimeError, match="Previous version restored"):
        release.main()
    assert commands[-1] == ("sh /opt/visao/activate.sh " + "b" * 40,)
    assert health.call_args_list[-1].args == ("b" * 40,)


def test_a_failed_first_release_has_nothing_to_restore(monkeypatch):
    commands, _ = lightsail(monkeypatch, running=None)
    monkeypatch.setattr(release, "wait_healthy", Mock(return_value=False))
    with pytest.raises(RuntimeError, match="nothing to restore"):
        release.main()
    assert len(commands) == 1  # activated once, never "rolled back" to nothing


def test_health_requires_the_app_shell_not_any_200(monkeypatch):
    from io import BytesIO

    class Page(BytesIO):
        status = 200

    pages = {
        "/api/release": b'{"revision": "x"}',
        "/api/ready": b'{"status": "ok", "database": "up"}',
    }

    def open_request(request, **kwargs):
        path = request.full_url.removeprefix(release.URL)
        return Page(pages.get(path, b"<html>proxy error</html>"))

    monkeypatch.setattr(release.urllib.request, "urlopen", open_request)
    assert release.healthy("x") is False
    pages["/"] = b'<div id="root"></div>'
    assert release.healthy("x") is True
