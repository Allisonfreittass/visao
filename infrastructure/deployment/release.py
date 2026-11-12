"""Deploy the CI-tested main SHA, verify its running API, and roll back on failure.

Two targets, chosen by `VISAO_DEPLOY_TARGET`:

- `lightsail` (default): a Docker image and the web build go to the server over SSH;
  `deploy/activate.sh` switches the running release. Every release stays on the server under
  its SHA, so rolling back is activating the previous one again.
- `cloudflare`: Workers + Containers through wrangler (docs/CLOUDFLARE.md).

Either way the candidate counts as published only when the public URL reports its revision,
the database answers and the page loads; otherwise the previous release comes back.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from infrastructure.evolution.runner import (  # noqa: E402
    PUBLIC_URL,
    api,
    code_id_at_head,
    git,
    push,
    report,
)

CLOUD = ROOT / "infrastructure" / "cloudflare"
URL = PUBLIC_URL
# Files the workflow prepares in ARTIFACTS for a Lightsail release (see .github/workflows/cd.yml).
ARTIFACTS = Path(os.environ.get("VISAO_RELEASE_DIR", ROOT / "release"))
REMOTE_DIR = "/opt/visao"
DEPLOY_FILES = ("docker-compose.yml", "Caddyfile", "activate.sh")


def wrangler(*args, capture=False):
    result = subprocess.run(  # noqa: S603
        ["npx", "wrangler", *args],  # noqa: S607
        cwd=CLOUD,
        text=True,
        check=True,
        capture_output=capture,
    )  # noqa: S603,S607
    return result.stdout if capture else None


def _ssh_base() -> list[str]:
    key = os.path.expanduser(os.environ.get("VPS_SSH_KEY_FILE", "~/.ssh/deploy"))
    return ["-i", key, "-o", "BatchMode=yes"]


def remote(*command: str) -> None:
    """Runs one command on the server as the deploy user (never with sudo)."""
    host = "deploy@" + os.environ["VPS_HOST"]
    subprocess.run(["ssh", *_ssh_base(), host, *command], check=True)  # noqa: S603,S607


def upload(*paths: Path) -> None:
    host = "deploy@" + os.environ["VPS_HOST"]
    subprocess.run(  # noqa: S603
        ["scp", *_ssh_base(), *map(str, paths), f"{host}:{REMOTE_DIR}/incoming/"],  # noqa: S607
        check=True,
    )


def public_request(path):
    if path not in {"/", "/api/release", "/api/ready"}:
        raise ValueError("unexpected_health_path")
    return urllib.request.Request(  # noqa: S310 (fixed public HTTPS service)
        URL + path, headers={"User-Agent": "visao-release-controller/1.0"}
    )


def request_json(path):
    with urllib.request.urlopen(public_request(path), timeout=30) as response:  # noqa: S310
        return json.load(response)


def current_main():
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/git/ref/heads/main",
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)["object"]["sha"]


def healthy(revision):
    try:
        if request_json("/api/release").get("revision") != revision:
            return False
        if request_json("/api/ready") != {"status": "ok", "database": "up"}:
            return False
        with urllib.request.urlopen(public_request("/"), timeout=20) as response:  # noqa: S310
            # The app shell, not a proxy error page that happens to answer 200.
            return response.status == 200 and 'id="root"' in response.read().decode()
    except Exception:
        return False


def wait_healthy(revision):
    for _ in range(30):
        if healthy(revision):
            return True
        time.sleep(5)
    return False


class Cloudflare:
    def previous(self):
        deployments = json.loads(wrangler("deployments", "list", "--json", capture=True))
        latest = max(deployments, key=lambda d: d["created_on"])
        if len(latest["versions"]) != 1 or latest["versions"][0]["percentage"] != 100:
            raise ValueError("Automatic release requires a single known previous version")
        return latest["versions"][0]["version_id"]

    def deploy(self, sha):
        wrangler(
            "deploy",
            "--var",
            f"VISION_BUILD_SHA:{sha}",
            "--durable-objects-code-update-mode",
            "deferred 30s",
        )

    def rollback(self, previous):
        wrangler(
            "rollback",
            previous,
            "--yes",
            "--message",
            "Automatic health rollback",
            "--durable-objects-code-update-mode",
            "immediate",
        )


class Lightsail:
    """The previous release is whatever the server reports running; its files stay there."""

    def previous(self):
        try:
            revision = request_json("/api/release").get("revision")
        except Exception:
            return None  # first release on this server: nothing to fall back to
        return revision if revision and revision != "local" else None

    def deploy(self, sha):
        image = ARTIFACTS / f"visao-{sha}.tar.gz"
        web = ARTIFACTS / f"web-{sha}.tar.gz"
        upload(image, web, *(ROOT / "deploy" / name for name in DEPLOY_FILES))
        remote(f"sh {REMOTE_DIR}/incoming/activate.sh {sha}")

    def rollback(self, previous):
        remote(f"sh {REMOTE_DIR}/activate.sh {previous}")


def target():
    name = os.environ.get("VISAO_DEPLOY_TARGET", "lightsail")
    if name == "cloudflare":
        return Cloudflare()
    if name == "lightsail":
        return Lightsail()
    raise ValueError(f"unknown deploy target: {name}")


def main():
    sha = git("rev-parse", "HEAD")
    if current_main() != sha:
        print("A main avançou; esta versão antiga não será publicada.")
        return
    run_id = code_id_at_head()
    if run_id and not api("/evolution/permission")["enabled"]:
        report(run_id, "rejected", sha)
        raise RuntimeError("Code autonomy is paused")
    where = target()
    previous = where.previous()
    previous_revision = (
        previous if isinstance(where, Lightsail) else request_json("/api/release")["revision"]
    )
    try:
        where.deploy(sha)
        if not wait_healthy(sha):
            raise RuntimeError("The new API revision did not pass health verification")
    except Exception:
        if previous is None:
            raise RuntimeError("First release failed and there is nothing to restore") from None
        print("Publicação falhou; revertendo para a versão anterior.")
        where.rollback(previous)
        restored = wait_healthy(previous_revision)
        if run_id:
            report(run_id, "reverted", sha)
            # Leave main aligned with the recovered code, without overwriting newer work.
            if restored and current_main() == sha:
                git("config", "user.name", "VISÃO")
                git("config", "user.email", "visao@users.noreply.github.com")
                git("revert", "--no-edit", sha)
                push()
        if not restored:
            raise RuntimeError(
                "Rollback was requested but recovery could not be verified"
            ) from None
        raise RuntimeError("Previous version restored; candidate rejected") from None
    if run_id:
        report(run_id, "published", sha)
    print("Versão publicada e conferida:", sha)


if __name__ == "__main__":
    main()
