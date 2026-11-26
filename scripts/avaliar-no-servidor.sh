#!/usr/bin/env bash
# Runs experiments/eval_turns.py on the production server, in a throwaway container from the app's
# own image, with the server's settings and an in-memory database: production data is not touched.
# The image leaves tests/ and experiments/ out (.dockerignore), so the branch is downloaded to /tmp.
#
#   wget -q --output-document=- https://github.com/allisonfreittass/visao/raw/<branch>/scripts/avaliar-no-servidor.sh | bash
set -euo pipefail

BRANCH="${BRANCH:-feat/avaliacao-de-turnos}"
LABEL="${LABEL:-antes}"
DIR=/tmp/visao-eval

rm -rf "$DIR" && mkdir -p "$DIR"
wget -q -O - "https://github.com/Allisonfreittass/visao/archive/refs/heads/${BRANCH}.tar.gz" \
  | tar xz -C "$DIR" --strip-components=1
sudo docker run --rm --entrypoint "" --env-file /etc/visao/app.env \
  -v "$DIR":/src -w /src --user root visao:current \
  sh -c "pip install -q pytest >/dev/null 2>&1; python -m experiments.eval_turns ${LABEL}" \
  2>&1 | tail -30 || true
echo
echo "== respostas =="
sudo python3 - "$DIR" <<'PY'
import glob, json, sys
files = sorted(glob.glob(sys.argv[1] + "/experiments/results/turns-*.json"))
if files:
    data = json.load(open(files[-1]))
    print(data["model"], data["passed"], "/", data["total"], "US$", data["cost_usd"])
    for r in data["results"]:
        failed = [k for k, v in r["checks"].items() if not v]
        print(f"- {r['name']}: {'ok' if r['passed'] else 'FALHOU ' + ', '.join(failed)}")
        print("  " + r["reply"].replace("\n", " ")[:300])
PY
