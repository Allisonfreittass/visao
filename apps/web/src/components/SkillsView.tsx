import { useEffect, useState } from "react";

import type { Api, Skill } from "../api";
import { Icon } from "./Icon";

/** "anthropics/skills · Apache-2.0", the line under each skill. */
export function skillOrigin(skill: Skill): string {
  return `vem de ${skill.source} · ${skill.license}`;
}

/** Habilidades: the ways of working he follows when a request fits one, each with a switch. */
export function SkillsView({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [skills, setSkills] = useState<Skill[] | null>(null);

  useEffect(() => {
    api.skills().then(setSkills).catch(onError);
  }, [api, onError]);

  async function toggle(skill: Skill) {
    const flip = (list: Skill[] | null, enabled: boolean) =>
      list?.map((s) => (s.id === skill.id ? { ...s, enabled } : s)) ?? null;
    setSkills((list) => flip(list, !skill.enabled));
    try {
      const saved = await api.setSkill(skill.id, !skill.enabled);
      setSkills((list) => flip(list, saved.enabled));
    } catch (e) {
      setSkills((list) => flip(list, skill.enabled));
      onError(e);
    }
  }

  return (
    <section className="page skills" aria-labelledby="skills-title">
      <header className="page-head">
        <h1 id="skills-title">Habilidades</h1>
        <p className="lede">
          Jeitos de trabalhar que ele segue quando o pedido combina com um deles. Cada um foi lido antes
          de entrar e é só texto: nada aqui roda código. Desligue o que não quiser.
        </p>
      </header>
      {skills === null ? (
        <p className="note">Carregando…</p>
      ) : (
        <ul className="routine-list">
          {skills.map((s) => (
            <li key={s.id} className="routine skill">
              <Icon name="sparkle" size={20} />
              <div className="routine-text">
                <span id={`skill-${s.id}`} className="routine-title">{s.name}</span>
                <span className="skill-description">{s.description}</span>
                <span className="routine-meta">
                  <a href={s.source_url} target="_blank" rel="noreferrer">{skillOrigin(s)}</a>
                </span>
              </div>
              <button
                type="button"
                role="switch"
                className="switch"
                aria-checked={s.enabled}
                aria-labelledby={`skill-${s.id}`}
                onClick={() => void toggle(s)}
              >
                <span aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="note routines-foot">
        Por enquanto elas vêm instaladas com o app. As que ele propuser aprender sozinho ainda não chegam aqui.
      </p>
    </section>
  );
}
