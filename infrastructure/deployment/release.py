"""Deploy the CI-tested main SHA, verify its running API, and roll back on failure."""

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
    api,
    code_id_at_head,
    git,
    push,
    report,
)

CLOUD = ROOT / "infrastructure" / "cloudflare"
URL = "https://visao.auris-api.workers.dev"


def wrangler(*args, capture=False):
    result = subprocess.run(  # noqa: S603
        ["npx", "wrangler", *args],  # noqa: S607
        cwd=CLOUD,
        text=True,
        check=True,
        capture_output=capture,
    )  # noqa: S603,S607
    return result.stdout if capture else None


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
            return response.status == 200 and "VISÃO" in response.read().decode()
    except Exception:
        return False


def wait_healthy(revision):
    for _ in range(30):
        if healthy(revision):
            return True
        time.sleep(5)
    return False


def main():
    sha = git("rev-parse", "HEAD")
    if current_main() != sha:
        print("A main avançou; esta versão antiga não será publicada.")
        return
    run_id = code_id_at_head()
    if run_id and not api("/evolution/permission")["enabled"]:
        report(run_id, "rejected", sha)
        raise RuntimeError("Code autonomy is paused")
    deployments = json.loads(wrangler("deployments", "list", "--json", capture=True))
    previous = max(deployments, key=lambda d: d["created_on"])
    if len(previous["versions"]) != 1 or previous["versions"][0]["percentage"] != 100:
        raise ValueError("Automatic release requires a single known previous version")
    previous_version = previous["versions"][0]["version_id"]
    previous_revision = request_json("/api/release")["revision"]
    try:
        wrangler(
            "deploy",
            "--var",
            f"VISION_BUILD_SHA:{sha}",
            "--durable-objects-code-update-mode",
            "deferred 30s",
        )
        if not wait_healthy(sha):
            raise RuntimeError("The new API revision did not pass health verification")
    except Exception:
        print("Publicação falhou; revertendo para a versão anterior.")
        wrangler(
            "rollback",
            previous_version,
            "--yes",
            "--message",
            "Automatic health rollback",
            "--durable-objects-code-update-mode",
            "immediate",
        )
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
