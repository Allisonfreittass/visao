/** Confirmations and short questions drawn in the page, in place of window.confirm and
 * window.prompt. The Mac app's window (Tauri, on macOS WebKit) shows neither: both answered
 * "cancel" at once, so "Desconectar o Google" did nothing (25/11/2026). Same look as the share
 * dialog (palette-scrim + share), so nothing new to style. */

type Options = { ok?: string; value?: string; input?: boolean };

function ask(message: string, { ok = "Confirmar", value = "", input = false }: Options): Promise<string | null> {
  return new Promise((resolve) => {
    const before = document.activeElement as HTMLElement | null;
    const scrim = document.createElement("div");
    scrim.className = "palette-scrim";
    const box = document.createElement("div");
    box.className = "share ask";
    box.setAttribute("role", input ? "dialog" : "alertdialog");
    box.setAttribute("aria-modal", "true");
    const text = document.createElement("p");
    text.className = "ask-text";
    text.id = `ask-${Date.now()}`;
    text.textContent = message;
    box.setAttribute("aria-labelledby", text.id);
    box.append(text);
    let field: HTMLInputElement | null = null;
    if (input) {
      field = document.createElement("input");
      field.className = "ask-input";
      field.value = value;
      field.setAttribute("aria-labelledby", text.id);
      box.append(field);
    }
    const actions = document.createElement("div");
    actions.className = "ask-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "Cancelar";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.textContent = ok;
    actions.append(cancel, confirm);
    box.append(actions);
    scrim.append(box);

    const done = (answer: string | null) => {
      window.removeEventListener("keydown", onKey, true);
      scrim.remove();
      before?.focus?.();
      resolve(answer);
    };
    const accept = () => done(field ? field.value : "");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(null); }
      else if (e.key === "Enter" && (field ? document.activeElement === field : document.activeElement !== cancel)) { e.preventDefault(); accept(); }
      else if (e.key === "Tab") {
        // Focus stays inside the dialog.
        const stops = [field, cancel, confirm].filter(Boolean) as HTMLElement[];
        const at = stops.indexOf(document.activeElement as HTMLElement);
        const next = e.shiftKey ? (at <= 0 ? stops.length - 1 : at - 1) : (at + 1) % stops.length;
        e.preventDefault();
        stops[next].focus();
      }
    };
    cancel.addEventListener("click", () => done(null));
    confirm.addEventListener("click", accept);
    scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) done(null); });
    window.addEventListener("keydown", onKey, true);
    document.body.append(scrim);
    if (field) { field.focus(); field.select(); } else confirm.focus();
  });
}

/** Yes or no, in the page. Resolves true only on the confirm button (or Enter on it). */
export async function confirmar(message: string, ok = "Confirmar"): Promise<boolean> {
  return (await ask(message, { ok })) !== null;
}

/** A short text answer, in the page; null when cancelled. */
export function perguntar(message: string, value = "", ok = "Salvar"): Promise<string | null> {
  return ask(message, { ok, value, input: true });
}
