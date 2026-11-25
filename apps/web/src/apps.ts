// The owner's other apps through Composio (docs/APPS.md): how a waiting change reads on its card
// and aloud, and the catalog search in Ajustes.

import type { AppCatalogItem, ToolAction } from "./api";

function value(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (v === null || v === undefined) return "";
  if (Array.isArray(v) && v.every((x) => typeof x === "string" || typeof x === "number")) return v.join(", ");
  return JSON.stringify(v);
}

/** Every argument, one per line and in full: the card shows exactly what goes to the app. */
export function argumentLines(args: Record<string, unknown>): string {
  const entries = Object.entries(args ?? {});
  if (!entries.length) return "(sem argumentos)";
  return entries.map(([k, v]) => `${k}: ${value(v)}`).join("\n");
}

const clip = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text);

/** What the card says above the arguments: the tool, and what it does when the app says. */
export function cardText(action: ToolAction): string {
  return action.description ? `${action.tool_name}: ${action.description}` : action.tool_name;
}

/** The question read aloud in a call before a spoken yes counts (docs/VOICE.md). */
export function spokenApp(action: ToolAction): { id: string; question: string; done: string } {
  const what = action.description ? `${action.tool_name} (${clip(action.description, 80)})` : action.tool_name;
  return {
    id: action.id,
    question: `Preparei uma mudança no ${action.app}: ${clip(what, 140)}. Os detalhes estão na tela. Para fazer, diga "pode fazer". Para cancelar, diga "não".`,
    done: `Pronto, fiz no ${action.app}.`,
  };
}

const fold = (text: string) => text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

/** The catalog filtered by name, slug, description or category; most used first, as it came. */
export function searchCatalog(items: AppCatalogItem[], query: string, limit = 30): AppCatalogItem[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const found = words.length
    ? items.filter((a) => {
        const text = fold(`${a.name} ${a.slug} ${a.description} ${a.categories.join(" ")}`);
        return words.every((w) => text.includes(w));
      })
    : items;
  return found.slice(0, limit);
}
