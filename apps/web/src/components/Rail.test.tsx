import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Conversation } from "../api";
import css from "../layout.css?raw";
import { Rail, recentConversations } from "./Rail";

const LONGO = "Correção do assistente ao cotar voos e hospedagem para Santiago em agosto";

function conversa(id: string, title: string | null, created_at: string, continuous = false): Conversation {
  return { id, title, created_at, continuous } as Conversation;
}

function barra(conversations: Conversation[]): string {
  return renderToStaticMarkup(
    <Rail
      open={false}
      view="conversation"
      online
      pendingCount={0}
      conversations={conversations}
      currentConversation={null}
      preparing={false}
      onView={() => {}}
      onNewChat={() => {}}
      onSearch={() => {}}
      onOpenConversation={() => {}}
    />,
  );
}

/** The declarations of the first rule whose selector list is exactly `selector`. */
function regra(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return css.match(new RegExp(`(?:^|\\n)${escaped} \\{([^}]*)\\}`))?.[1] ?? "";
}

describe("recentConversations", () => {
  it("lists titled conversations, newest first, without the continuous one", () => {
    const list = [
      conversa("a", "Antiga", "2026-11-01T10:00:00Z"),
      conversa("b", null, "2026-11-02T10:00:00Z"),
      conversa("c", "Contínua", "2026-11-03T10:00:00Z", true),
      conversa("d", "Nova", "2026-11-04T10:00:00Z"),
    ];
    expect(recentConversations(list).map((c) => c.id)).toEqual(["d", "a"]);
  });
});

describe("Rail", () => {
  it("cuts a long title in the list and keeps the whole of it in the tooltip", () => {
    const html = barra([conversa("x", LONGO, "2026-11-25T10:00:00Z")]);
    expect(html).toContain(`title="${LONGO}"`);
    expect(html).toContain(`<span class="rail-chat-title">${LONGO}</span>`);
  });

  it("keeps the browser's translator off the name", () => {
    expect(barra([])).toMatch(/<span class="rail-wordmark"[^>]*translate="no"[^>]*>VISAO<\/span>/);
  });

  // On a touch screen :hover sticks after the tap; the rows answer the touch with :active instead.
  it("shows hover only where there is a mouse", () => {
    expect(css).toMatch(/@media \(hover: hover\) \{\n {2}\.rail-nav button:hover, \.rail-chats button:hover/);
    expect(regra(".rail-nav button:active, .rail-chats button:active")).toMatch(/background: var\(--surface-2\)/);
  });

  // The bar is 248 px and a long title must not widen it: an auto grid column grows to the longest
  // title (the horizontal scroll bar in the owner's screenshot), minmax(0, 1fr) does not.
  it("keeps a fixed width that its items cannot stretch", () => {
    expect(regra(".rail")).toMatch(/width: 248px/);
    expect(regra(".rail")).toMatch(/max-width: 248px/);
    expect(regra(".rail")).toMatch(/overflow-x: hidden/);
    // As a drawer on the phone, scrolling it does not carry on to the page behind.
    expect(regra(".rail")).toMatch(/overscroll-behavior: contain/);
    expect(regra(".rail-nav, .rail-section, .rail-chats, .rail-bottom")).toMatch(/grid-template-columns: minmax\(0, 1fr\)/);
    expect(regra(".rail-chat-title")).toMatch(/text-overflow: ellipsis/);
    expect(regra(".rail-chat-title")).toMatch(/white-space: nowrap/);
  });
});
