import { useState } from "react";

import { type Source, utcDate } from "../api";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** What the pill says: "ao vivo · google.com · 10:14" when it read prices live, else "3 fontes". */
export function sourcesLabel(sources: Source[], at: string): string {
  const live = sources.filter((s) => s.source === "ao vivo");
  if (live.length > 0) {
    const hosts = [...new Set(live.map((s) => host(s.url)))];
    const time = utcDate(at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const others = sources.length - live.length;
    return `ao vivo · ${hosts.slice(0, 2).join(", ")}${hosts.length > 2 ? "…" : ""} · ${time}${others > 0 ? ` · +${others}` : ""}`;
  }
  return sources.length === 1 ? "1 fonte" : `${sources.length} fontes`;
}

/** The sources of a reply, out of the way: a small pill that opens the list. */
export function SourcesPill({ sources, at }: { sources: Source[]; at: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sources-pill">
      <button type="button" className="sources-pill-button" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {sourcesLabel(sources, at)}
      </button>
      {open && (
        <ol className="sources" aria-label="Fontes">
          {sources.map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                {s.title}
              </a>{" "}
              <span>· {s.source === "ao vivo" ? `ao vivo, ${host(s.url)}` : s.source}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
