import type { ReactNode } from "react";

import type { WorkspaceView } from "./Rail";

const TITLES: Record<WorkspaceView, string> = {
  inbox: "Início",
  conversation: "Chat",
  projects: "Projetos",
  study: "Caderno",
  mac: "Mac",
  settings: "Ajustes",
};

/** The bar's title: the place, or the conversation's own title in the chat. */
export function pageTitle(view: WorkspaceView, conversationTitle?: string | null): string {
  if (view === "conversation" && conversationTitle?.trim()) return conversationTitle.trim();
  return TITLES[view];
}

/** The 52 px bar on top of the main area (computer only): where you are, and the actions of that
 * screen on the right. Not a heading: each screen keeps its own h1. */
export function PageBar({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-bar">
      <span className="page-bar-title">{title}</span>
      {children && <div className="page-bar-actions">{children}</div>}
    </div>
  );
}
