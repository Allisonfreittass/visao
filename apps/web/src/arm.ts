// `/mac <projeto> <pedido>` in the chat: work for the arm on the owner's Mac (docs/BRACO.md).

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
