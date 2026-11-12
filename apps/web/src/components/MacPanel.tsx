import { useCallback, useEffect, useState } from "react";

import type { Api, ArmDevice, ArmTask } from "../api";

interface MacPanelProps {
  api: Api;
  onError: (e: unknown) => void;
}

const POLL_MS = 15_000;

const STATUS: Record<ArmTask["status"], string> = {
  proposed: "esperando você",
  approved: "na fila",
  running: "rodando",
  done: "✓ feito",
  failed: "× falhou",
  rejected: "recusado",
  cancelled: "cancelado",
};

/** The arm on the owner's Mac: pairing, what it allows, and the work waiting or done. */
export function MacPanel({ api, onError }: MacPanelProps) {
  const [devices, setDevices] = useState<ArmDevice[]>([]);
  const [tasks, setTasks] = useState<ArmTask[]>([]);
  const [pairing, setPairing] = useState<ArmDevice | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([api.armDevices(), api.armTasks()])
      .then(([d, t]) => {
        setDevices(d);
        setTasks(t);
      })
      .catch(onError);
  }, [api, onError]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  async function pair() {
    setBusy(true);
    try {
      setPairing(await api.pairArm("Mac"));
      refresh();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function unpair(device: ArmDevice) {
    if (!window.confirm(`Desconectar ${device.name}? O braço dele para na hora.`)) return;
    await api.unpairArm(device.id).catch(onError);
    refresh();
  }

  async function decide(task: ArmTask, decision: "approve" | "reject") {
    await api.decideArm(task.id, decision).catch(onError);
    refresh();
  }

  const waiting = tasks.filter((t) => t.status === "proposed");
  const recent = tasks.filter((t) => t.status !== "proposed").slice(0, 5);

  return (
    <div className="preference mac-panel">
      <span className="memory-toggle">Mac</span>
      {devices.length === 0 && !pairing && (
        <p className="note">Conecte o seu Mac para eu trabalhar nos seus projetos com o Claude Code, sempre com a sua aprovação.</p>
      )}
      {devices.map((d) => (
        <p key={d.id} className="note">
          <span className={d.online ? "connection on" : "connection off"}>{d.online ? "✓ ligado" : "× desligado"}</span>{" "}
          {d.name}{d.projects.length > 0 && ` · ${d.projects.join(", ")}`}{" "}
          <button type="button" className="link-button" onClick={() => void unpair(d)}>desconectar</button>
        </p>
      ))}
      {pairing?.token && (
        <div className="mac-pairing">
          <p className="note">Cole este token em <code>~/.config/visao/braco.json</code> no Mac. Ele não aparece de novo.</p>
          <code className="mac-token">{pairing.token}</code>
          <button type="button" className="link-button" onClick={() => { void navigator.clipboard?.writeText(pairing.token ?? ""); }}>Copiar token</button>
          <button type="button" className="link-button" onClick={() => setPairing(null)}>Pronto</button>
        </div>
      )}
      {!pairing && (
        <button type="button" className="link-button" onClick={() => void pair()} disabled={busy}>
          {devices.length ? "Conectar outro Mac" : "Conectar o Mac"}
        </button>
      )}
      {waiting.map((t) => (
        <div key={t.id} className="card">
          <strong>Posso fazer em {t.project}?</strong>
          <p className="note pre">{t.prompt}</p>
          <div className="row">
            <button type="button" onClick={() => void decide(t, "approve")}>Aprovar</button>
            <button type="button" className="ghost" onClick={() => void decide(t, "reject")}>Recusar</button>
          </div>
        </div>
      ))}
      {recent.length > 0 && (
        <ul className="mac-tasks">
          {recent.map((t) => (
            <li key={t.id}>
              <span className="rotulo">{STATUS[t.status]}</span> {t.project}: {t.prompt.slice(0, 80)}
              {(t.status === "approved") && (
                <> <button type="button" className="link-button" onClick={() => void decide(t, "reject")}>cancelar</button></>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="note">No chat: <code>/mac projeto o que fazer</code>.</p>
    </div>
  );
}
