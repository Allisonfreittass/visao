import { useState } from "react";

import { type Api, type ArmDevice, utcDate } from "../api";
import type { Pending } from "../hooks/usePending";
import { dayLabel, TASK_STATUS } from "../labels";

interface MacViewProps {
  api: Api;
  pending: Pending;
  onError: (e: unknown) => void;
}

/** The arm on the owner's Mac: is it on, which projects it opens, and the work it did. */
export function MacView({ api, pending, onError }: MacViewProps) {
  const [pairing, setPairing] = useState<ArmDevice | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const { devices, tasks } = pending;

  async function pair() {
    setBusy(true);
    try {
      setPairing(await api.pairArm("Mac"));
      setCopied(false);
      pending.refresh();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function unpair(device: ArmDevice) {
    if (!window.confirm(`Desconectar ${device.name}? O braço dele para na hora.`)) return;
    await api.unpairArm(device.id).catch(onError);
    pending.refresh();
  }

  async function copy(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const history = tasks.filter((t) => t.status !== "proposed").slice(0, 12);
  return (
    <section className="page" aria-labelledby="mac-title">
      <header className="page-head">
        <span className="rotulo">Mac</span>
        <h1 id="mac-title">{devices.length ? <>Trabalho no seu <em>Mac.</em></> : <>Conecte o seu <em>Mac.</em></>}</h1>
        <p className="lede">Eu peço ao Claude Code nos projetos que você liberou. Escreva <code>/mac projeto o que fazer</code> na conversa.</p>
      </header>
      <div className="page-body">
        <section className="list-group">
          <h2 className="rotulo">Aparelhos</h2>
          {devices.map((d) => (
            <article className="list-item" key={d.id}>
              <div className="list-item-text">
                <strong><span className={`status-dot ${d.online ? "on" : ""}`} aria-hidden="true" />{d.name} · {d.online ? "ligado" : "desligado"}</strong>
                <p className="note">{d.projects.length ? d.projects.join(", ") : "Nenhum projeto liberado no braco.json."}</p>
                {d.last_seen_at && <time className="panel-time">Visto {dayLabel(utcDate(d.last_seen_at)).toLowerCase()}</time>}
              </div>
              <div className="row">
                <button type="button" className="ghost" onClick={() => void unpair(d)}>Desconectar</button>
              </div>
            </article>
          ))}
          {pairing?.token ? (
            <div className="list-item mac-pairing">
              <div className="list-item-text">
                <strong>Cole este token em <code>~/.config/visao/braco.json</code></strong>
                <p className="note">Ele não aparece de novo. Depois rode <code>bash arm/instalar-mac.sh</code> no Mac.</p>
                <code className="mac-token">{pairing.token}</code>
              </div>
              <div className="row">
                <button type="button" onClick={() => void copy(pairing.token ?? "")}>{copied ? "Copiado" : "Copiar token"}</button>
                <button type="button" className="ghost" onClick={() => setPairing(null)}>Pronto</button>
              </div>
            </div>
          ) : (
            <div className="row">
              <button type="button" onClick={() => void pair()} disabled={busy}>{devices.length ? "Conectar outro Mac" : "Conectar o Mac"}</button>
            </div>
          )}
        </section>
        <section className="list-group">
          <h2 className="rotulo">O que eu fiz lá</h2>
          {history.length === 0 && <p className="note">Nada ainda.</p>}
          <ul className="task-list">
            {history.map((t) => (
              <li key={t.id} className={`task task--${t.status}`}>
                <span className="task-status">{TASK_STATUS[t.status] ?? t.status}</span>
                <span className="task-what"><b>{t.project}</b> {t.prompt}</span>
                <time className="panel-time">{dayLabel(utcDate(t.finished_at ?? t.created_at))}</time>
                {t.status === "approved" && (
                  <button type="button" className="link-button" onClick={() => void pending.decideArm(t, "reject")}>cancelar</button>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}
