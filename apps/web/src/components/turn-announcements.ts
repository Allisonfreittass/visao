export type TurnAnnouncement = { type: "start" | "complete" | "cancel" } | { type: "tool"; label: string };

/** Discrete announcements only; stream deltas never pass through this helper. */
export function turnAnnouncement(event: TurnAnnouncement): string {
  if (event.type === "tool") return `Usando uma ferramenta: ${event.label}.`;
  if (event.type === "start") return "Visão começou a responder.";
  if (event.type === "complete") return "Resposta concluída.";
  return "Resposta interrompida.";
}
