import { type FormEvent, useEffect, useState } from "react";

import type { Api, Project } from "../api";

interface ProjectColumnProps {
  api: Api;
  current: string | null;
  /** Changes when a project is made, renamed or deleted, to list it again. */
  refreshKey: number;
  onOpen: (id: string) => void;
  onError: (e: unknown) => void;
}

/** On a computer, in a project's chat: the projects on the left, one tap to switch (ADR-0021). */
export function ProjectColumn({ api, current, refreshKey, onOpen, onError }: ProjectColumnProps) {
  const [list, setList] = useState<Project[]>([]);
  const [name, setName] = useState("");

  useEffect(() => {
    api.projects().then(setList).catch(onError);
  }, [api, onError, refreshKey]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const project = await api.createProject(name.trim());
      setName("");
      setList((l) => [project, ...l]);
      onOpen(project.id);
    } catch (e) {
      onError(e);
    }
  }

  return (
    <nav className="home-column project-column" aria-label="Projetos">
      <form className="projects-new" onSubmit={(e) => void create(e)}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Novo projeto" maxLength={80} aria-label="Nome do novo projeto" />
      </form>
      <ul>
        {list.map((p) => (
          <li key={p.id}>
            <button type="button" aria-current={p.id === current ? "page" : undefined} onClick={() => onOpen(p.id)}>{p.name}</button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
