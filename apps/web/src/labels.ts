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

export const TASK_STATUS: Record<string, string> = {
  proposed: "esperando você",
  approved: "na fila",
  running: "rodando",
  done: "feito",
  failed: "falhou",
  rejected: "recusado",
  cancelled: "cancelado",
};
