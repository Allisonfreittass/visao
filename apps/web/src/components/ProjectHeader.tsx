import { useCallback, useEffect, useState } from "react";

import type { Api, ProjectDetail } from "../api";
import { attachmentUrl, formatSize } from "../attachments";
import { Icon } from "./Icon";
import { PanelsBoard } from "./PanelsBoard";
import { projectSummary } from "./ProjectsView";
import { confirmar, perguntar } from "../ask";

interface ProjectHeaderProps {
  api: Api;
  projectId: string;
  /** Changes whenever a turn ends here, so new notes show without reloading. */
  refreshKey: number;
  /** On a phone the list is not beside the chat: a way back to it. */
  showBack: boolean;
  onBack: () => void;
  onDeleted: () => void;
  onRenamed: (name: string) => void;
  onError: (e: unknown) => void;
}

/** On top of a project's chat: its name, and what it holds (notes, panels, pages, files) in a
 * card that opens and closes (ADR-0021). */
export function ProjectHeader({ api, projectId, refreshKey, showBack, onBack, onDeleted, onRenamed, onError }: ProjectHeaderProps) {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const load = useCallback(() => {
    api.project(projectId).then(setProject).catch(onError);
  }, [api, projectId, onError]);

  useEffect(load, [load, refreshKey]);

  if (!project) return null;
  const notes = (project.notes ?? "").split("\n").filter((l) => l.trim());

  async function saveNotes() {
    if (!project || editing === null) return;
    try {
      const saved = await api.setProjectNotes(project.id, editing);
      setProject({ ...project, notes: saved.notes });
      setEditing(null);
    } catch (e) {
      onError(e);
    }
  }

  async function rename() {
    if (!project) return;
    const next = await perguntar("Novo nome do projeto", project.name);
    if (!next?.trim()) return;
    try {
      const saved = await api.renameProject(project.id, next.trim());
      setProject({ ...project, name: saved.name });
      onRenamed(saved.name);
    } catch (e) {
      onError(e);
    }
  }

  async function remove() {
    if (!project || !(await confirmar(`Apagar o projeto “${project.name}”? As anotações vão junto; o chat, as páginas, os arquivos e os painéis continuam, fora de projeto.`, "Apagar"))) return;
    try {
      await api.deleteProject(project.id);
      onDeleted();
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

  return (
    <div className="project-head">
      <div className="project-head-bar">
        {showBack && (
          <button type="button" className="project-head-back" onClick={onBack} aria-label="Voltar para Projetos" title="Projetos">
            <Icon name="back" size={20} />
          </button>
        )}
        <strong className="project-head-name">{project.name}</strong>
      </div>
      <button type="button" className="project-head-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {projectSummary(project)} <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="project-head-body">
          <section className="project-notes" aria-label="Anotações">
            <h2 className="rotulo">Anotações</h2>
            {editing === null ? (
              <>
                {notes.length > 0 ? (
                  <ul>{notes.map((line, i) => <li key={i}>{line.replace(/^-\s*/, "")}</li>)}</ul>
                ) : (
                  <p className="note">Nada anotado ainda. Peça aqui: “anota isso”.</p>
                )}
                <button type="button" className="ghost project-head-edit" onClick={() => setEditing(project.notes ?? "")}>Editar anotações</button>
              </>
            ) : (
              <>
                <textarea value={editing} rows={8} onChange={(e) => setEditing(e.target.value)} aria-label="Anotações do projeto" />
                <div className="row">
                  <button type="button" className="projects-primary" onClick={() => void saveNotes()}>Salvar</button>
                  <button type="button" className="ghost" onClick={() => setEditing(null)}>Cancelar</button>
                </div>
              </>
            )}
          </section>
          <PanelsBoard api={api} nothingPending={false} onDraft={() => undefined} projectId={project.id} />
          {project.page_list.length > 0 && (
            <section className="list-group" aria-label="Páginas">
              <h2 className="rotulo">Páginas</h2>
              {project.page_list.map((p) => (
                <a key={p.id} className="project-row" href={p.path ? api.pageUrl(p.path) : undefined} target="_blank" rel="noopener noreferrer">
                  <strong>{p.title}</strong>
                </a>
              ))}
            </section>
          )}
          {project.file_list.length > 0 && (
            <section className="list-group" aria-label="Arquivos">
              <h2 className="rotulo">Arquivos</h2>
              {project.file_list.map((f) => (
                <button type="button" key={f.id} className="project-row" onClick={() => void download(f.id, f.filename)}>
                  <strong>{f.filename}</strong>
                  <span>{formatSize(f.size_bytes)}</span>
                </button>
              ))}
            </section>
          )}
          <div className="row project-head-actions">
            <button type="button" className="ghost" onClick={() => void rename()}>Renomear</button>
            <button type="button" className="ghost" onClick={() => void remove()}>Apagar projeto</button>
          </div>
        </div>
      )}
    </div>
  );
}
