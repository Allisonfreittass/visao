import type { ArtifactSummary, Bench as BenchData, ProgressStep } from "../api";
import { utcDate } from "../api";

interface BenchProps {
  bench: BenchData | null;
  /** The turn in flight, step by step; empty when it is not working. */
  steps: ProgressStep[];
  working: boolean;
  onOpenPage: (page: ArtifactSummary) => void;
}

const hour = (iso: string) => utcDate(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

/** Beside the chat on a computer: what it is doing now, and everything it really did here. */
export function Bench({ bench, steps, working, onOpenPage }: BenchProps) {
  const pages = bench?.pages ?? [];
  const visits = bench?.visits ?? [];
  const deeds = bench?.deeds ?? [];
  return (
    <aside className="bench" aria-label="Bancada">
      <section className="bench-card bench-now" aria-live="polite">
        <h2 className="bench-title">Agora</h2>
        {working ? (
          <ol className="bench-steps">
            {(steps.length ? steps : [{ label: "Pensando" }]).map((step, i, all) => (
              <li key={`${i}-${step.label}`} className={i === all.length - 1 ? "bench-step--current" : "bench-step--done"}>
                <span className="bench-step-mark" aria-hidden="true">{i === all.length - 1 ? "" : "✓"}</span>
                <span>
                  {step.label}
                  {step.detail && <small>{step.detail}</small>}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="bench-quiet">Parado. Quando você pedir algo, cada passo aparece aqui.</p>
        )}
      </section>

      {pages.length > 0 && (
        <section className="bench-card">
          <h2 className="bench-title">Páginas</h2>
          <ul className="bench-list">
            {pages.map((page) => (
              <li key={page.id}>
                <button type="button" className="bench-page" disabled={page.status !== "ready"} onClick={() => onOpenPage(page)}>
                  <strong>{page.title}</strong>
                  <span>{page.status === "ready" ? "Abrir" : page.status === "pending" ? "Criando…" : "Não deu certo"}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {visits.length > 0 && (
        <section className="bench-card">
          <h2 className="bench-title">Lido ao vivo</h2>
          <ul className="bench-list">
            {visits.map((visit) => (
              <li key={`${visit.url}-${visit.at}`}>
                <a href={visit.url} target="_blank" rel="noopener noreferrer" className="bench-visit">
                  <strong>{visit.title}</strong>
                  <span>{host(visit.url)} · {hour(visit.at)}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="bench-card">
        <h2 className="bench-title">O que fiz de verdade</h2>
        {deeds.length === 0 ? (
          <p className="bench-quiet">Nada além de conversar, por enquanto.</p>
        ) : (
          <ol className="bench-deeds">
            {deeds.map((deed) => (
              <li key={`${deed.at}-${deed.text}`}>
                <time>{hour(deed.at)}</time>
                <span>{deed.text}</span>
              </li>
            ))}
          </ol>
        )}
        <p className="bench-note">Tirado do registro do sistema, não do que eu disse.</p>
      </section>
    </aside>
  );
}
