import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { Api, Project } from "../api";
import { Icon } from "./Icon";

interface ProjectsViewProps {
  api: Api;
  /** Opens the project's own chat (the project lives there, with its notes on top). */
  onOpenProject: (id: string) => void;
  onError: (e: unknown) => void;
  /** Goes up by one each time "Novo projeto" in the page bar is pressed. */
  newRequest?: number;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** What the project holds, for the card on top of its chat. */
export function projectSummary(p: Project): string {
  const notes = (p.notes ?? "").split("\n").filter((l) => l.trim()).length;
  const parts = [
    notes > 0 ? plural(notes, "anotação", "anotações") : null,
    p.panels ? plural(p.panels, "painel", "painéis") : null,
    p.pages > 0 ? plural(p.pages, "página", "páginas") : null,
    p.files > 0 ? plural(p.files, "arquivo", "arquivos") : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "só o chat, por enquanto";
}

/** The line under the name: his first note about the project (there is no description field),
 * and the live panels. Nothing made up when there is nothing. */
export function projectBlurb(p: Pick<Project, "notes" | "panels">): string {
  const first = (p.notes ?? "")
    .split("\n")
    .map((l) => l.replace(/^\s*[-•]\s*/, "").trim())
    .find(Boolean);
  const panels = p.panels ? ` ${p.panels === 1 ? "Tem um painel ativo." : `Tem ${p.panels} painéis ativos.`}` : "";
  if (first) return `${first.endsWith(".") ? first : `${first}.`}${panels}`;
  return panels ? panels.trim() : "Só o chat, por enquanto.";
}

/** "14 conversas", "3 páginas", "22 arquivos": what the project has, in Geist Mono. */
export function projectCounts(p: Pick<Project, "conversations" | "pages" | "files">): string[] {
  return [plural(p.conversations, "conversa", "conversas"), plural(p.pages, "página", "páginas"), plural(p.files, "arquivo", "arquivos")];
}

/** Projetos: the cards. Tapping one opens its chat, where everything about it lives (ADR-0021).
 * The dashed card at the end, or "Novo projeto" in the bar, names a new one. */
export function ProjectsView({ api, onOpenProject, onError, newRequest = 0 }: ProjectsViewProps) {
  const [list, setList] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    api.projects().then(setList).catch(onError);
  }, [api, onError]);
  useEffect(reload, [reload]);

  useEffect(() => { if (newRequest > 0) setCreating(true); }, [newRequest]);
  useEffect(() => { if (creating) input.current?.focus(); }, [creating, newRequest]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const project = await api.createProject(name.trim());
      setName("");
      setCreating(false);
      onOpenProject(project.id);
    } catch (e) {
      onError(e);
    }
  }

  return (
    <section className="page projects" aria-labelledby="projects-title">
      <header className="page-head">
        <h1 id="projects-title">Projetos</h1>
        {list?.length === 0 && (
          <p className="lede">Cada assunto, um projeto: um chat só dele, com o que ele anotou, os painéis, as páginas e os arquivos em cima. Dê um nome, ou peça na conversa: “cria o projeto…”.</p>
        )}
      </header>
      {list === null && <p className="note">Carregando…</p>}
      {list && (
        <ul className="project-grid">
          {list.map((p) => (
            <li key={p.id}>
              <button type="button" className="project-tile" onClick={() => onOpenProject(p.id)}>
                <span className="project-tile-name"><Icon name="folder" size={18} />{p.name}</span>
                <span className="project-tile-blurb">{projectBlurb(p)}</span>
                <span className="project-tile-counts">{projectCounts(p).map((c) => <span key={c}>{c}</span>)}</span>
              </button>
            </li>
          ))}
          <li>
            {creating ? (
              <form className="project-tile project-tile--new" onSubmit={(e) => void create(e)}>
                <label htmlFor="new-project" className="project-tile-label">Novo projeto</label>
                <input
                  id="new-project"
                  ref={input}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") { setCreating(false); setName(""); } }}
                  placeholder="Nome do projeto"
                  maxLength={80}
                />
                <span className="row-buttons">
                  <button type="submit" className="btn-primary btn-small" disabled={!name.trim()}>Criar</button>
                  <button type="button" className="btn-secondary btn-small" onClick={() => { setCreating(false); setName(""); }}>Cancelar</button>
                </span>
              </form>
            ) : (
              <button type="button" className="project-tile project-tile--add" onClick={() => setCreating(true)}>+ Novo projeto</button>
            )}
          </li>
        </ul>
      )}
    </section>
  );
}
