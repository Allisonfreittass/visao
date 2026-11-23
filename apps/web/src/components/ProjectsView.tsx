import { type FormEvent, useCallback, useEffect, useState } from "react";

import type { Api, Project } from "../api";

interface ProjectsViewProps {
  api: Api;
  /** Opens the project's own chat (the project lives there, with its notes on top). */
  onOpenProject: (id: string) => void;
  onError: (e: unknown) => void;
}

export function projectSummary(p: Project): string {
  const notes = (p.notes ?? "").split("\n").filter((l) => l.trim()).length;
  const parts = [
    notes > 0 ? `${notes} ${notes === 1 ? "anotação" : "anotações"}` : null,
    p.panels ? `${p.panels} ${p.panels === 1 ? "painel" : "painéis"}` : null,
    p.pages > 0 ? `${p.pages} ${p.pages === 1 ? "página" : "páginas"}` : null,
    p.files > 0 ? `${p.files} ${p.files === 1 ? "arquivo" : "arquivos"}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "só o chat, por enquanto";
}

/** Projetos: the list. Tapping one opens its chat, where everything about it lives (ADR-0021). */
export function ProjectsView({ api, onOpenProject, onError }: ProjectsViewProps) {
  const [list, setList] = useState<Project[] | null>(null);
  const [name, setName] = useState("");

  const reload = useCallback(() => {
    api.projects().then(setList).catch(onError);
  }, [api, onError]);

  useEffect(reload, [reload]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const project = await api.createProject(name.trim());
      setName("");
      onOpenProject(project.id);
    } catch (e) {
      onError(e);
    }
  }

  const form = (
    <form className="projects-new" onSubmit={(e) => void create(e)}>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do novo projeto" maxLength={80} aria-label="Nome do novo projeto" />
      <button type="submit" className="projects-primary" disabled={!name.trim()}>Criar</button>
    </form>
  );

  if (list?.length === 0) {
    return (
      <section className="projects-vazio" aria-labelledby="projects-title">
        <h1 id="projects-title">Cada assunto, <em>um projeto.</em></h1>
        <p className="lede">
          Um chat só dele, com o que eu anotei, os painéis, as páginas e os arquivos em cima. Dê um nome, ou me
          peça na conversa: “cria o projeto…”.
        </p>
        {form}
      </section>
    );
  }

  return (
    <section className="page projects" aria-labelledby="projects-title">
      <header className="page-head">
        <h1 id="projects-title">Projetos</h1>
        <p className="lede">Tocar abre o chat do projeto, com as anotações, os painéis e os arquivos em cima.</p>
      </header>
      <div className="page-body">
        {form}
        {list === null && <p className="note">Carregando…</p>}
        <div className="project-cards">
          {list?.map((p) => (
            <button type="button" key={p.id} className="project-card" onClick={() => onOpenProject(p.id)}>
              <strong>{p.name}</strong>
              <span>{projectSummary(p)}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
