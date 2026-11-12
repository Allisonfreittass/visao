import { utcDate } from "../api";
import type { Pending } from "../hooks/usePending";
import { dayLabel } from "../labels";

interface InboxViewProps {
  pending: Pending;
  current: string | null;
  onReplied: (conversationId: string) => void;
}

/** Everything that waits for a yes, a no or a read, in one list. */
export function InboxView({ pending, current, onReplied }: InboxViewProps) {
  const empty = pending.count === 0;
  return (
    <section className="page" aria-labelledby="inbox-title">
      <header className="page-head">
        <span className="rotulo">Pendências</span>
        <h1 id="inbox-title">{empty ? <>Nada esperando <em>por você.</em></> : <>O que precisa <em>de você.</em></>}</h1>
        <p className="lede">Eu só proponho. Nada roda sem o seu sim.</p>
      </header>
      <div className="page-body">
        {pending.armProposals.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">No Mac</h2>
            {pending.armProposals.map((t) => (
              <article className="list-item" key={t.id}>
                <div className="list-item-text">
                  <strong>Posso fazer em {t.project}?</strong>
                  <p className="note pre">{t.prompt}</p>
                  <time className="panel-time">{dayLabel(utcDate(t.created_at))}</time>
                </div>
                <div className="row">
                  <button type="button" onClick={() => void pending.decideArm(t, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideArm(t, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.googleActions.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Email e agenda</h2>
            {pending.googleActions.map((a) => (
              <article className="list-item" key={a.id}>
                <div className="list-item-text">
                  <strong>{a.kind === "send_email" ? "Posso mandar este email?" : "Posso marcar isto?"}</strong>
                  <p className="note">{a.summary}</p>
                  {a.kind === "send_email" && a.payload.body && <p className="note pre google-body">{a.payload.body}</p>}
                  {a.kind === "create_event" && a.payload.location && <p className="note">Local: {a.payload.location}</p>}
                  <time className="panel-time">{dayLabel(utcDate(a.created_at))}</time>
                </div>
                <div className="row">
                  <button type="button" onClick={() => void pending.decideGoogle(a, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideGoogle(a, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.goals.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Metas que eu quero seguir</h2>
            {pending.goals.map((g) => (
              <article className="list-item" key={g.id}>
                <div className="list-item-text">
                  <strong>{g.title}</strong>
                  <p className="note">{g.rationale}</p>
                  {g.required_permissions.length > 0 && <p className="note">Preciso de: {g.required_permissions.join(", ")}</p>}
                </div>
                <div className="row">
                  <button type="button" onClick={() => void pending.decideGoal(g, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideGoal(g, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.notices.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Avisos</h2>
            {pending.notices.map((n) => (
              <article className="list-item" key={n.id}>
                <div className="list-item-text">
                  <strong>{n.title}</strong>
                  <p className="note pre">{n.body}</p>
                  <time className="panel-time">{dayLabel(utcDate(n.created_at))}</time>
                </div>
                <div className="row">
                  <button
                    type="button"
                    onClick={() => void pending.reply(n, current).then((id) => { if (id) onReplied(id); })}
                  >
                    Responder
                  </button>
                  <button type="button" className="ghost" onClick={() => void pending.dismiss(n)}>Dispensar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {empty && <p className="note page-empty">Quando eu quiser fazer algo por conta própria, aparece aqui primeiro.</p>}
      </div>
    </section>
  );
}
