import { useCallback, useEffect, useState } from "react";

import type { Api, Goal } from "../api";

const POLL_MS = 30_000;

interface Props {
  api: Api;
  onError: (e: unknown) => void;
}

/** Approvals, notifications and the global autonomy pause. */
export function InitiativesPanel({ api, onError }: Props) {
  const [approvals, setApprovals] = useState<Goal[]>([]);
  const [paused, setPaused] = useState(false);
  const [autoResearch, setAutoResearch] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([api.approvals(), api.autonomy(), api.permissions()])
      .then(([a, auto, perms]) => {
        setApprovals(a);
        setPaused(auto.paused);
        setAutoResearch(perms.auto_research);
      })
      .catch(onError);
  }, [api, onError]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  async function decide(goal: Goal, decision: "approve" | "reject") {
    try {
      await api.decideGoal(goal.id, decision);
      refresh();
    } catch (e) {
      onError(e);
    }
  }

  async function toggleAutoResearch() {
    try {
      setAutoResearch((await api.setAutoResearch(!autoResearch)).auto_research);
    } catch (e) {
      onError(e);
    }
  }

  async function togglePause() {
    try {
      setPaused((await api.setAutonomyPaused(!paused)).paused);
    } catch (e) {
      onError(e);
    }
  }

  return (
    <div className="initiatives">
      {approvals.length > 0 && (
        <section>
          <h3>Aguardando sua aprovação</h3>
          {approvals.map((goal) => (
            <div key={goal.id} className="card">
              <strong>{goal.title}</strong>
              <p className="note">{goal.rationale}</p>
              <p className="note">Permissões: {goal.required_permissions.join(", ")}</p>
              <div className="row">
                <button onClick={() => decide(goal, "approve")}>Aprovar</button>
                <button className="ghost" onClick={() => decide(goal, "reject")}>
                  Rejeitar
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
      <label className="memory-toggle">
        <input type="checkbox" checked={autoResearch} onChange={toggleAutoResearch} />
        Permitir pesquisas autônomas
      </label>
      <p className="note">
        Ligado, dúvidas de fatos públicos que ficaram sem resposta são pesquisadas de novo pelo
        ciclo autônomo (só Wikipédia, dentro do orçamento), sem pedir aprovação a cada vez.
      </p>
      <label className="memory-toggle">
        <input type="checkbox" checked={paused} onChange={togglePause} />
        Pausar autonomia
      </label>
      <p className="note">
        Pausada, nada roda por iniciativa própria: sem metas novas, sem pesquisas agendadas, sem
        avisos. A conversa continua funcionando.
      </p>
    </div>
  );
}
