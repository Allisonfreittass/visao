import { describe, expect, it } from "vitest";

import type { ArmTask } from "./api";
import { parseMacCommand, taskDetail, undoQuestion } from "./arm";

describe("parseMacCommand", () => {
  it("splits the project from a multi-line request", () => {
    expect(parseMacCommand("/mac visao rode os testes\ne me diga o que falhou")).toEqual({
      project: "visao",
      prompt: "rode os testes\ne me diga o que falhou",
    });
  });

  it("asks for usage when something is missing and ignores normal messages", () => {
    expect(parseMacCommand("/mac")).toBe("usage");
    expect(parseMacCommand("/mac visao")).toBe("usage");
    expect(parseMacCommand("me ajuda no mac")).toBeNull();
    expect(parseMacCommand("/macarrão é bom")).toBeNull();
  });
});

function task(extra: Partial<ArmTask>): ArmTask {
  return {
    id: "t", project: "visao", prompt: "conserta", status: "done", requested_by: "owner",
    result: "", error: "", cost_usd: null, claude_session_id: null, conversation_id: null,
    created_at: "2026-11-23T10:00:00", finished_at: null, kind: "work", undo_of: null,
    until_tests: false, changed_files: null, tests: null, undone_at: null, can_undo: false,
    ...extra,
  };
}

describe("taskDetail", () => {
  it("says what the arm measured and how the tests went", () => {
    const changed = [{ path: "a.py", status: "M" as const }, { path: "b.py", status: "A" as const }];
    expect(taskDetail(task({ changed_files: changed, tests: { command: "make check", passed: true, attempts: 2 } })))
      .toBe("2 arquivos mudados · testes passaram na 2ª");
    expect(taskDetail(task({ changed_files: [], tests: { command: "x", passed: false, attempts: 3 } })))
      .toBe("nenhum arquivo mudou · testes falharam 3×");
    expect(taskDetail(task({ changed_files: [changed[0]] }))).toBe("1 arquivo mudado");
    expect(taskDetail(task({ status: "approved", until_tests: true }))).toBe("");
    expect(taskDetail(task({ kind: "undo", changed_files: changed }))).toBe("2 arquivos de volta");
    expect(taskDetail(task({ changed_files: changed, undone_at: "x" }))).toBe("2 arquivos mudados · desfeito");
    expect(taskDetail(task({}))).toBe("");
  });

  it("lists the files before an undo", () => {
    const changed = Array.from({ length: 10 }, (_, i) => ({ path: `f${i}.py`, status: "M" as const }));
    const question = undoQuestion(task({ changed_files: changed }));
    expect(question).toContain("Voltar 10 arquivos de visao");
    expect(question).toContain("• f7.py");
    expect(question).not.toContain("• f8.py");
    expect(question).toContain("e mais 2");
  });
});
