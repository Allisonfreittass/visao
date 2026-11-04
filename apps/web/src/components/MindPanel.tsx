import { useEffect, useState } from "react";

import { ApiError, utcDate, type Api, type Mind } from "../api";

const DELIVERY: Record<string, string> = {
  sent: "mandou",
  quiet_hours: "guardou: horário silencioso",
  owner_active: "guardou: você estava falando",
  waiting_for_reply: "guardou: esperando você responder",
  daily_limit: "guardou: limite do dia",
  paused: "guardou: autonomia pausada",
};

/** What the agent is thinking, what it cares about and how it describes itself right now. */
export function MindPanel({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [mind, setMind] = useState<Mind | null>(null);
  useEffect(() => {
    let alive = true;
    const poll = () => api.mind().then((next) => { if (alive) setMind(next); }).catch((e) => {
      if (alive && e instanceof ApiError && e.status === 401) onError(e);
    });
    void poll();
    const timer = setInterval(() => void poll(), 15_000);
    return () => { alive = false; clearInterval(timer); };
  }, [api, onError]);

  if (!mind?.enabled) return null;
  const previous = mind.self_history[1];
  async function undo() {
    await api.revertSelf(previous ? previous.version : null);
    setMind(await api.mind());
  }
  return (
    <section className="mind-panel">
      <article className="study-entry">
        <h3>Como ele se descreve agora</h3>
        <p>{mind.self_text}</p>
        {mind.self_history[0] && <p className="note">Mudou porque: {mind.self_history[0].reason}{" "}
          <button type="button" className="link-button" onClick={() => void undo()}>desfazer</button></p>}
      </article>
      {!!mind.interests.length && <article className="study-entry">
        <h3>Interesses</h3>
        <ul>{mind.interests.map((item) => <li key={item.topic}><strong>{item.topic}</strong>: {item.why}</li>)}</ul>
      </article>}
      <article className="study-entry">
        <h3>Pensamentos</h3>
        {!mind.thoughts.length && <p className="note">Ainda não pensou nada: rode o worker.</p>}
        {mind.thoughts.map((thought) => <div className="mind-thought" key={thought.created_at}>
          <time>{utcDate(thought.created_at).toLocaleString("pt-BR")}</time>
          <p>{thought.content}</p>
          {thought.ask_owner && <p className="note">Quer perguntar: {thought.ask_owner}</p>}
          {thought.wanted_to_say && <p className="note">Quis dizer ({DELIVERY[thought.delivery ?? ""] ?? thought.delivery}): {thought.wanted_to_say}</p>}
        </div>)}
      </article>
    </section>
  );
}
