"""Release must verify the actual API revision and roll back a failed candidate."""

import json
from unittest.mock import Mock

import pytest

from infrastructure.deployment import release


def setup(monkeypatch):
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
