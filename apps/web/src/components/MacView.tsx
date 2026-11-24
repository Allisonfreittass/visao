import { useEffect, useState } from "react";

import { type Api, type ArmDevice, type ArmTask, utcDate } from "../api";
import { taskDetail, undoQuestion } from "../arm";
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
  const { devices } = pending;
  const [fresh, setFresh] = useState<ArmTask[] | null>(null);
  const tasks = fresh ?? pending.tasks;
  const [selected, setSelected] = useState<string | null>(null);
  const running = tasks.some((t) => t.status === "running" || t.status === "approved");
  // While something runs, read the tasks every 3 s: the log on the right follows.
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const timer = setInterval(() => { api.armTasks().then((list) => alive && setFresh(list), () => undefined); }, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [api, running]);
  useEffect(() => setFresh(null), [pending.tasks]);

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

  async function undo(task: ArmTask) {
    if (!window.confirm(undoQuestion(task))) return;
    await api.undoArm(task.id).catch(onError);
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
  const current = history.find((t) => t.id === selected) ?? history.find((t) => t.status === "running") ?? history[0] ?? null;
  const online = devices.find((d) => d.online);
  return (
    <section className="page" aria-labelledby="mac-title">
      <header className="page-head">
        <h1 id="mac-title">Mac</h1>
        <p className="lede">
          {online ? `${online.name} · conectado. ` : devices.length ? "Mac desligado. " : ""}
          Ele só trabalha nos projetos que você liberou, e cada tarefa espera o seu sim. Escreva <code>/mac projeto o que fazer</code> na conversa.
        </p>
      </header>
      {history.length > 0 && (
        <div className="mac-split">
          <div className="mac-tasks" role="listbox" aria-label="Tarefas no Mac">
            <p className="mac-col-title">Tarefas</p>
            {history.map((t) => (
              <button
                key={t.id}
                type="button"
                role="option"
                aria-selected={current?.id === t.id}
                className="mac-task"
                onClick={() => setSelected(t.id)}
              >
                <span className="mac-task-what">{t.prompt}</span>
                <span className="mac-task-meta"><span>{TASK_STATUS[t.status] ?? t.status}{t.changed_files?.length ? ` · ${t.changed_files.length} ${t.changed_files.length === 1 ? "arquivo" : "arquivos"}` : ""}</span><span>{dayLabel(utcDate(t.finished_at ?? t.created_at))}</span></span>
              </button>
            ))}
          </div>
          {current && <TaskLog task={current} onCancel={() => void pending.decideArm(current, "reject")} onUndo={() => void undo(current)} />}
        </div>
      )}
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
      </div>
    </section>
  );
}

/** The selected task as a terminal: what was asked, what came back, the files and tests the arm
 * measured, the cost. The server sends the result when the task ends, not each line as it runs. */
function TaskLog({ task, onCancel, onUndo }: { task: ArmTask; onCancel: () => void; onUndo: () => void }) {
  const detail = taskDetail(task);
  const live = task.status === "running" || task.status === "approved";
  return (
    <section className="mac-log" aria-label={`Registro: ${task.prompt}`} aria-live={live ? "polite" : "off"}>
      <div className="mac-log-head"><span>{task.prompt}</span><span className="mac-log-project">{task.project}</span></div>
      <pre className="mac-log-body">
        <span className="mac-log-dim">{task.project} $</span> {task.prompt}{"\n"}
        {live && <><span className="mac-log-dim">›</span> {task.status === "approved" ? "na fila do Mac" : "rodando"}…<span className="mac-log-cursor" aria-hidden="true">▍</span>{"\n"}</>}
        {task.result && <>{task.result}{"\n"}</>}
        {task.error && <><span className="mac-log-fail">ERRO</span> {task.error}{"\n"}</>}
        {task.changed_files?.map((f) => <span key={f.path}><span className="mac-log-dim">{f.status}</span> {f.path}{"\n"}</span>)}
        {detail && <span className="mac-log-dim">{detail}</span>}
      </pre>
      <div className="mac-log-foot">
        {task.status === "approved" && <button type="button" className="btn-secondary btn-small" onClick={onCancel}>Cancelar</button>}
        {task.can_undo && <button type="button" className="btn-secondary btn-small" onClick={onUndo}>Desfazer</button>}
        <span>{task.requested_by === "agent" ? "pedido por ele · aprovado por você" : "pedido por você"}</span>
        {task.cost_usd && <span className="mac-log-cost">custo: US$ {Number(task.cost_usd).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>}
      </div>
      {live && <p className="note">O passo a passo ao vivo ainda não vem do servidor: o resultado aparece quando a tarefa termina.</p>}
    </section>
  );
}
