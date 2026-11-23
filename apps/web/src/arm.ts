// `/mac <projeto> <pedido>` in the chat: work for the arm on the owner's Mac (docs/BRACO.md).

import type { ArmTask } from "./api";

export interface MacCommand {
  project: string;
  prompt: string;
}

export function parseMacCommand(text: string): MacCommand | "usage" | null {
  const match = text.trim().match(/^\/mac(?:\s+(\S+))?(?:\s+([\s\S]+))?$/i);
  if (!match) return null;
  const [, project, prompt] = match;
  if (!project || !prompt?.trim()) return "usage";
  return { project, prompt: prompt.trim() };
}

function files(count: number): string {
  return count === 1 ? "1 arquivo" : `${count} arquivos`;
}

/** One quiet line under a task: what the arm measured, never what Claude said. */
export function taskDetail(task: ArmTask): string {
  const parts: string[] = [];
  const changed = task.changed_files;
  if (task.kind === "undo") {
    if (task.status === "done" && changed?.length) parts.push(`${files(changed.length)} de volta`);
  } else if (changed) {
    if (!changed.length) parts.push("nenhum arquivo mudou");
    else parts.push(changed.length === 1 ? "1 arquivo mudado" : `${changed.length} arquivos mudados`);
  }
  const tests = task.tests;
  if (tests) {
    if (tests.passed) parts.push(tests.attempts > 1 ? `testes passaram na ${tests.attempts}ª` : "testes passaram");
    else if (tests.error) parts.push("testes não rodaram");
    else parts.push(`testes falharam ${tests.attempts}×`);
  }
  if (task.undone_at) parts.push("desfeito");
  return parts.join(" · ");
}

/** The question before an undo: which files go back. */
export function undoQuestion(task: ArmTask): string {
  const changed = task.changed_files ?? [];
  const shown = changed.slice(0, 8).map((f) => `• ${f.path}`);
  if (changed.length > 8) shown.push(`• e mais ${changed.length - 8}`);
  return `Voltar ${files(changed.length)} de ${task.project} ao que eram antes desta tarefa?\n\n${shown.join("\n")}\n\nSe algum mudou depois, eu não mexo em nada.`;
}
