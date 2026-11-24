import type { Routine, Routines } from "../hooks/useRoutines";
import { shortHour } from "../hooks/useRoutines";
import { Icon, type IconName } from "./Icon";

const ICON: Record<Routine["kind"], IconName> = { briefing: "clock", study: "notebook", research: "search", panel: "coin" };

/** Rotinas: what he does on his own and when, each with a switch. */
export function RoutinesView({ routines }: { routines: Routines }) {
  const { list, quiet, loaded } = routines;
  return (
    <section className="page routines" aria-labelledby="routines-title">
      <header className="page-head">
        <h1 id="routines-title">Rotinas</h1>
        <p className="lede">
          O que ele faz sozinho e quando. Nada aqui manda mensagem no horário de silêncio
          {quiet ? ` (${shortHour(quiet.quiet_start)}–${shortHour(quiet.quiet_end)})` : ""}.
        </p>
      </header>
      {!loaded ? (
        <p className="note">Carregando…</p>
      ) : (
        <ul className="routine-list">
          {list.map((r) => (
            <li key={r.id} className="routine">
              <Icon name={ICON[r.kind]} size={20} />
              <div className="routine-text">
                <span id={`r-${r.id}`} className="routine-title">{r.title}</span>
                <span className="routine-meta"><span>{r.when}</span><span>{r.delivery}</span></span>
              </div>
              <button
                type="button"
                role="switch"
                className="switch"
                aria-checked={r.on}
                aria-labelledby={`r-${r.id}`}
                onClick={() => void routines.toggle(r)}
              >
                <span aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="note routines-foot">Para acompanhar um preço novo, peça no chat: ele vira um painel e entra aqui.</p>
    </section>
  );
}
