"""Trusted Actions controller. Generated files are never executed on the host runner."""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.evolution.guard import ALLOWED, digest, snapshot, validate_patch  # noqa: E402

BASE_URL = "https://visao.auris-api.workers.dev/api"
DATA = ROOT / ".code-run" / "proposal.json"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()  # noqa: S603,S607


def api(path, data=None):
    request = urllib.request.Request(  # noqa: S310 (fixed HTTPS service)
        BASE_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "visao-code-controller/1.0",
            "X-Visao-Code-Key": os.environ["VISION_CODE_AUTONOMY_KEY"],
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.load(response)


def output(name, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as file:
        file.write(f"{name}={value}\n")


def report(run_id, status, commit=None):
    return api(
        "/evolution/report",
        {
            "id": run_id,
            "status": status,
            "commit": commit,
            "run_url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        },
    )


def code_id_at_head():
    paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    for path in paths:
        if re.fullmatch(r"\.visao/changes/\d{4}-\d{2}-\d{2}\.json", path):
            value = json.loads((ROOT / path).read_text())
            if value["base_sha"] == git("rev-parse", "HEAD^"):
                return value["id"]
    return None


def push():
    # The token stays in the step environment, not a URL, process argument or git config file.
    helper = '!f() { printf "%s\\n" username=x-access-token "password=$GH_TOKEN"; }; f'
    subprocess.run(  # noqa: S603
        ["git", "-c", f"credential.helper={helper}", "push", "origin", "HEAD:main"],  # noqa: S607
        cwd=ROOT,
        check=True,
    )  # noqa: S603,S607


def propose():
    base = git("rev-parse", "HEAD")
    files = snapshot(ROOT)
    result = api("/evolution/propose", {"base_sha": base, "files": files})
    if result.get("status") != "proposed":
        print("Sem alteração:", result.get("status"))
        output("changed", "false")
        return
    run_id = result.get("id", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_id):
        raise ValueError("invalid_run_id")
    # Rebuild a proposal and validate independently of the API response.
    patch = {
        "change": True,
        "summary": result["summary"],
        "reason": result["reason"],
        "files": [{"path": f["path"], "content": f["content"]} for f in result["changes"]],
    }
    changes = validate_patch(files, patch)
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({**result, "snapshot": files, "changes": changes}))
    DATA.chmod(0o600)
    for change in changes:
        target = ROOT / change["path"]
        if target.is_symlink() or digest(target.read_text()) != change["previous_sha256"]:
            raise ValueError("source_changed")
        target.write_text(change["content"])
    output("changed", "true")
    output("id", run_id)
    print("Proposta recebida; aguardando testes isolados.")


def publish():
    data = json.loads(DATA.read_text())
    if not api("/evolution/permission")["enabled"]:
        report(data["id"], "rejected")
        raise ValueError("autonomy_paused")
    git("fetch", "origin", "main")
    if git("rev-parse", "origin/main") != data["base_sha"]:
        report(data["id"], "rejected")
        raise ValueError("main_changed")
    changed = set(git("diff", "--name-only").splitlines())
    if changed != {item["path"] for item in data["changes"]} or not changed <= set(ALLOWED):
        raise ValueError("unexpected_files")
    for item in data["changes"]:
        if digest((ROOT / item["path"]).read_text()) != item["sha256"]:
            raise ValueError("candidate_changed_after_test")
    manifest = ROOT / ".visao" / "changes" / f"{data['id']}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {k: data[k] for k in ("id", "base_sha", "summary", "reason")},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    git("config", "user.name", "VISÃO")
    git("config", "user.email", "visao@users.noreply.github.com")
    git("add", *sorted(changed), str(manifest.relative_to(ROOT)))
    git("commit", "-m", "visao: " + data["summary"])
    sha = git("rev-parse", "HEAD")
    report(data["id"], "tested", sha)
    try:
        push()
        request = urllib.request.Request(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/ci.yml/dispatches",
            data=json.dumps({"ref": "main"}).encode(),
            headers={
                "Authorization": "Bearer " + os.environ["GH_TOKEN"],
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30):  # noqa: S310
            pass
    except Exception:
        report(data["id"], "rejected", sha)
        raise
    print("Mudança enviada; CI e CD decidirão a publicação.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["propose", "publish", "reject", "report-head"])
    parser.add_argument("--status", choices=["published", "reverted", "rejected"])
    args = parser.parse_args()
    if args.command == "propose":
        propose()
    elif args.command == "publish":
        publish()
    elif args.command == "reject":
        if DATA.exists():
            report(json.loads(DATA.read_text())["id"], "rejected")
    else:
        run_id = code_id_at_head()
        if run_id:
            report(run_id, args.status, git("rev-parse", "HEAD"))
