import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Icon, type IconName } from "./Icon";

export interface PaletteItem {
  id: string;
  label: string;
  icon: IconName;
  group: "Ações" | "Conversas" | "Projetos";
  /** Extra words that match the search (the place's other names). */
  keywords?: string;
  run: () => void;
}

/** Lowercase, without accents: "Início" matches "inicio". */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Every word typed must appear in the label or the keywords. Empty search: everything. */
export function filterItems(items: PaletteItem[], query: string): PaletteItem[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return items;
  return items.filter((item) => {
    const hay = fold(`${item.label} ${item.keywords ?? ""}`);
    return words.every((w) => hay.includes(w));
  });
}

/** Ctrl/⌘+K: search conversations, projects and commands. Arrows move, Enter opens, Esc closes. */
export function CommandPalette({ items, onClose }: { items: PaletteItem[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const shown = useMemo(() => filterItems(items, query), [items, query]);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => before?.focus?.();
  }, []);
  useEffect(() => setActive(0), [query]);

  function run(item: PaletteItem | undefined) {
    if (!item) return;
    onClose();
    item.run();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); run(shown[active]); }
    else if (e.key === "Tab") e.preventDefault(); // one field: focus stays in the dialog
  }

  useEffect(() => {
    document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, listId]);

  let lastGroup = "";
  return (
    <div className="palette-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Comandos" onKeyDown={onKeyDown}>
        <div className="palette-search">
          <Icon name="search" size={18} />
          <label htmlFor={`${listId}-input`} className="visually-hidden">Buscar</label>
          <input
            id={`${listId}-input`}
            ref={inputRef}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={shown[active] ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
            placeholder="Buscar conversas, projetos ou um comando…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="button" className="palette-close" aria-label="Fechar" title="Fechar" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <div id={listId} role="listbox" aria-label="Resultados" className="palette-list">
          {shown.length === 0 && <p className="palette-empty">Nada com esse nome.</p>}
          {shown.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <div key={item.id} role="presentation">
                {header && <p className="palette-group" role="presentation">{header}</p>}
                <div
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  className="palette-item"
                  onMouseMove={() => setActive(i)}
                  onClick={() => run(item)}
                >
                  <Icon name={item.icon} size={16} />
                  <span>{item.label}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="palette-foot" aria-hidden="true"><span>↑↓ navegar</span><span>↵ abrir</span><span>esc fechar</span></div>
      </div>
    </div>
  );
}
