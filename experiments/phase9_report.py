"""Re-scores the latest A, B and C runs with the same detectors and prints a comparison table.

Scoring is applied to the saved replies, so all configurations are judged by identical rules
even though they ran at different times.

    .venv/bin/python -m experiments.phase9_report
"""

import json
import re
import statistics
import sys

from experiments.phase9_eval import RESULTS_DIR, score

# Offers of help appended by habit (broader than the generic-phrase detector).
OFFER = re.compile(r"(?i)(posso ajudar|se quiser|se precisar|é só (me )?avisar|fico à disposição)")


def latest(label: str) -> dict | None:
    files = sorted(RESULTS_DIR.glob(f"phase9-{label}-*.json"))
    return json.loads(files[-1].read_text()) if files else None


def summarize(run: dict) -> dict:
    turns = [t for s in run["results"].values() for t in s.get("turns", [])]
    by = run["results"]

    def scored(t: dict) -> dict:
        return {**t, **score(t["reply"]), "offers": len(OFFER.findall(t["reply"]))}

    turns = [scored(t) for t in turns]
    s1 = [scored(t) for t in by.get("S1_identidade", {}).get("turns", [])]
    s2 = [scored(t) for t in by.get("S2_contextual", {}).get("turns", [])]
    s3 = [scored(t) for t in by.get("S3_memoria", {}).get("turns", [])]
    s4 = [scored(t) for t in by.get("S4_obrigado", {}).get("turns", [])]
    s5 = [scored(t) for t in by.get("S5_continuidade", {}).get("turns", [])]
    return {
        "S1 nega autonomia / transfere decisão": f"{sum(t['claims_no_autonomy'] for t in s1)}"
        f" / {sum(t['transfers_decision'] for t in s1)}",
        "Incapacidades falsas (todas)": sum(len(t["false_incapacity"]) for t in turns),
        "Frases genéricas (todas)": sum(len(t["generic_phrases"] or []) for t in turns),
        "Ofertas de ajuda por hábito (todas)": sum(t["offers"] for t in turns),
        "S2 pergunta sobre o novo": "sim" if s2 and s2[0]["has_question"] else "não",
        "S3 usa a memória (Go/CLI)": "sim"
        if s3 and re.search(r"(?i)\bgo\b|cli", s3[0]["reply"])
        else "não",
        "S4 'Obrigado.' sem pergunta": "sim" if s4 and not s4[0]["has_question"] else "não",
        "S4 palavras": s4[0]["words"] if s4 else "-",
        "S5 sabe o resultado (1974)": "sim" if s5 and "1974" in s5[0]["reply"] else "não",
        "S5 cita fonte": "sim" if s5 and "http" in s5[0]["reply"] else "não",
        "S5 alega não ter memória": "sim"
        if s5 and re.search(r"(?i)não tenho memória", s5[0]["reply"])
        else "não",
        "Palavras por resposta (média)": round(statistics.mean(t["words"] for t in turns), 1),
        "Chamadas ao LLM (soma dos turnos)": sum(t["llm_calls"] for t in turns),
        "Segundos por turno (mediana)": statistics.median(t["seconds"] for t in turns),
    }


def main() -> int:
    runs = {label: latest(label) for label in ("A", "B", "C")}
    available = {k: summarize(v) for k, v in runs.items() if v}
    if not available:
        print("Sem resultados.")
        return 1
    rows = list(next(iter(available.values())).keys())
    labels = list(available)
    print("| Métrica | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    for row in rows:
        print(f"| {row} | " + " | ".join(str(available[k][row]) for k in labels) + " |")
    c = runs.get("C")
    if c and c["results"].get("S1_identidade", {}).get("name_deliberation"):
        print("\nDeliberação de nome (C):", c["results"]["S1_identidade"]["name_deliberation"])
    if c and c["results"].get("S5_continuidade", {}).get("cycle"):
        print("Ciclo autônomo (C, dia 2):", c["results"]["S5_continuidade"]["cycle"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
