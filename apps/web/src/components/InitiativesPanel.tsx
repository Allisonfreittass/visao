import { useCallback, useEffect, useState } from "react";

import type { Api, AppNotification, Goal } from "../api";

const POLL_MS = 30_000;

interface Props {
  api: Api;
  onError: (e: unknown) => void;
}

/** Approvals, notifications and the global autonomy pause. */
export function InitiativesPanel({ api, onError }: Props) {
  const [approvals, setApprovals] = useState<Goal[]>([]);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [paused, setPaused] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([api.approvals(), api.notifications(), api.autonomy()])
      .then(([a, n, auto]) => {
        setApprovals(a);
        setNotifications(n);
        setPaused(auto.paused);
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

  async function read(notification: AppNotification) {
    try {
      await api.markRead(notification.id);
      refresh();
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

  const unread = notifications.filter((n) => !n.read_at);

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
      {unread.length > 0 && (
        <section>
          <h3>Avisos ({unread.length})</h3>
          {unread.map((n) => (
            <div key={n.id} className="card">
              <strong>{n.title}</strong>
              <p className="note pre">{n.body}</p>
              <button className="ghost" onClick={() => read(n)}>
                Marcar como lido
              </button>
            </div>
          ))}
        </section>
      )}
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
