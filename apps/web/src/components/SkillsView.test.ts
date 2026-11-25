import { describe, expect, it } from "vitest";

import type { Skill } from "../api";
import { NOT_YET } from "./NotYetView";
import { skillOrigin } from "./SkillsView";

const skill: Skill = {
  id: "achar-bugs",
  name: "Achar a causa de um bug",
  description: "Investiga um erro antes de propor conserto.",
  origin: "instalada",
  source: "obra/superpowers",
  source_url: "https://github.com/obra/superpowers/tree/abc/skills/systematic-debugging",
  license: "MIT",
  installed_on: "2026-11-25",
  enabled: true,
};

describe("Habilidades", () => {
  it("says where each skill came from and under which license", () => {
    expect(skillOrigin(skill)).toBe("vem de obra/superpowers · MIT");
  });

  it("is no longer a place that says 'ainda não disponível'", () => {
    expect(Object.keys(NOT_YET)).not.toContain("skills");
  });
});
