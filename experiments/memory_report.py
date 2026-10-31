"""Aggregates every memory-benchmark-*.json run into one table per variant.

For each (model, scenario, variant) the most recent run without errors wins, so scenarios can be
run in batches over several days (free-tier quotas).

    .venv/bin/python -m experiments.memory_report
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"


def latest_results(paths: list[Path]) -> dict[tuple[str, str, str], dict[str, Any]]:
    chosen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in sorted(paths):  # file names sort by timestamp
        run = json.loads(path.read_text())
        for result in run["results"]:
            if result["errors"]:
                continue
            chosen[(run["model"], result["scenario"], result["variant"])] = result
    return chosen


def comparable(
    results: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Keeps only scenarios that every variant of the same model completed, so all variants
    are compared on exactly the same scenario set."""
    variants_by_model: dict[str, set[str]] = defaultdict(set)
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    for model, scenario, variant in results:
        variants_by_model[model].add(variant)
        seen[(model, scenario)].add(variant)
    return {
        key: value
        for key, value in results.items()
        if seen[(key[0], key[1])] == variants_by_model[key[0]]
    }


def summarize(results: dict[tuple[str, str, str], dict[str, Any]]) -> dict[tuple[str, str], dict]:
    table: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "scenarios": set(),
            "hits": 0,
            "hit_total": 0,
            "leaks": 0,
            "probes": 0,
            "store_found": 0,
            "store_total": 0,
            "forbidden_stored": 0,
            "memories": 0,
            "memory_chars": 0,
            "calls": 0,
            "tokens": 0,
        }
    )
    for (model, scenario, variant), r in results.items():
        row = table[(model, variant)]
        row["scenarios"].add(scenario)
        for probe in r["probes"]:
            row["probes"] += 1
            if probe.get("hit") is not None:
                row["hit_total"] += 1
                row["hits"] += int(probe["hit"])
            row["leaks"] += int(bool(probe.get("leaked")))
        row["store_found"] += len(r["store_expected_found"])
        row["store_total"] += r["store_expected_total"]
        row["forbidden_stored"] += len(r["store_forbidden_found"])
        row["memories"] += len(r["stored_memories"])
        row["memory_chars"] += r["memory_chars"]
        row["calls"] += r["llm_calls"]
        row["tokens"] += r["input_tokens"] + r["output_tokens"]
    return table


def render(table: dict[tuple[str, str], dict[str, Any]]) -> str:
    lines = [
        "| Modelo | Var. | Cenários | Acerto nas perguntas | Respostas com dado proibido "
        "| Fatos esperados guardados | Termos proibidos guardados | Memórias | Chamadas | Tokens |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (model, variant), r in sorted(table.items()):
        store = f"{r['store_found']}/{r['store_total']}" if variant != "A" else "n/a"
        lines.append(
            f"| {model} | {variant} | {len(r['scenarios'])} | {r['hits']}/{r['hit_total']} "
            f"| {r['leaks']}/{r['probes']} | {store} | {r['forbidden_stored']} "
            f"| {r['memories']} | {r['calls']} | {r['tokens']} |"
        )
    return "\n".join(lines)


def main() -> int:
    paths = list(RESULTS_DIR.glob("memory-benchmark-*.json"))
    if not paths:
        print("Nenhum resultado encontrado. Rode experiments.memory_benchmark antes.")
        return 1
    results = latest_results(paths)
    kept = comparable(results)
    dropped = sorted({(m, s) for m, s, _ in results} - {(m, s) for m, s, _ in kept})
    print(render(summarize(kept)))
    if dropped:
        print("\nIncompletos (fora da comparação): " + ", ".join(f"{s} ({m})" for m, s in dropped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
