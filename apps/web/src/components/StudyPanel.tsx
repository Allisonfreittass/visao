import { useCallback, useEffect, useState } from "react";

import { ApiError, utcDate, type Api, type StudyNotebook } from "../api";

const STATUS: Record<string, string> = {
  PLANNING: "Escolhendo uma pergunta", READING: "Lendo fontes",
  READY: "Achados registrados", INCONCLUSIVE: "Ainda sem resposta suficiente",
  SKIPPED: "Rodada adiada", FAILED: "Rodada interrompida",
};
const REASONS: Record<string, string> = {
  no_useful_question: "Não identifiquei uma pergunta útil nesta rodada.",
  not_public_topic: "O tema não passou pelos critérios de pesquisa pública.",
  no_sources: "A busca não retornou trechos aproveitáveis.",
  repeated_query: "A retomada não propôs uma busca diferente das anteriores.",
  repeated_question: "A pergunta já estava no caderno; evitei repetir a investigação.",
  invalid_seed_reference: "Não consegui ligar o tema às evidências disponíveis.",
  cycle_budget: "O limite desta rodada foi atingido.",
  permission_revoked: "O estudo foi desligado ou a autonomia foi pausada.",
  unsafe_review: "A revisão não passou pelos critérios de conteúdo público.",
  invalid_model_output: "A resposta do modelo não pôde ser validada.",
};

export function StudyPanel({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [notebook, setNotebook] = useState<StudyNotebook | null>(null);
  const [saving, setSaving] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const refresh = useCallback(async () => {
    const data = await api.study();
    setNotebook(data);
    setUnavailable(false);
  }, [api, onError]);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const data = await api.study();
        if (alive) { setNotebook(data); setUnavailable(false); }
      } catch (e) {
        if (alive && e instanceof ApiError && e.status === 401) onError(e);
        else if (alive) setUnavailable(true);
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 15_000);
    return () => { alive = false; clearInterval(timer); };
  }, [api, onError]);

  async function toggle() {
    if (!notebook) return;
    setSaving(true);
    try { await api.setStudyEnabled(!notebook.enabled); await refresh(); }
    catch (e) { onError(e); }
    finally { setSaving(false); }
  }

  const latest = notebook?.entries[0];
  const evolutionStatus: Record<string, string> = {
    planning: "Analisando uma melhoria", proposed: "Proposta aguardando testes", tested: "Testada, aguardando publicação",
    published: "Publicada", rejected: "Rejeitada nos testes ou na publicação", reverted: "Revertida",
    no_change: "Sem mudança justificada", failed: "Tentativa falhou",
  };
  return (
    <section className="study-panel">
      <div className="study-title">
        <span>O que estou investigando</span>
        <span className="study-status">
          {unavailable ? "Indisponível" : !notebook ? "Carregando…" : notebook.paused
            ? "Autonomia pausada" : !notebook.enabled ? "Desligado"
              : latest ? STATUS[latest.status] ?? latest.status : "Aguardando primeira rodada"}
        </span>
      </div>
      <div className="study-content">
        {unavailable && <p className="note" role="status">O caderno está temporariamente indisponível. A conversa continua funcionando.</p>}
        {notebook && <>
          <label className="memory-toggle">
            <input type="checkbox" checked={notebook.enabled} disabled={saving || unavailable} onChange={() => void toggle()} />
            Permitir estudo autônomo
          </label>
          <p className="note">Leitura de fontes públicas da Wikipédia, com uma rodada nova a cada seis horas. Uma pesquisa sem resposta suficiente pode ter uma única retomada após uma hora, com outra busca. Tudo respeita o orçamento e a pausa de autonomia.</p>
          {notebook.scheduler && <p className="note">Verificação na nuvem: {utcDate(notebook.scheduler.last_tick_at).toLocaleString("pt-BR")}{notebook.scheduler.status === "failed" ? " · A última rodada encontrou uma falha." : ""}</p>}
          {notebook.next_eligible_at && notebook.enabled && <p className="note">
            Próxima oportunidade a partir de {utcDate(notebook.next_eligible_at).toLocaleString("pt-BR")}, conforme o ciclo e o orçamento disponíveis.
          </p>}
          {!latest && <p className="study-empty">Quando houver uma rodada, você verá aqui a pergunta, as fontes e o que ainda falta descobrir.</p>}
          {!!notebook.code_evolution?.length && <article className="study-entry">
            <h3>Evolução do código</h3>
            <p className="note">Alterações autônomas na estratégia de busca e na clareza das respostas. Os testes e a publicação ficam fora do código que posso modificar. A pausa de autonomia também pausa novas alterações.</p>
            {notebook.code_evolution.map(run => <div key={run.id}>
              <h4>{run.summary ?? "Verificação de melhoria"} · {evolutionStatus[run.status] ?? run.status}</h4>
              {run.reason && <p className="note">{run.reason}</p>}
              {run.error && <p className="note">Motivo da falha: {run.error}</p>}
              {run.run_url && <a href={run.run_url} target="_blank" rel="noopener noreferrer">Ver execução de {run.id}</a>}
            </div>)}
          </article>}
          {notebook.entries.map((entry) => <article className="study-entry" key={entry.id}>
            <div className="study-entry-heading"><span>{STATUS[entry.status] ?? entry.status}</span><time>{utcDate(entry.created_at).toLocaleString("pt-BR")}</time></div>
            <h3>{entry.question || "Buscando uma linha de investigação"}</h3>
            {entry.rationale && <p className="note">{entry.rationale}</p>}
            {!!entry.evidence.findings?.length && <>
              <h4>Achados provisórios</h4>
              <ul>{entry.evidence.findings.map((finding, index) => <li key={index}>
                {finding.claim} <span className="study-citations">[{finding.sources.join(", ")}]</span>
              </li>)}</ul>
            </>}
            {entry.evidence.uncertain && <p><strong>Ainda incerto:</strong> {entry.evidence.uncertain}</p>}
            {entry.evidence.next_question && <p className="study-next"><strong>Próxima pergunta:</strong> {entry.evidence.next_question}</p>}
            {!!entry.evidence.sources?.length && <div className="study-sources">
              <h4>Fontes consultadas</h4>
              {entry.evidence.sources.map((source) => <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">[{source.id}] {source.title}</a>)}
              <p className="note">Trechos enciclopédicos; as fontes não representam verificação independente nem certeza definitiva.</p>
            </div>}
            {entry.outcome_reason !== "evidence_recorded" && entry.outcome_reason !== "sources_do_not_answer" && entry.outcome_reason && <p className="note">
              {REASONS[entry.outcome_reason] ?? "Houve uma falha na consulta ao provedor. Uma nova oportunidade ocorrerá em outro ciclo."}
            </p>}
          </article>)}
        </>}
      </div>
    </section>
  );
}
