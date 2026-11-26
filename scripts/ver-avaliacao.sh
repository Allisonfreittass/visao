#!/usr/bin/env bash
# Prints the last result of scripts/avaliar-no-servidor.sh wrapped to a narrow terminal (the
# Lightsail browser terminal), without calling the model again.
sudo python3 - /tmp/visao-eval <<'PY'
import glob, json, sys, textwrap
files = sorted(glob.glob(sys.argv[1] + "/experiments/results/turns-*.json"))
data = json.load(open(files[-1]))
w = lambda s, ind="": print(textwrap.fill(s, 40, initial_indent=ind, subsequent_indent=ind))
w(f"{data['model']} {data['passed']}/{data['total']} US$ {data['cost_usd']}")
for r in data["results"]:
    failed = [k for k, v in r["checks"].items() if not v]
    print()
    w(f"## {r['name']}: {'ok' if r['passed'] else 'FALHOU'}")
    if failed:
        w("falhou: " + "; ".join(failed), "  ")
    w("passos: " + ", ".join(r["steps"]), "  ")
    if r["name"].startswith(("issue", "criar")):
        w("apps vistos: " + repr(r.get("seen_apps")), "  ")
    w("> " + r["message"], "  ")
    w(r["reply"].replace("\n", " "), "  ")
PY
