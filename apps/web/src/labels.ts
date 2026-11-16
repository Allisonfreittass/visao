/** Short, human dates for lists: "Hoje, 11:33", "Ontem, 13:33", "10/11, 09:12". */
export function dayLabel(date: Date, now: Date = new Date()): string {
  const time = date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(date)) / 86_400_000);
  if (diff === 0) return `Hoje, ${time}`;
  if (diff === 1) return `Ontem, ${time}`;
  const sameYear = date.getFullYear() === now.getFullYear();
  const dayPart = date.toLocaleDateString("pt-BR", sameYear ? { day: "2-digit", month: "2-digit" } : { dateStyle: "short" });
  return `${dayPart}, ${time}`;
}

/** "Hoje", "Ontem", "14/11" or "14/11/2025": the day of a divider in the continuous chat. */
export function dividerDay(date: Date, now: Date = new Date()): string {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(date)) / 86_400_000);
  if (diff === 0) return "Hoje";
  if (diff === 1) return "Ontem";
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString("pt-BR", sameYear ? { day: "2-digit", month: "2-digit" } : { dateStyle: "short" });
}

/** Where a divider goes in the continuous chat, by message id: a new day, a stretch's title. */
export function dividers(
  messages: Array<{ id: string; created_at: string }>,
  segments: Array<{ first_message_id: string; title: string; status: string }>,
  toDate: (iso: string) => Date,
  now: Date = new Date(),
): Map<string, string> {
  const titles = new Map(segments.filter((s) => s.status === "summarized" && s.title).map((s) => [s.first_message_id, s.title]));
  const found = new Map<string, string>();
  let lastDay = "";
  for (const m of messages) {
    const day = dividerDay(toDate(m.created_at), now);
    const title = titles.get(m.id);
    if (day !== lastDay || title) found.set(m.id, title ? `${title} · ${day}` : day);
    lastDay = day;
  }
  return found;
}

/** How the menu names a conversation: the continuous one is "Conversa". */
export function conversationLabel(c: { continuous?: boolean; title?: string | null; created_at: string }, toDate: (iso: string) => Date): string {
  if (c.continuous) return "Conversa";
  return c.title ?? dayLabel(toDate(c.created_at));
}

export const TASK_STATUS: Record<string, string> = {
  proposed: "esperando você",
  approved: "na fila",
  running: "rodando",
  done: "feito",
  failed: "falhou",
  rejected: "recusado",
  cancelled: "cancelado",
};
