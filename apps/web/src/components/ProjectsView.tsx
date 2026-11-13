import { type FormEvent, useCallback, useEffect, useState } from "react";

import { type Api, type Project, type ProjectDetail, utcDate } from "../api";
import { attachmentUrl, formatSize } from "../attachments";
import { dayLabel } from "../labels";

interface ProjectsViewProps {
  api: Api;
  /** The conversation open in the chat, to bring it into a project. */
  current: string | null;
  currentProjectId: string | null;
  onOpenConversation: (id: string) => void;
  onNewConversation: (projectId: string) => void;
  onMoved: (conversationId: string, projectId: string | null) => void;
  onError: (e: unknown) => void;
}

/** Projetos: subjects with their conversations, pages and files together. */
export function ProjectsView({ api, current, currentProjectId, onOpenConversation, onNewConversation, onMoved, onError }: ProjectsViewProps) {
  const [list, setList] = useState<Project[] | null>(null);
  const [open, setOpen] = useState<ProjectDetail | null>(null);
  const [name, setName] = useState("");

  const reload = useCallback(() => {
    api.projects().then(setList).catch(onError);
  }, [api, onError]);

  useEffect(reload, [reload]);

  async function show(id: string) {
    try {
      setOpen(await api.project(id));
    } catch (e) {
      onError(e);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const project = await api.createProject(name.trim());
      setName("");
      reload();
      await show(project.id);
    } catch (e) {
      onError(e);
    }
  }

  async function rename() {
    if (!open) return;
    const next = window.prompt("Novo nome do projeto", open.name);
    if (!next?.trim()) return;
    try {
      await api.renameProject(open.id, next.trim());
      await show(open.id);
      reload();
    } catch (e) {
      onError(e);
    }
  }

  async function remove() {
    if (!open || !window.confirm(`Apagar o projeto “${open.name}”? As conversas, páginas e arquivos continuam, só saem do projeto.`)) return;
    try {
      await api.deleteProject(open.id);
      open.conversation_list.forEach((c) => onMoved(c.id, null));
      setOpen(null);
      reload();
    } catch (e) {
      onError(e);
    }
  }

  async function bringCurrent() {
    if (!open || !current) return;
    try {
      await api.moveConversation(current, open.id);
      onMoved(current, open.id);
      await show(open.id);
      reload();
    } catch (e) {
      onError(e);
    }
  }

  async function download(id: string, filename: string) {
    try {
      const url = await attachmentUrl(id, (x) => api.attachmentBlob(x));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    } catch (e) {
      onError(e);
    }
  }

  if (open) {
    return (
      <section className="page projects" aria-labelledby="project-title">
        <header className="page-head">
          <button type="button" className="link-button projects-back" onClick={() => { setOpen(null); reload(); }}>← Projetos</button>
          <h1 id="project-title">{open.name}</h1>
          <div className="row">
            <button type="button" className="projects-primary" onClick={() => onNewConversation(open.id)}>Nova conversa aqui</button>
            {current && currentProjectId !== open.id && (
              <button type="button" onClick={() => void bringCurrent()}>Trazer a conversa aberta</button>
            )}
            <button type="button" className="ghost" onClick={() => void rename()}>Renomear</button>
            <button type="button" className="ghost" onClick={() => void remove()}>Apagar</button>
          </div>
        </header>
        <div className="page-body">
          <section className="list-group">
            <h2 className="rotulo">Conversas</h2>
            {open.conversation_list.length === 0 && <p className="note">Nenhuma ainda. Comece uma aqui ou traga a que está aberta.</p>}
            {open.conversation_list.map((c) => (
              <button type="button" key={c.id} className="project-row" onClick={() => onOpenConversation(c.id)}>
                <strong>{c.title}</strong>
                <span>{dayLabel(utcDate(c.created_at))}</span>
              </button>
            ))}
          </section>
          {open.page_list.length > 0 && (
            <section className="list-group">
              <h2 className="rotulo">Páginas</h2>
              {open.page_list.map((p) => (
                <a key={p.id} className="project-row" href={p.path ? api.pageUrl(p.path) : undefined} target="_blank" rel="noopener noreferrer">
                  <strong>{p.title}</strong>
                  <span>{dayLabel(utcDate(p.created_at))}</span>
                </a>
              ))}
            </section>
          )}
          {open.file_list.length > 0 && (
            <section className="list-group">
              <h2 className="rotulo">Arquivos</h2>
              {open.file_list.map((f) => (
                <button type="button" key={f.id} className="project-row" onClick={() => void download(f.id, f.filename)}>
                  <strong>{f.filename}</strong>
                  <span>{f.kind === "image" ? "Foto" : f.media_type === "application/pdf" ? "PDF" : "Texto"} · {formatSize(f.size_bytes)}</span>
                </button>
              ))}
            </section>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="page projects" aria-labelledby="projects-title">
      <header className="page-head">
        <span className="rotulo">Projetos</span>
        <h1 id="projects-title">Cada assunto <em>no seu lugar.</em></h1>
        <p className="lede">Conversas, páginas e arquivos de um assunto juntos. Numa conversa do projeto, eu lembro do que foi falado nas outras.</p>
      </header>
      <div className="page-body">
        <form className="projects-new" onSubmit={(e) => void create(e)}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Novo projeto, ex.: Viagem a Santiago" maxLength={80} aria-label="Nome do novo projeto" />
          <button type="submit" className="projects-primary" disabled={!name.trim()}>Criar</button>
        </form>
        {list === null && <p className="note">Carregando…</p>}
        {list?.length === 0 && <p className="note page-empty">Nenhum projeto ainda.</p>}
        <div className="project-cards">
          {list?.map((p) => (
            <button type="button" key={p.id} className="project-card" onClick={() => void show(p.id)}>
              <strong>{p.name}</strong>
              <span>
                {p.conversations} {p.conversations === 1 ? "conversa" : "conversas"}
                {p.pages > 0 && ` · ${p.pages} ${p.pages === 1 ? "página" : "páginas"}`}
                {p.files > 0 && ` · ${p.files} ${p.files === 1 ? "arquivo" : "arquivos"}`}
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
